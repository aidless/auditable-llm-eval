# Qwen2.5-3B-Instruct → TMLR 领域专家 微调方案

> 目标模型：`Qwen/Qwen2.5-3B-Instruct`
> 方法：`4bit 量化 + LoRA（PEFT）`
> 硬件约束：`RTX 3060 6GB`（单卡）
> 领域目标：TMLR 机器学习方向（论文理解 / 公式推导 / 实验设计 / 代码实现）
> 适用阶段：从 0 跑通 → 产出可用领域专家模型

---

## 0. 方案总览

| 维度 | 决策 |
|---|---|
| 基座 | Qwen2.5-3B-Instruct（中文友好、3B 容量、6GB 甜点区） |
| 微调范式 | LoRA（非全参），4bit NF4 量化 + 双量化 |
| 推理能力注入 | 训练数据采用 R1 风格 CoT 格式（显式推理链） |
| 训练工具 | Unsloth（首选，速度/显存最优）或 LLaMA-Factory（UI 备选） |
| 训练框架 | TRL `SFTTrainer` |
| 数据规模 | 5k–20k 条高质量领域样本 + 30% 通用防遗忘 |
| 训练时长 | 1.5B 验证 1–2 天；3B 主力 2–4 周（含数据构建） |

---

## 1. 环境准备

### 1.1 推荐运行时
使用隔离环境，避免污染系统 Python（参考托管 3.11 运行时）：

```bash
# 创建隔离 venv（使用托管 python）
python -m venv .venv
.venv\Scripts\activate

pip install --upgrade pip
```

### 1.2 核心依赖（6GB 关键）
```bash
pip install "unsloth[windows-torch230] @ git+https://github.com/unslothai/unsloth.git"
pip install "trl>=0.9" "transformers>=4.45" "datasets" "accelerate" \
            "bitsandbytes-windows" "peft" "sentencepiece" "numpy<2"
```

> **注意**：3060 为 Ampere 架构，CUDA 12.x + torch 2.3+ 最佳。若 `bitsandbytes` 在 Windows 上报错，改用 `bitsandbytes-windows` 预编译包。

---

## 2. 数据方案（决定成败的核心）

### 2.1 数据类型与配比

| 类型 | 内容 | 占比 | 示例 |
|---|---|---|---|
| A. 论文理解 | 摘要→方法→贡献提炼 | 25% | 给出 TMLR 论文段落，要求总结核心方法与创新点 |
| B. 公式推导 | step-by-step 数学推理 | 20% | 从 ELBO 推导到变分下界，要求显式每步 |
| C. 实验设计 | 假设→变量→评估指标 | 20% | 给定研究问题，设计对照实验与统计检验 |
| D. 代码实现 | PyTorch/Trainer 代码 | 15% | 实现特定损失函数 / 训练循环 |
| E. 通用防遗忘 | 通用对话 / 指令跟随 | 20% | 来自 ShareGPT / 中文指令数据 |

**配比原则**：领域(A–D) 合计 ~80%，通用(E) ~20%。通用比例过低会导致指令跟随退化。

### 2.2 数据来源建议

- **arXiv**：`cs.LG`, `cs.CL`, `cs.AI`, `stat.ML` 高频论文（用 `arxiv` 库，`build_dataset.py` 抓摘要级 / `build_dataset_fulltext.py` 抓正文级，详见 §2.2）。
- **TMLR / JMLR 开源论文**：方法章节 + 实验章节最适合做 A/C 类。
- **自身研究资产**：你已有的论文稿件、实验笔记、审稿意见——这是独特且高质量的数据（#47–51 投稿记录可直接转化为 A/B/C）。
- **合成数据**：用 GPT-4o/DeepSeek/Claude 按模板生成 B/D 类 CoT 样本（需人工抽查 10% 校验）。
- **通用**：`Belle`（中文指令）、`ShareGPT` 子集。

### 2.3 数据格式（R1 风格 CoT / ShareGPT）

统一为对话格式，强制推理链：

```json
{
  "conversations": [
    {
      "role": "user",
      "content": "请推导高斯分布下的最大似然估计参数，并说明每一步的依据。"
    },
    {
      "role": "assistant",
      "content": "我们来逐步推导。\n\n**步骤 1**：设样本 x_1...x_n 独立同分布于 N(μ, σ²)...\n\n**步骤 2**：写出对数似然函数 L(μ,σ²) = Σ log p(x_i|μ,σ²)...\n\n**步骤 3**：对 μ 求偏导并令为零... 得到 μ_MLE = x̄。\n\n**结论**：..."
    }
  ]
}
```

