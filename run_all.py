"""
一键编排：M0(验证) -> M1(数据) -> M2(训练) -> M3(评估)
串联 data/build_dataset.py, data/build_dataset_fulltext.py, data/convert_manuscript.py,
train/train_lora.py, eval/run_eval.py。

依赖：本机已装 unsloth 等训练依赖，且有 NVIDIA GPU（M0/M2 需训练）。
M1 的 arXiv 抓取需联网 + arxiv 库；可用 --from-dir 走离线论文源。

用法：
    python run_all.py                      # 全流程 M0->M3
    python run_all.py --papers 150         # 指定 M1 抓取论文数
    python run_all.py --skip-m0 --skip-m3   # 跳过验证与评估，只做数据+训练
    python run_all.py --manuscript ../my_paper.tex   # 追加你的稿件到训练集
    python run_all.py --reviews review_corpus.jsonl  # 追加"审稿偏好"样本（路径 B）
    python run_all.py --dry-run            # 只打印命令不执行，预览完整流程
    python run_all.py --hf-cache D:/hf_cache   # 覆盖 HF 缓存目录（默认 F:/hf_cache）

注意：训练耗时较长（M2 在 3060 6GB 上可能数小时），运行前确保显存充足。
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
DRY_RUN = False  # --dry-run 时只打印命令不执行

# ---------------- 可配置项 ----------------
MODEL_15B = "Qwen/Qwen2.5-1.5B-Instruct"      # M0 验证用
MODEL_3B = "Qwen/Qwen2.5-3B-Instruct"        # M2 主力
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "outputs"
DEFAULT_PAPERS = 100
GENERAL_RATIO = 0.2
HF_CACHE = "F:/hf_cache"                      # 默认 HF 缓存（F 盘）
# -----------------------------------------


def run(cmd):
    print("\n>>> " + " ".join(str(c) for c in cmd))
    if DRY_RUN:
        print("   [dry-run] 跳过执行")
        return
    r = subprocess.run([str(c) for c in cmd], cwd=str(ROOT))
    if r.returncode != 0:
        raise SystemExit(f"[fail] 命令失败（返回码 {r.returncode}）: {' '.join(map(str, cmd))}")


def _train_args(extra):
    """统一给训练命令追加 --hf-cache（若与默认不同）。"""
    if HF_CACHE and HF_CACHE != "F:/hf_cache":
        return extra + ["--hf-cache", HF_CACHE]
    return extra


def m0_verify():
    """M0：1.5B 小数据跑通整条 pipeline（验证脚本/格式无误）。"""
    print("\n===== M0: 1.5B 验证 =====")
    sample = DATA_DIR / "sample_m0.jsonl"
    run([PY, "data/build_dataset.py", "--max-papers", "30",
         "--out", str(sample), "--general-ratio", "0.2"])
    run(_train_args([PY, "train/train_lora.py",
         "--model", MODEL_15B, "--data", str(sample),
         "--out", str(OUT_DIR / "m0_verify"),
         "--epochs", "1", "--eval-ratio", "0"]))
    print("[M0] 验证完成：若上述训练顺利结束，说明数据格式与训练脚本无误。")


def m1_data(papers: int, manuscript: str, reviews: str):
    """M1：正文级 arXiv 抓取 + （可选）稿件转换 + （可选）审稿偏好 + 合并。"""
    print("\n===== M1: 数据构建 =====")
    full = DATA_DIR / "fulltext_cot_data.jsonl"
    run([PY, "data/build_dataset_fulltext.py",
         "--max-papers", str(papers), "--out", str(full),
         "--general-ratio", str(GENERAL_RATIO)])

    parts = [full]
    if manuscript:
        man = DATA_DIR / "manuscript_cot_data.jsonl"
        run([PY, "data/convert_manuscript.py",
             "--in", manuscript, "--out", str(man)])
        parts.append(man)
    if reviews:
        rev = DATA_DIR / "review_cot_data.jsonl"
        run([PY, "data/convert_reviews.py",
             "--in", reviews, "--out", str(rev)])
        parts.append(rev)

    merged = DATA_DIR / "training_all.jsonl"
    with merged.open("w", encoding="utf-8") as out:
        for p in parts:
            if p.exists():
                out.write(p.read_text(encoding="utf-8"))
    print(f"[M1] 训练集合并 -> {merged}")


def m2_train():
    """M2：3B 主力训练 + 合并导出。"""
    print("\n===== M2: 3B 训练 =====")
    merged = DATA_DIR / "training_all.jsonl"
    if not merged.exists() and not DRY_RUN:
        raise SystemExit(f"[fail] 未找到 {merged}，请先运行 M1。")
    run(_train_args([PY, "train/train_lora.py",
         "--model", MODEL_3B, "--data", str(merged),
         "--out", str(OUT_DIR / "qwen25-3b-tmlr"), "--merge"]))
    print("[M2] 训练完成，合并权重在 outputs/qwen25-3b-tmlr-merged")


def m3_eval():
    """M3：开放题生成回答（供人工/LLM 评分）。"""
    print("\n===== M3: 评估 =====")
    merged_model = OUT_DIR / "qwen25-3b-tmlr-merged"
    if not merged_model.exists() and not DRY_RUN:
        raise SystemExit(f"[fail] 未找到 {merged_model}，请先运行 M2。")
    run([PY, "eval/run_eval.py",
         "--questions", "eval/eval_questions.jsonl",
         "--model", str(merged_model), "--mode", "open"])
    print("[M3] 开放题回答已生成 open_answers.jsonl，请人工或外部 LLM 评分。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-m0", action="store_true")
    ap.add_argument("--skip-m1", action="store_true")
    ap.add_argument("--skip-m2", action="store_true")
    ap.add_argument("--skip-m3", action="store_true")
    ap.add_argument("--papers", type=int, default=DEFAULT_PAPERS)
    ap.add_argument("--manuscript", type=str, default="",
                    help="你的稿件路径(.tex/.md)，追加进训练集")
    ap.add_argument("--reviews", type=str, default="",
                    help="审稿语料路径(.jsonl)，追加'审稿偏好'样本进训练集（路径 B）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印将要执行的命令，不真正运行（预览完整流程）")
    ap.add_argument("--hf-cache", type=str, default="",
                    help="覆盖 HuggingFace 缓存目录（默认 F:/hf_cache），透传给训练脚本")
    args = ap.parse_args()

    global DRY_RUN, HF_CACHE
    DRY_RUN = args.dry_run
    if args.hf_cache:
        HF_CACHE = args.hf_cache

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if not args.skip_m0:
            m0_verify()
        if not args.skip_m1:
            m1_data(args.papers, args.manuscript, args.reviews)
        if not args.skip_m2:
            m2_train()
        if not args.skip_m3:
            m3_eval()
    except SystemExit as e:
        print(str(e))
        sys.exit(1)
    print("\n[done] 全流程结束。")


if __name__ == "__main__":
    main()
