# Qwen2.5-3B TMLR 领域专家微调工程（RTX 3060 6GB 专用）

[![release-validate](https://github.com/aidless/auditable-llm-eval/actions/workflows/release.yml/badge.svg)](https://github.com/aidless/auditable-llm-eval/actions/workflows/release.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python ≥ 3.10](https://img.shields.io/badge/python-≥3.10-blue.svg)]()
[![No GPU for CI](https://img.shields.io/badge/CI-no%20GPU%20needed-success.svg)](./.github/workflows/README.md)

> **TL;DR.** This repo is an auditable LLM evaluation pipeline (10 programmatic `reference_checks`, including *cognitive-honesty* dimensions) that catches false-green verdicts. Two committed runs reproduce in one command: naive verdicts **100% green**, authoritative scorer **69.00%** and **67.00%** — a 30-point deception zone, falsifiable by any reader. Full story: [docs/blog/001](./outputs/llm-lab/docs/blog/001-auditable-llm-eval-no-green-lights.md). 中文小白指南: [docs/GETTING_STARTED.md](./outputs/llm-lab/docs/GETTING_STARTED.md).

在 **RTX 3060 6GB**（Ampere / CUDA 12.x / Windows）上，用 **LoRA + 4bit 量化（QLoRA）** 把 `Qwen/Qwen2.5-3B-Instruct` 微调成 **TMLR 机器学习领域专家** 的完整可运行工程，并支持可选的 **"审稿偏好"第二轮 LoRA**（路径 B）。

全流程分四阶段，由 `run_all.py` 一键编排：

| 阶段 | 作用 | 是否需要 GPU |
|---|---|---|
| **M0** | 1.5B 跑通整条 pipeline（验证脚本/数据格式） | ✅ |
| **M1** | 构建领域训练数据（arXiv 抽象级 / 正文级 / 可选稿件 / 可选审稿偏好） | ❌ |
| **M2** | 3B 主力 LoRA 训练 + 合并导出 | ✅ |
| **M3** | 评估：生成回答（mc 自动判分 + 开放题待人工/LLM 评分） | ✅ |

> 沙箱/无 GPU 环境只能跑 M1 数据腿与 M3 的 `eval_mc` 判分逻辑；**训练（M0/M2）与 M3 模型推理必须在 3060 上执行**。

---

## 1. 硬件与系统要求

- **GPU**：NVIDIA RTX 3060 6GB（Ampere，CUDA 12.x）。7B 在 6GB 上仅 batch=1/seq≤1536 且 OOM 风险高，不建议本地起步。
- **OS**：Windows（本工程针对 Windows 调优；包名/路径为 win 适配，Linux 可改后运行）。
- **Python**：3.11 或 3.12（unsloth 的 `windows-torch230` 自带 CUDA 12.1 torch，勿单独先装 torch）。
- **磁盘**：3B 合并导出约 6GB（fp16）；HF 缓存与 arXiv 源码默认重定向到 **F 盘**（`F:/hf_cache`、`F:/arxiv_src`），不占 C 盘。

---

## 2. 一步安装环境

```bash
pip install -r requirements_win3060.txt
```

- `unsloth[windows-torch230]` 会拉入**兼容的 CUDA 12.1 torch**——**先装它，再也不要单独 `pip install torch`**，否则易出现 torch/CUDA 版本错配。
- `arxiv==1.4.2` 已锁版（规避 arxiv 4.x 破坏性变更；但 arXiv 服务端现网对正文级源码的 PDF 降级无法靠锁版本解决，见 §6）。

---

## 3. 目录结构

```
.
├── README.md                       # 本文件
├── requirements_win3060.txt        # 3060 Windows 训练环境依赖
├── qwen25-3b-tmlr-finetune-plan.md # 方案文档（含 §2.4 审稿偏好数据来源与格式）
├── RUN_GUIDE.md                    # M0→M3 运行监控清单 + 预期输出表格
├── M2_CONFIG_REVIEW.md             # M2 超参审计 + "审稿偏好"路径定位
├── run_all.py                      # M0→M3 一键编排器
├── data/
│   ├── build_dataset.py            # arXiv 抽象级抓取 + 通用混入
│   ├── build_dataset_fulltext.py   # arXiv 正文级解析（.tex），支持 --from-dir 离线
│   ├── convert_manuscript.py       # 你的稿件 .tex/.md → 样本 + LaTeX 公式抽取
│   ├── convert_reviews.py          # 【路径 B】审稿偏好数据生成器
│   ├── cot_templates.py            # 5 类 CoT 模板
│   ├── review_corpus_TEMPLATE.jsonl# 审稿语料输入格式示例（需替换为真实语料）
│   ├── sample_m0.jsonl / sample_fulltext.jsonl  # M0 验证数据（示例产物）
│   └── training_all.jsonl          # M1 合并训练集（M2 输入，运行后生成）
├── train/
│   └── train_lora.py               # Unsloth QLoRA 训练器（env-check/GPU监控/早停/合并）
├── eval/
│   ├── build_eval_set.py           # 生成 200 题评估集
│   ├── run_eval.py                 # mc 自动判分 + 开放题回答生成
│   └── eval_questions.jsonl        # 评估题库（200 题，示例产物）
└── outputs/
    └── llm-lab/
        └── docs/
            ├── adr/                # 架构决策记录（0001–0004 + README 索引）
            └── blog/               # 方法论博客（001-auditable-llm-eval-no-green-lights.md）
    # 训练产物（m0_verify / qwen25-3b-tmlr / copilot_3b_lora_v3c 等 -merged）
```

---

## 4. 运行（在 3060 机器上）

```bash
# ① 轻量验证（不训练，先确认数据管道通畅）
python run_all.py --skip-m2 --skip-m3 --papers 20

# ② 仅攒数据（不训练）
python run_all.py --skip-m0 --skip-m2 --skip-m3 --papers 200 --manuscript "你的稿件.tex"

# ③ 全流程（含你的稿件）
python run_all.py --papers 200 --manuscript "你的稿件.tex"

# ④ 带"审稿偏好"数据（路径 B，见 §5）
python run_all.py --papers 200 --manuscript "你的稿件.tex" --reviews "review_corpus.jsonl"

# 预览完整命令但不执行：
python run_all.py --dry-run --papers 200 --manuscript "你的稿件.tex"
```

> 训练时在**另一个终端**常开显存监控：`nvidia-smi -l 1`。

各阶段也可单独运行对应脚本，详见 `RUN_GUIDE.md`。

---

## 5. 数据轨说明（M1）

M1 把以下数据轨合并为 `data/training_all.jsonl`：

| 轨 | 脚本 | 说明 |
|---|---|---|
| 抽象级 | `build_dataset.py` | arXiv 摘要 → CoT 样本（联网抓取） |
| 正文级（推荐） | `build_dataset_fulltext.py` | 下载源码包解析 `.tex`；**建议 `--from-dir` 传手动下载的源码包** |
| 你的稿件 | `convert_manuscript.py` | 稿件 `.tex`/`.md` → 方法/实验/公式理解样本（`--manuscript`） |
| **审稿偏好（路径 B）** | `convert_reviews.py` | 你的真实审稿语料 → 审稿视角样本（`--reviews`，默认关闭） |

**路径 B 用法：**
```bash
# 先看输入格式模板
python data/convert_reviews.py --make-template review_corpus_TEMPLATE.jsonl
# 用真实语料替换后，全流程带审稿偏好
python run_all.py --papers 200 --manuscript "你的稿件.tex" --reviews "review_corpus.jsonl"
```
- 输入每行一种：`{"excerpt":"<论文片段原文>","review":"<你对该片段的真实审稿意见>"}` 或 `{"principles":"<你最看重的审稿准则>"}`。
- `convert_reviews.py` **只做转格式+清洗截断，不编造审稿观点**。模板仅为格式示例，**必须替换为真实语料**，否则模型会学到示例噪声。

---

## 6. 关键约束与坑（必读）

1. **3060 必进 low 档**：`train_lora.py` 的 `env_check` 阈值 `6.5GB`，RTX 3060（6.0GB）**任何运行都会默认降为 `batch=2 / seq=2048`**（安全优先，零 OOM）。确认 `nvidia-smi` 峰值 < 5.0GB 后，可显式 `--batch 4 --seq-len 4096` 覆盖以恢复"舒适区"吞吐；OOM 即回退。
2. **arXiv 正文级会降级为摘要**：arXiv 服务端现网对 `/e-print/`、`/src/` 返回 PDF（非源码包），live 抓取大量降级。**要稳定正文级，用 `--from-dir` 传入浏览器手动下载的源码 tarball**。脚本打印 `正文级成功 N / 降级为摘要 M`。
3. **C 盘重定向已写死默认**：HF 缓存 `F:/hf_cache`、arXiv 源码 `F:/arxiv_src`，不占 C 盘（治本策略）。
4. **不要单独先装 torch**：让 `unsloth[windows-torch230]` 决定 torch/CUDA 版本。
5. **训练需 GPU**：M0/M2 训练与 M3 模型推理必须在 3060 执行；M1 数据腿与 `eval_mc` 判分可在任意环境。

---

## 7. 审稿偏好数据收集清单（路径 B 用，需你提供）

`convert_reviews.py` 不会替你写评语。整理以下真实资产，按 §5 格式存成 `review_corpus.jsonl`：

- [ ] **#47–51 收到的 TMLR 审稿意见**：你论文被审时，审稿人对你工作的具体质疑 / 肯定点。
- [ ] **你担任 PC / 审稿人时的真实评语**：你给别人的稿件的审稿意见（最贴近"你的偏好"）。
- [ ] **偏好清单**：你最看重的审稿维度，如「重视消融实验 / 可复现性 / 显著性检验 / 数据量充分性 / 与 SOTA 的公平对比」。
- [ ] **反面样本（可选）**：你最反感的、认为"不够扎实"的写法，作为 `principles` 的负面锚点。

整理提示：每条尽量绑定一段**具体论文片段**（`excerpt`）+ **你对其的真实点评**（`review`），比纯原则更有判别力。

---

## 8. 与技能包的关系

`low-vram-llm-finetune.zip` 是本工作流的**固化技能包**（`SKILL.md` + `references/finetune_playbook.md` + `scripts/`，用户级技能位于 `~/.workbuddy/skills/low-vram-llm-finetune/`）。它描述"如何在低显存 GPU 上做领域专家微调"的通用方法，可复用于其他项目；**本目录是该方法在 `F:/test` 的一次具体实例化**（含你的方案与运行产物）。两者脚本一致：修改技能需同步回技能目录并重建 zip。

---

## 9. 参考文档

- `qwen25-3b-tmlr-finetune-plan.md` — 完整方案（环境/数据/训练/评估/里程碑/风险）
- `RUN_GUIDE.md` — M0→M3 运行监控清单、预期控制台输出、失败处置表
- `M2_CONFIG_REVIEW.md` — M2 超参审计 + "审稿偏好"三条路径（A 基线 / B 数据轨 / C 换模板）定位
- `TRAINING_TROUBLESHOOTING.md` — 3060 训练排错速查（显存预算 / OOM 处置 / 升档降档决策树 / 监控命令）

---

## 10. 可审计评测平台文档（llm-lab-copilot）

本项目用 `llm-lab-copilot` 评测平台对微调模型做**可审计**评估——其核心纪律是"绿灯只是邀请函，不是毕业证书"。以下文档记录该平台的设计决策与实证经过（位于 `outputs/llm-lab/docs/`）：

> 子项目独立门户：[`outputs/llm-lab/README.md`](outputs/llm-lab/README.md)（文档导航 + 实证分数链首页，便于单独发布 `llm-lab/`）
> 完整过程报告（开源用）：[`outputs/llm-lab/REPORT.md`](outputs/llm-lab/REPORT.md)（中英双语：假绿捕获→根因→v3c 修复→复现→开源说明）
> 经验文档：[`outputs/llm-lab/docs/LESSONS.md`](outputs/llm-lab/docs/LESSONS.md)（可审计评测五条纪律，中英双语）

**架构决策记录（ADR）**
- [`docs/adr/README.md`](outputs/llm-lab/docs/adr/README.md) — 索引（四条决策一句话概览 + "map≠territory" 声明）
- [`docs/adr/0001-content-hashing-evidence.md`](outputs/llm-lab/docs/adr/0001-content-hashing-evidence.md) — 证据 sha256（tamper-perceiving 非防篡改）
- [`docs/adr/0002-sequential-synchronous-runner.md`](outputs/llm-lab/docs/adr/0002-sequential-synchronous-runner.md) — 顺序同步 runner（证据一致性 > 吞吐）
- [`docs/adr/0003-local-jsonl-audit-trail.md`](outputs/llm-lab/docs/adr/0003-local-jsonl-audit-trail.md) — 本地 JSONL 审计（否 Langfuse）
- [`docs/adr/0004-verifier-is-not-scorer.md`](outputs/llm-lab/docs/adr/0004-verifier-is-not-scorer.md) — verifier≠scorer（以 31/31 假绿 vs 7.59% 为活标本）

**方法论博客**
- [`docs/blog/001-auditable-llm-eval-no-green-lights.md`](outputs/llm-lab/docs/blog/001-auditable-llm-eval-no-green-lights.md) — *Auditable LLM Eval: No Green Lights*（HN 向；以 v3 假绿→v3c 77.69% 修复验证为实证链）

**实证数据权威源**
- `COPILOT_RETROSPECTIVE.md` — 评测平台复盘（分数链至 v2）
- `COPILOT_NEXT_STEPS.md` — 评测修复路线图

---

*工程状态（2026-07-13）：M0/M2 训练产物 `outputs/copilot_3b_lora_v3c`（QLoRA 4bit）已合并导出并接入评测；评测实证链见 §10（v3 假绿 7.59% → 二分锁定低侵入超参 → v3c 修复 77.69%）。本 README 引用的 `outputs/llm-lab/docs/` 文档为**本轮会话重建落盘**（此前因会话断连丢失），均以真实代码理念与评测数据为依据。*