> **关键**：基座是 Instruct 模型，需用其 chat 模板（`tokenizer.apply_chat_template`）。若用 Unsloth，可直接喂 `conversations` 字段，无需手动拼模板。

### 2.4 审稿偏好数据来源与格式（可选的第二轮 LoRA · 路径 B）

§2.1–2.3 产出的是**作者侧领域理解**样本（提炼方法 / 复现实验 / 解释公式），让模型**懂内容**。若目标进一步是让模型**模仿你的审稿视角与评判偏好**（给定一篇稿，输出你会质疑什么、看重什么），需要额外一条"审稿偏好"数据轨——这是**独立于领域理解**的样本类型，不可由稿件正文自动派生。

**实现：** `data/convert_reviews.py`（生成器）+ `run_all.py --reviews`（编排接线）。默认关闭，仅当显式传 `--reviews` 时启用。

**输入格式（每行一条 JSON，两种其一）：**

```json
{"excerpt": "<论文片段原文>", "review": "<你对该片段的真实审稿意见>"}
{"principles": "<你最看重的审稿准则，如：重视消融/可复现/显著性检验>"}
```

- `excerpt+review`：针对具体片段的审稿式点评（推荐主力，最能刻画你的评判偏好）。
- `principles`：抽象审稿准则（作为偏好锚点，补充覆盖）。

**产出：** `data/review_cot_data.jsonl`（ShareGPT `conversations` 格式），由 `run_all.py` 并入 `training_all.jsonl`。

**语料来源（你的独特资产）：** #47–51 收到的 TMLR 审稿意见、你担任 PC/审稿人时的真实评语、个人偏好清单。

**关键纪律：**
- **不编造审稿观点**——`convert_reviews.py` 只做转格式+清洗截断，不生成评价内容；`review_corpus_TEMPLATE.jsonl` 仅为格式示例，**必须替换为真实语料**，否则模型会学到示例噪声。
- 审稿语料通常量小，第二轮建议降 `learning_rate`（易过拟合），或对新数据用**独立 LoRA 适配器**避免冲刷首轮领域能力。
- **落地顺序**：先路径 A 跑通 M0→M3 拿领域专家基线，基线达标后再用路径 B 做第二轮。详见 `M2_CONFIG_REVIEW.md` §3。

**启动命令：**
```bash
# ① 先看输入格式模板
python data/convert_reviews.py --make-template review_corpus_TEMPLATE.jsonl
# ② 用真实语料替换后，全流程带审稿偏好
python run_all.py --papers 200 --manuscript "你的稿件.tex" --reviews "review_corpus.jsonl"
```

---

## 3. 训练配置（6GB 专用）

### 3.1 量化与 LoRA 参数

| 参数 | 值 | 说明 |
|---|---|---|
| 量化 | `load_in_4bit=True`, `bnb_4bit_quant_type="nf4"` | 权重约 2GB |
| 双量化 | `bnb_4bit_use_double_quant=True` | 进一步省显存 |
| `max_seq_length` | 4096 | 3B 在 6GB 可承受 |
| LoRA `r` | 32 | 3B 用 32 足够，过大会过拟合 |
| LoRA `alpha` | 64 | alpha=2r 惯例 |
| LoRA `dropout` | 0.1 | 防过拟合 |
| `target_modules` | q/k/v/o_proj, gate/up/down_proj | 覆盖注意力+MLP |
| `bias` | "none" | 省参数 |
| `gradient_checkpointing` | "unsloth" | 必开，省显存 |
| 优化器 | `paged_adamw_8bit` | 防优化器 OOM |

### 3.2 训练超参

```python
training_args = {
    "per_device_train_batch_size": 4,      # 6GB 舒适值
    "gradient_accumulation_steps": 4,      # 等效 batch=16
    "warmup_ratio": 0.03,
    "num_train_epochs": 3,
    "learning_rate": 2e-4,                 # LoRA 常用 1e-4~3e-4
    "lr_scheduler_type": "cosine",
    "optim": "paged_adamw_8bit",
    "bf16": False,                         # 3060 不支持 bf16，用 fp16
    "fp16": True,
    "max_grad_norm": 0.3,
    "logging_steps": 10,
    "save_strategy": "epoch",
}
```

