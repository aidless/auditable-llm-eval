# 完整执行计划：RTX 3060 (6GB) 微调 Qwen2.5-3B 为 TMLR 领域专家

> 本计划整合 `README.md` / `qwen25-3b-tmlr-finetune-plan.md` / `RUN_GUIDE.md` / `M2_CONFIG_REVIEW.md` / `TRAINING_TROUBLESHOOTING.md` 的决策与约束，给一份**端到端可照做**的路线图。
> 适用对象：你的 Windows + RTX 3060 6GB 机器。本环境（沙箱）无 GPU、未装训练依赖，故所有 **GPU 步骤只能在你机器上执行**；CPU 侧（数据生成/评测集/判分逻辑）已实跑验证通过。

---

## 0. 目标

用 QLoRA（4bit NF4 + 双量化 + LoRA）把 `Qwen/Qwen2.5-3B-Instruct` 微调成「懂机器学习/论文」的 TMLR 领域助手；可选**路径 B 第二轮**注入「审稿偏好」（需你提供真实审稿语料）。

成功标准：M2 合并权重可加载、对 `eval/eval_questions.jsonl` 的 mc 题正确率**明显高于基座**；开放题经人工/外部 LLM 评分显示领域能力提升。

---

## 1. 当前状态（已交付，待你执行 GPU 部分）

| 层 | 文件 | 状态 |
|---|---|---|
| 运行入口 | `README.md` | 就绪 |
| 环境 | `requirements_win3060.txt` | 就绪（unsloth 自带 CUDA torch + `arxiv==1.4.2` 锁版） |
| 方案 | `qwen25-3b-tmlr-finetune-plan.md`（含 §2.4 审稿偏好） | 就绪 |
| 运行监控 | `RUN_GUIDE.md`、`M2_CONFIG_REVIEW.md` | 就绪 |
| 排错 | `TRAINING_TROUBLESHOOTING.md` | 就绪 |
| 工程 | `data/*` 三件套 + `train/train_lora.py` + `eval/*` + `run_all.py` + `data/convert_reviews.py`（路径 B） | 就绪，CPU 侧已实测 |
| 技能包 | `low-vram-llm-finetune.zip`（11 条目，文档/脚本一致） | 就绪 |

**已验证（CPU）**：评测集 200 题、路径 B 回归、编排 dry-run、M3 判分器（40/40、39/40）、M1 抽象级 3 样本、M1 正文级 4 样本（含 `$$L(θ)=...$$` 公式抽取）。

---

## 2. 前置条件（你的 3060 机器）

- Windows + **RTX 3060 6GB** + 已装 **CUDA 12.x 驱动**。
- 磁盘：**F 盘优先留 ≥30GB**（C 盘已爆满，HF/arxiv 缓存已默认指向 F 盘，切勿改回 C）。
- Python **3.11+**（脚本在 3.13 管理版验证过）。
- 联网（首次需下载基座权重与 arXiv 数据；arXiv 实时正文级源码端点可能被服务端降级为 PDF → 降级摘要）。

---

## 3. 阶段 0：装环境（约 10–20 分钟）

```bash
cd <项目目录>
pip install -r requirements_win3060.txt
python -c "import torch, unsloth; print('cuda ok:', torch.cuda.is_available())"
```

- 预期：`cuda ok: True`。
- **注意**：**不要先单独 `pip install torch`**——`unsloth[windows-torch230]` 自带匹配 CUDA 的 torch，单独装会版本错配。
- HF 缓存默认 `F:/hf_cache`；arXiv 源码包默认 `F:/arxiv_src`（均避开 C 盘）。

---

## 4. 阶段 1：M0 + M1 轻量验证（约 20–40 分钟，含 1.5B 训练冒烟）

```bash
python run_all.py --skip-m2 --skip-m3 --papers 20
```

