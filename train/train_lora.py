"""
Qwen2.5-3B-Instruct LoRA 微调训练脚本（6GB RTX 3060 专用）
- 4bit NF4 量化 + 双量化
- Unsloth 注入 LoRA，覆盖注意力+MLP
- 显存监控 Callback
- 断点续训（--resume）
- 训练后合并导出 merged 权重（fp16）

依赖：
    pip install "unsloth[windows-torch230] @ git+https://github.com/unslothai/unsloth.git"
    pip install "trl>=0.9" "transformers>=4.45" "datasets" "accelerate" "bitsandbytes-windows" "peft"

用法：
    python train_lora.py --data ../data/tmlr_cot_data.jsonl --out ../outputs/qwen25-3b-tmlr
    python train_lora.py --data merged.jsonl --resume ../outputs/qwen25-3b-tmlr --out ../outputs/qwen25-3b-tmlr
"""

import argparse
import os
import sys
import torch
from datetime import datetime


# ---------------- 1. 环境检查 ----------------
def env_check():
    print("=" * 50)
    print(f"[env] Python: {sys.version.split()[0]}")
    print(f"[env] torch: {torch.__version__}")
    print(f"[env] CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        free, total = torch.cuda.mem_get_info(0)
        print(f"[env] GPU: {props.name} | 总显存 {total/1024**3:.1f}GB | 空闲 {free/1024**3:.1f}GB")
        if total < 6.5 * 1024**3:
            print("[warn] 检测到显存 < 6.5GB，已按最小配置运行（batch=2, seq=2048）。")
            return "low"
        return "ok"
    else:
        raise SystemExit("[fatal] 未检测到 CUDA，无法训练。请确认 torch 装的是 CUDA 版本。")


# ---------------- 2. 显存监控 Callback ----------------
class GPUMemCallback:
    """轻量显存日志（不依赖 transformers TrainerCallback，手动在日志步打印）。"""
    @staticmethod
    def snapshot(tag: str):
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info(0)
            used = (total - free) / 1024**3
            print(f"[{tag}] GPU 已用 {used:.2f}GB / {total/1024**3:.2f}GB")


# ---------------- 3. 数据格式化 ----------------
def formatting_func(examples, tokenizer):
    """把 ShareGPT conversations 转成单条文本（应用 Qwen chat 模板）。"""
    texts = []
    for conv in examples["conversations"]:
        messages = [{"role": m["role"], "content": m["content"]} for m in conv]
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
        texts.append(text)
    return texts


# ---------------- 4. 主训练 ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct")
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default="../outputs/qwen25-3b-tmlr")
    ap.add_argument("--resume", default="", help="断点续训：传入之前的 output_dir")
    # 默认值依据 GitHub 社区推理类微调经验调整（见方案文档"参考仓库"）：
    #   - lr 从通用 2e-4 降到 1e-4，防推理任务过拟合（数学推理仓库甚至用 5e-6）
    #   - epochs 从 3 降到 2，配合早停，避免记忆化
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--seq-len", type=int, default=4096)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--lora-r", type=int, default=32)
    ap.add_argument("--eval-ratio", type=float, default=0.05,
                    help="从训练集切出的验证集比例，用于早停；设 0 关闭验证/早停")
    ap.add_argument("--early-stop-patience", type=int, default=3,
                    help="早停耐心值（连续多少次 eval 无改善则停）")
    ap.add_argument("--merge", action="store_true", help="训练后合并导出 fp16")
    ap.add_argument("--hf-cache", type=str, default="",
                    help="HuggingFace 缓存目录（默认 F:/hf_cache；传此参数强制覆盖已有环境变量）")
    args = ap.parse_args()

    # C 盘空间治本策略：HuggingFace 模型/数据集缓存重定向到 F 盘（3B 权重约 6GB，不占 C 盘）
    if args.hf_cache:
        os.environ["HF_HOME"] = args.hf_cache
        os.environ["HF_DATASETS_CACHE"] = os.path.join(args.hf_cache, "datasets")
        os.environ["TRANSFORMERS_CACHE"] = os.path.join(args.hf_cache, "models")
    else:
        os.environ.setdefault("HF_HOME", "F:/hf_cache")
        os.environ.setdefault("HF_DATASETS_CACHE", "F:/hf_cache/datasets")
        os.environ.setdefault("TRANSFORMERS_CACHE", "F:/hf_cache/models")

    tier = env_check()
    # 安全降级仅作用于"用户未显式指定"的情况：
    # 3060(6GB)会被判定为 low 档。若用户用 --batch/--seq-len 明确指定，则尊重其意图（自担 OOM 风险），
    # 否则保持保守的 batch=2/seq=2048（与方案文档"首次跑通优先于吞吐"一致）。
    user_set_batch = "--batch" in sys.argv
    user_set_seq = "--seq-len" in sys.argv
    if tier == "low":
        if not user_set_batch:
            args.batch = min(args.batch, 2)
        if not user_set_seq:
            args.seq_len = min(args.seq_len, 2048)

    from unsloth import FastLanguageModel
    from trl import SFTTrainer
    from transformers import TrainingArguments, EarlyStoppingCallback
    from datasets import load_dataset

    GPUMemCallback.snapshot("load-start")

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model,
        max_seq_length=args.seq_len,
        dtype=torch.float16,
        load_in_4bit=True,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        lora_alpha=args.lora_r * 2,
        lora_dropout=0.1,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        bias="none",
        use_gradient_checkpointing="unsloth",
    )
    GPUMemCallback.snapshot("load-end")

    data = load_dataset("json", data_files=args.data, split="train")
    # 加 text 字段供 SFTTrainer 使用
    data = data.map(lambda ex: {"text": formatting_func({"conversations": [ex["conversations"]]}, tokenizer)[0]},
                    remove_columns=data.column_names)

    # 切出验证集用于早停（防过拟合，社区推理类微调普遍做法）
    eval_data = None
    if args.eval_ratio and args.eval_ratio > 0 and len(data) >= 20:
        split = data.train_test_split(test_size=args.eval_ratio, seed=42)
        data, eval_data = split["train"], split["test"]
        print(f"[data] 训练 {len(data)} 条 / 验证 {len(eval_data)} 条")
    else:
        print(f"[data] 训练样本数: {len(data)}（未切验证集，早停关闭）")

    # 有验证集才启用按步评估 + 早停 + 取最优
    eval_kwargs = {}
    callbacks = []
    if eval_data is not None:
        eval_kwargs = dict(
            eval_strategy="steps",
            eval_steps=50,
            save_strategy="steps",
            save_steps=50,
            load_best_model_at_end=True,
            metric_for_best_model="eval_loss",
            greater_is_better=False,
            save_total_limit=2,
        )
        callbacks = [EarlyStoppingCallback(early_stopping_patience=args.early_stop_patience)]
    else:
        eval_kwargs = dict(save_strategy="epoch")

    resume_dir = args.resume or None
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=data,
        eval_dataset=eval_data,
        max_seq_length=args.seq_len,
        callbacks=callbacks,
        args=TrainingArguments(
            per_device_train_batch_size=args.batch,
            gradient_accumulation_steps=4,
            warmup_ratio=0.03,
            num_train_epochs=args.epochs,
            learning_rate=args.lr,
            lr_scheduler_type="cosine",
            optim="paged_adamw_8bit",
            fp16=True,
            max_grad_norm=0.3,
            logging_steps=10,
            output_dir=args.out,
            report_to="none",
            **eval_kwargs,
        ),
    )

    GPUMemCallback.snapshot("train-start")
    if resume_dir and os.path.isdir(os.path.join(resume_dir, "checkpoint-last")):
        print(f"[resume] 从 {resume_dir} 续训")
        trainer.train(resume_from_checkpoint=os.path.join(resume_dir, "checkpoint-last"))
    else:
        trainer.train()
    GPUMemCallback.snapshot("train-end")

    # 保存 LoRA 适配器
    model.save_pretrained(args.out)
    tokenizer.save_pretrained(args.out)
    print(f"[done] LoRA 已保存 -> {args.out}")

    if args.merge:
        merged_dir = args.out + "-merged"
        model.save_pretrained_merged(merged_dir, tokenizer, save_method="merged_16bit")
        print(f"[done] 合并权重已导出 -> {merged_dir}（约 6GB fp16，可用 vLLM/llama.cpp 部署）")


if __name__ == "__main__":
    main()