> **注（3060 实测，2026-07-12）**：`train_lora.py` 的 `env_check` 阈值为 6.5GB，RTX 3060（6.0GB）会进入 low 档并**默认降为 `batch=2 / seq=2048`**（安全优先，零 OOM 风险）。若 `nvidia-smi` 显示峰值显存 < 5.0GB，可显式 `--batch 4 --seq-len 4096` 覆盖以恢复"舒适区"吞吐；OOM 即回退。详见 `M2_CONFIG_REVIEW.md`。

---

## 4. 训练脚本（Unsloth 可运行骨架）

```python
from unsloth import FastLanguageModel
from trl import SFTTrainer
from transformers import TrainingArguments
from datasets import load_dataset
import torch

# ---------- 1. 加载 4bit 量化模型 ----------
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="Qwen/Qwen2.5-3B-Instruct",
    max_seq_length=4096,
    dtype=torch.float16,
    load_in_4bit=True,
)

# ---------- 2. 注入 LoRA ----------
model = FastLanguageModel.get_peft_model(
    model,
    r=32,
    lora_alpha=64,
    lora_dropout=0.1,
    target_modules=["q_proj","k_proj","v_proj","o_proj",
                    "gate_proj","up_proj","down_proj"],
    bias="none",
    use_gradient_checkpointing="unsloth",
)

# ---------- 3. 加载数据（ShareGPT 格式） ----------
dataset = load_dataset("json", data_files="tmlr_cot_data.jsonl", split="train")

# ---------- 4. 训练 ----------
trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",          # 或用 formatting_func 拼 conversations
    max_seq_length=4096,
    args=TrainingArguments(
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        warmup_ratio=0.03,
        num_train_epochs=3,
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        optim="paged_adamw_8bit",
        fp16=True,
        max_grad_norm=0.3,
        logging_steps=10,
        output_dir="outputs/qwen25-3b-tmlr-lora",
        save_strategy="epoch",
    ),
)
trainer.train()

# ---------- 5. 保存 LoRA 适配器 ----------
model.save_pretrained("outputs/qwen25-3b-tmlr-lora/final")
tokenizer.save_pretrained("outputs/qwen25-3b-tmlr-lora/final")
```

> **合并部署（推理时）**：
> ```python
> model.save_pretrained_merged("outputs/qwen25-3b-tmlr-merged",
>                              tokenizer, save_method="merged_16bit")
> ```
> 合并后约 6GB（fp16），可用 `vLLM` 或 `llama.cpp` 部署。

---

## 5. 评估方案

### 5.1 自动指标
- **Perplexity**：在领域测试集（held-out TMLR 段落）上对比 base vs finetuned。
- **领域 QA 准确率**：构造 200 道 ML 概念/推导题（选择题+简答），自动/半自动评分。

### 5.2 人工评估（重点）
从三类任务各抽 30 例，盲评 base vs finetuned：
- 论文贡献提炼准确度
- 公式推导步骤完整性（是否跳步）
- 实验设计合理性（变量控制、统计检验）

### 5.3 防退化检查
- **通用指令跟随**：用 50 条通用指令测，确保不退化。
- **灾难性遗忘**：对比 base 在通用 benchmark（如 C-Eval 子集）上的掉点。

---

## 6. 风险与缓解

| 风险 | 表现 | 缓解 |
|---|---|---|
| OOM | 训练崩溃 | `batch=2` + `grad_accum=8`；关闭 `fp16` 改 `bf16`（若支持）；降 `max_seq_length` 至 2048 |
| 灾难性遗忘 | 通用能力下降 | 通用数据保底 20%；降低 `num_epochs` 至 2 |
| 过拟合 | 训练 loss 降、验证 loss 升 | `lora_dropout=0.1`；早停；数据去重 |
| 数据噪声 | 输出出现幻觉公式 | 合成数据人工抽查 10%；剥离错误 CoT |
| 推理链退化 | 模型不输出思考过程 | 训练数据 100% 含 CoT；推理时 temperature=0.3 强制展开 |

---

## 7. 分阶段里程碑