- **M0**：30 篇 → `data/sample_m0.jsonl`，随后 1.5B 训练 1 epoch（冒烟，验证脚本/格式/训练链路）。
- **M1**：抓 20 篇 → `data/fulltext_cot_data.jsonl`（部分可能降级为摘要）+ 合并 `data/training_all.jsonl`。
- **预期产出**：`data/training_all.jsonl` 非空；M0 训练 loss 下降；无 CUDA OOM。
- **成功判据**：流程跑完退出码 0，且 `data/training_all.jsonl` 存在且行数 > 0。
- **风险/回退**：
  - arXiv 源码端点返回 PDF → 部分论文降级为摘要（**可接受**，或用 `build_dataset_fulltext.py --from-dir` 手动放入浏览器下载的源码包拿正文级）。
  - 若 M0 意外 OOM（1.5B 4bit 极小，正常不会）→ 降 `--seq-len 1024`。

---

## 5. 阶段 2：M2 主力训练（数小时）

先跑纯领域基线（不带稿件/审稿），确认链路：

```bash
python run_all.py --skip-m0 --skip-m1 --skip-m3 --papers 200
```

若要把你自己的稿件也并进训练集：

```bash
python run_all.py --skip-m0 --skip-m1 --skip-m3 --papers 200 --manuscript "你的稿件.tex"
```

- **VRAM 档（关键）**：
  - 3060 自动进入 **low 档** → 默认 `batch=2 / seq=2048`，峰值 ~4.5GB，**安全**。
  - 仅当你 `nvidia-smi -l 1` 观测到峰值 **< 5.0GB 且稳定**时，才进阶：`--batch 4 --seq-len 4096`（峰值 ~5.5GB）。
  - **显式传 `--batch`/`--seq-len` 会覆盖 low 档默认**；不传则保留安全默认。
- **预期产出**：`outputs/qwen25-3b-tmlr-merged/`（合并权重）；训练日志显示 eval_loss 收敛后早停（patience=3）。
- **成功判据**：合并目录存在；loss 合理下降；全程无 OOM。
- **风险/OOM**：见 `TRAINING_TROUBLESHOOTING.md`（9 类故障处置表 + 升档降档决策树）。

---

## 6. 阶段 3：M3 评估（约 10–30 分钟）

```bash
python run_all.py --skip-m0 --skip-m1 --skip-m2
```

- 对 `eval/eval_questions.jsonl` 的 200 题生成 `open_answers.jsonl`（mc 题模型复述正确陈述，供 `eval_mc` 判分）。
- **判分（mc 自动）**：

```bash
python eval/run_eval.py --questions eval/eval_questions.jsonl --answers open_answers.jsonl --mode mc
```

- **开放题（derive/exp/code/paper）**：无自动分，需**人工或外部 LLM** 评分。
- **成功判据**：mc 正确率明显高于基座（说明学到领域知识）；开放题评分显示能力提升。

---

## 7. 阶段 4（可选）：路径 B 第二轮「审稿偏好」LoRA

**前提**：你提供**真实审稿语料**（#47–51 收到的 TMLR 审稿意见 + 你当 PC/审稿人时的真实评语 + 偏好清单如「重视消融/可复现/显著性检验」）。**切勿直接拿 `review_corpus_TEMPLATE.jsonl` 当训练语料**（那是示例噪声）。

步骤：

1. 整理语料为 `review_corpus.jsonl`，格式见模板：
   ```bash
   python data/convert_reviews.py --make-template review_corpus.jsonl
   ```
   每条：`{"excerpt":"<论文片段原文>","review":"<你的真实审稿意见>"}` 或 `{"principles":"<你最看重的审稿准则>"}`。
2. 第二轮训练（在领域基线之上叠加审稿偏好）：
   ```bash
   python run_all.py --papers 200 --manuscript "你的稿件.tex" --reviews "review_corpus.jsonl"
   ```
   - **建议**：审稿语料通常较少 → 降 `learning_rate`（1e-4 → 5e-5）或用**独立 LoRA 适配器**，避免冲刷第一轮领域能力；保留 ≥20% 通用数据防遗忘。
3. **成功判据**：模型能输出符合你审稿偏好的、真实的审稿式点评。

---

## 8. 完整命令序列（可照搬）

```bash
# 阶段 0
pip install -r requirements_win3060.txt
python -c "import torch, unsloth; print(torch.cuda.is_available())"

# 阶段 1（轻量验证）
python run_all.py --skip-m2 --skip-m3 --papers 20

# 阶段 2（主力训练；可加 --manuscript）
python run_all.py --skip-m0 --skip-m1 --skip-m3 --papers 200

# 阶段 3（评估 + 判分）
python run_all.py --skip-m0 --skip-m1 --skip-m2
python eval/run_eval.py --questions eval/eval_questions.jsonl --answers open_answers.jsonl --mode mc

# 阶段 4（可选，路径 B；先备好 review_corpus.jsonl）
python run_all.py --papers 200 --manuscript "你的稿件.tex" --reviews "review_corpus.jsonl"
```

> 也可一条跑全：直接 `python run_all.py --papers 200`（M0→M3 全自动），但分阶段便于中途排查。

---

## 9. 时间估算

| 阶段 | 耗时 | 说明 |
|---|---|---|
| 0 装环境 | 10–20 min | 下载 unsloth/torch 等 |
| 1 M0+M1 验证 | 20–40 min | M0 训 1.5B 约几分钟 |
| 2 M2 训练 | 2–6 h | 取决于 papers 数 / seq_len / batch |
| 3 M3 评估 | 10–30 min | 推理 200 题 |
| 4 路径 B | 1–3 h + 你整理语料时间 | 第二轮 LoRA |

---

## 10. 关键约束速记（务必遵守）

- **3060 low 档自动降 `batch=2/seq=2048`**；显式传参可覆盖，但需先确认显存有余（峰值 < 5.0GB）。
- **arXiv 实时正文级可能降级为摘要**（服务端把源码端点改返回 PDF，与 arxiv 版本无关）→ 要稳定正文级用 `--from-dir` 手动放源码包。
- **C 盘爆满** → HF/arxiv 缓存已默认 F 盘，勿改回 C。
- **勿单独先装 torch**（unsloth 自带）。
- 训练需 GPU；M1 数据生成 / M3 判分逻辑 CPU 侧已验证通过。

> **执行中修正（2026-07-12）**：原计划/依赖锁 `arxiv==1.4.2`，实跑发现其查询端点用 `http://`，arXiv 现返回 **HTTP 301** 强制 https，旧客户端不跟随 → M1 抓取失败。已改锁 `arxiv==4.0.0`（走 https，可正常抓取；代码已兼容 4.x API 变更）。详见 `requirements_win3060.txt` 注释。

---

## 11. 风险与回退总表

详见 `TRAINING_TROUBLESHOOTING.md`（阶段定位表 + 显存预算 + 9 类故障处置 + 升档降档决策树 + 监控命令 + 路径 B 专属注意 + 紧急最小可跑配置）。

---

## 12. 需要你确认/提供的决策点

1. **数据规模**：先用 `--papers 20` 轻量验证，还是直接 `--papers 200` 主力训练？
2. **是否第一轮就带稿件**（`--manuscript`）？
3. **路径 B 真实审稿语料**何时提供？（#47–51 审稿意见 / PC 评语 / 偏好清单）
4. 训练期间是否需要我**预写一份运行日志模板**帮你记录每阶段实际耗时与显存峰值？

---

> 边界重申：本计划中的 GPU 步骤（阶段 0/1 的 M0 训练、阶段 2、阶段 3 模型推理）**只能在你 3060 上执行**；我可继续在沙箱里帮你做文档、排错速查、脚本静态检查，或在你贴回报错时诊断。