```
M0（第 1–2 天）环境 + 1.5B 验证
  └─ 用 DeepSeek-R1-Distill-Qwen-1.5B 跑通脚本，验证数据加载/格式/训练不报错

M1（第 3–10 天）数据构建
  └─ 采集 + 标注 5k–10k 条 TMLR CoT 数据；人工抽查校正

M2（第 11–21 天）3B 主力训练
  └─ Qwen2.5-3B-Instruct + LoRA，3 epoch，监控 loss/显存

M3（第 22–28 天）评估 + 迭代
  └─ 自动 + 人工评估；按结果调数据配比 / 超参 / 数据量

M4（可选）合并部署
  └─ save_pretrained_merged → vLLM 本地服务
```

---

## 8. 后续：mHC 等架构改造的定位

当前 6GB 硬件**不支持** mHC 改造（需多卡预训练 + 百万级 token）。建议：
- 阶段内专注 3B LoRA，产出可用专家模型。
- mHC 作为**未来云端研究课题**预留，或等 DeepSeek 开源带 mHC 的小模型后直接做 LoRA。
- 若想做架构研究，优先在云端申请 A100 资源，并设计 baseline vs +mHC 对照实验（可转化为 TMLR 投稿）。

---

## 附录：关键命令速查

```bash
# 显存监控（训练时另开终端）
nvidia-smi -l 1

# 合并后转 GGUF（如需 llama.cpp 部署）
# 用 llama.cpp convert_hf_to_gguf.py 转换 merged 权重

# 推理测试
from transformers import pipeline
pipe = pipeline("text-generation", model="outputs/qwen25-3b-tmlr-merged",
                torch_dtype="auto", device_map="auto")
```

---

## 附录 B：GitHub 参考仓库（社区经验交叉验证）

以下公开仓库验证了本方案的技术路线，并据此调整了默认超参（详见 train/train_lora.py 注释）。

| 仓库 | 相关度 | 关键配置 | 借鉴点 |
|---|---|---|---|
| `amirhoseinnaderali-pixel/qwen-math-reasoning` | ★★★★★ | Qwen2.5-3B + Unsloth + CoT，r=8/α=16/batch=2/grad_accum=8/seq=1536/**lr=5e-6**/1epoch/早停 | 最接近场景（推理类）；**lr 显式降低防过拟合**；含 base vs finetuned 对比 |
| `Kethanvr/qwen-fine-tuning` | ★★★★ | Qwen2.5-Coder-3B QLoRA，r=16/α=16/batch=2/grad_accum=4/seq=2048/200steps | **70 条数据即可做领域专家**；40min/8GB 峰值；合成数据路线 |
| `Yudewei1112/Chinese-Medical-Data-Fine-tuning` | ★★★★ | Qwen2.5 中文医疗，r=16/α=16/全线性层/lr=2e-4/3epoch/seq=2048 | 中文领域适配；三方对比评估（原始/微调/base+LoRA） |
| `yxc20089/qwen-2.5-vl-7b-fine-tune-lora` | ★★★ | Qwen2.5-VL-7B，OOM 缓解清单（降 batch/seq/rank） | OOM 应对策略参考 |
| CSDN《Unsloth 微调 Qwen2.5-0.5B》 | ★★★ | 明确 6GB 3060 可行；HF 缓存重定向到非 C 盘 | 印证 6GB 可行；缓存重定向（与用户 C 盘管理习惯一致） |

### 据社区经验调整的默认值（已写入 train/train_lora.py）
1. **学习率**：`2e-4 → 1e-4`（推理类易过拟合；数学推理仓库用到 5e-6）。若 eval_loss 早期反弹，继续降到 5e-5/1e-5。
2. **epoch**：`3 → 2` + 早停（数据 <1万条时防记忆化）。
3. **早停**：新增 `EarlyStoppingCallback(patience=3)` + 5% 验证集切分 + `load_best_model_at_end`（取最优 checkpoint）。

### 关键共识（多仓库一致，印证方案无误）
- 框架统一 Unsloth + TRL + PEFT；量化统一 4bit + gradient_checkpointing。
- target_modules 统一 7 个线性层（q/k/v/o + gate/up/down）。
- 优化器统一 AdamW 8bit；推理类任务统一强制 CoT 格式。
- 评估统一采用 base vs finetuned 对比。

---
*2026-07-12 更新：补充 GitHub 参考仓库与据社区经验的超参调整（lr/epoch/早停）*
*文档生成：2026-07-12 | 模型选型确认：Qwen2.5-3B-Instruct（6GB 约束下最优解）*
