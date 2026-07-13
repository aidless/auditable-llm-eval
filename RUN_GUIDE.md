# 全流程运行监控清单与预期输出（M0 → M3）

> 适用环境：本机已 `pip install -r requirements_win3060.txt` 且具备 NVIDIA GPU（RTX 3060 6GB）。
> 沙箱（无 GPU）只能跑 M1 数据腿与 M3 的 `eval_mc` 判分逻辑；**训练（M0/M2）与 M3 模型推理必须在 3060 上执行**。
> 编排入口：`run_all.py`。各阶段也可单独运行对应脚本（见下）。

---

## 0. 总览表

| 阶段 | 目标 | 是否需要 GPU | 关键产出文件 | 预计耗时（3060） |
|---|---|---|---|---|
| **M0** | 1.5B 跑通整条 pipeline（验证脚本/数据格式） | ✅ 是 | `data/sample_m0.jsonl`、`outputs/m0_verify/` | 数分钟 ~ 十余分 |
| **M1** | 构建 TMLR 领域训练数据（arXiv + 可选稿件） | ❌ 否 | `data/fulltext_cot_data.jsonl`、`data/training_all.jsonl` | 联网抓取数分钟（+合并瞬间） |
| **M2** | 3B 主力 LoRA 训练 + 合并导出 | ✅ 是 | `outputs/qwen25-3b-tmlr/`、`outputs/qwen25-3b-tmlr-merged/` | 数小时（取决于数据量与早停） |
| **M3** | 评估：生成回答（mc 自动判分 + 开放题待人工/LLM 评分） | ✅ 是 | `open_answers.jsonl`（200 条） | 推理数十分钟 |

---

## 1. 一键运行命令（按进度选用）

```bash
# ① 轻量验证（M0 数据+训练 + M1 数据），不进 M2/M3：先确认管道通顺
python run_all.py --skip-m2 --skip-m3 --papers 20

# ② 仅数据（M1）：先攒数据，训练稍后单独跑
python run_all.py --skip-m0 --skip-m2 --skip-m3 --papers 200 --manuscript "你的稿件.tex"

# ③ 全流程（含你的稿件）：M0→M1→M2→M3 依次执行
python run_all.py --papers 200 --manuscript "你的稿件.tex"

# ④ 带"审稿偏好"数据（路径 B）：在 ③ 基础上加 --reviews
python run_all.py --papers 200 --manuscript "你的稿件.tex" --reviews "review_corpus.jsonl"

# 预览完整命令但不执行：
python run_all.py --dry-run --papers 200 --manuscript "你的稿件.tex"
```

> 显存监控（训练时在**另一个终端**常开）：`nvidia-smi -l 1`

---

## 2. M0 — 1.5B 验证（绿灯检查）

**实际执行的子命令**（由 `run_all.py` 展开）：
```
python data/build_dataset.py --max-papers 30 --out data/sample_m0.jsonl --general-ratio 0.2
python train/train_lora.py --model Qwen/Qwen2.5-1.5B-Instruct --data data/sample_m0.jsonl \
       --out outputs/m0_verify --epochs 1 --eval-ratio 0
```

**预期控制台标记（按出现顺序）：**

| 顺序 | 来源 | 预期输出（关键字） | 说明 |
|---|---|---|---|
| 1 | build_dataset | `[info] 论文数: 30` | 抓取/读取 30 篇 |
| 2 | build_dataset | `[done] 生成 112 条训练样本 -> data/sample_m0.jsonl` | 30×3(A/B/C)=90 + 通用 22 ≈ 112 |
| 3 | train_lora | `[env] CUDA available: True` | 必须 True，否则 Fatal |
| 4 | train_lora | `[env] GPU: NVIDIA GeForce RTX 3060 \| 总显存 6.0GB \| 空闲 X.XGB` | 确认 3060 |
| 5 | train_lora | `[warn] 检测到显存 < 6.5GB，已按最小配置运行（batch=2, seq=2048）` | 3060 必然触发（见 M2 配置说明） |
| 6 | train_lora | `[load-start] GPU 已用 ...` → `[load-end]` | 4bit 加载模型 |
| 7 | train_lora | `[data] 训练 112 条 / 验证 0 条` | `--eval-ratio 0` 故无验证集 |
| 8 | train_lora | 每 10 步 `{'loss': ...}` 日志 | 1 epoch，1.5B 步数少 |
| 9 | train_lora | `[train-start]` → `[train-end]` | 训练完成 |
| 10 | train_lora | `[done] LoRA 已保存 -> outputs/m0_verify` | 适配器落地 |

**成功判据：** 进程退出码 0；`outputs/m0_verify/` 下出现 `adapter_config.json` 与 `adapter_model.safetensors`。
**失败信号：** 出现 `[fatal] 未检测到 CUDA` → 说明 torch 装错（非 CUDA 版）；或训练中途 CUDA OOM → 见末尾排错表。

---

## 3. M1 — 数据构建（无需 GPU）

**实际执行的子命令：**
```
python data/build_dataset_fulltext.py --max-papers 20 --out data/fulltext_cot_data.jsonl --general-ratio 0.2
# 若提供了 --manuscript：
python data/convert_manuscript.py --in 你的稿件.tex --out data/manuscript_cot_data.jsonl
# 若提供了 --reviews（路径 B：审稿偏好）：
python data/convert_reviews.py --in review_corpus.jsonl --out data/review_cot_data.jsonl
# 合并：
# （run_all 内部把上面产物拼接为 data/training_all.jsonl）
```

**预期控制台标记：**

| 来源 | 预期输出 | 说明 |
|---|---|---|
| build_dataset_fulltext | `[info] 论文数: 20` | |
| build_dataset_fulltext | `[info] 正文级成功 N / 降级为摘要 M` | **N 通常偏低**——arXiv 现网对多数论文返回 PDF 而非源码包，脚本自动降级为摘要，不崩溃 |
| build_dataset_fulltext | `[done] 正文级生成 K 条训练样本 -> data/fulltext_cot_data.jsonl` | K 取决于正文章节/公式密度，一般每篇 2–8 条 |
| convert_manuscript（可选） | `[done] 从 你的稿件.tex 生成 J 条稿件样本 -> data/manuscript_cot_data.jsonl` | J 取决于稿件章节/公式量 |
| convert_reviews（可选，路径 B） | `[done] 从 X 条语料生成 Y 条审稿偏好样本 -> data/review_cot_data.jsonl` | 仅当传 --reviews；X/Y 取决于真实语料 |
| run_all 合并 | `[M1] 训练集合并 -> data/training_all.jsonl` | 行数 ≈ K (+J) |

**成功判据：** `data/training_all.jsonl` 非空；每行是 `{"conversations":[{"role":"user",...},{"role":"assistant",...}]}`。
**重要提醒：** 若要**真正正文级**（公式/方法章节）而非摘要级，用 `--from-dir` 传入你在浏览器手动下载的源码目录：
```
python data/build_dataset_fulltext.py --from-dir ./papers_src --out data/fulltext_cot_data.jsonl --general-ratio 0.2
```
否则依赖 arXiv 实时抓取会大量降级为摘要，数据质量下降。

---

## 4. M2 — 3B 训练（重头戏，需要 GPU）

**实际执行的子命令（由 `run_all.py` 展开）：**
```
python train/train_lora.py --model Qwen/Qwen2.5-3B-Instruct \
       --data data/training_all.jsonl --out outputs/qwen25-3b-tmlr --merge
```

**预期控制台标记：**

| 顺序 | 预期输出 | 说明 |
|---|---|---|
| 1 | `[env] CUDA available: True` / GPU 信息 | |
| 2 | `[warn] 检测到显存 < 6.5GB...` | 默认安全档：batch=2 / seq=2048（详见 `M2_CONFIG_REVIEW.md`） |
| 3 | `[load-start] → [load-end]` | 4bit 加载 3B（约 2GB 权重） |
| 4 | `[data] 训练 X 条 / 验证 Y 条` | Y = 5% × X（默认 `eval-ratio=0.05`，启用早停） |
| 5 | 每 10 步 loss 日志；每 50 步 eval_loss | 有验证集才评估 |
| 6 | 可能打印 `Early stopping` | 连续 3 次 eval 无改善则停（patience=3） |
| 7 | `[train-start] → [train-end]` | |
| 8 | `[done] LoRA 已保存 -> outputs/qwen25-3b-tmlr` | 适配器 |
| 9 | `[done] 合并权重已导出 -> outputs/qwen25-3b-tmlr-merged（约 6GB fp16）` | 可用于推理/部署 |

**成功判据：** `outputs/qwen25-3b-tmlr-merged/` 含 `config.json` 与权重文件（`model.safetensors` 或 `pytorch_model.bin`）；`nvidia-smi` 峰值显存 < ~5.5GB（无 OOM）。
**监控要点：** 另开终端 `nvidia-smi -l 1` 盯峰值；loss 应稳步下降、eval_loss 不应反弹（反弹→降 lr，见 M2 配置说明）。

---

## 5. M3 — 评估（需要 GPU 做推理）

**步骤 A：生成全部 200 题回答（含 mc）**
```
python eval/run_eval.py --questions eval/eval_questions.jsonl \
       --model outputs/qwen25-3b-tmlr-merged --mode open
```
预期：`[open] 生成 200 条开放回答 -> open_answers.jsonl`（5 类 × 40 = 200 行；mc 类也会生成"复述正确陈述"的回答，供自动判分）。

**步骤 B：mc 自动判分**
```
python eval/run_eval.py --questions eval/eval_questions.jsonl --answers open_answers.jsonl --mode mc
```
预期：`[mc] 正确 X/40 = Y.YYY`（40 道 mc，自动比对正确陈述 + 排除错误项）。

**步骤 C：开放题人工/外部 LLM 评分**
derive / exp / code / paper 四类（160 道）无自动评分器，需人工或外部 LLM 依据 `reference` 字段判定。建议从每类抽 30 例盲评 base vs finetuned（见方案文档 §5.2）。

**成功判据：** `open_answers.jsonl` 恰好 200 行；mc 准确率打印。

---

## 6. 常见失败 → 处置表

| 阶段 | 现象 | 根因 | 处置 |
|---|---|---|---|
| 任意 | `未检测到 CUDA` / `torch.cuda.is_available()=False` | 装了 CPU 版 torch | 重装 `unsloth[windows-torch230]`（自带 CUDA torch），勿单独先装 torch |
| M0/M2 | CUDA OOM | 显存不足 | 已自动降 batch=2/seq=2048；仍 OOM 则手动 `--seq-len 2048 --batch 1`；或降 `lora_r` |
| M1 | `正文级成功 0 / 降级 20` | arXiv 现网返回 PDF | 改用 `--from-dir` 传入手动下载源码；或接受摘要级（质量降） |
| M1 | `arxiv` 报错 `results()` 缺参 / `download_source` 不存在 | arxiv 4.x 破坏性变更 | 已锁 `arxiv==1.4.2`（见 requirements）；勿升级 |
| M2 | eval_loss 早期反弹 | lr 偏高 / 过拟合 | 降 lr（5e-5→1e-5）；降 epoch；增大 `lora_dropout` |
| M2 | 训练慢（batch=2） | 3060 降档默认 | 见 M2 配置说明：显式 `--batch 4 --seq-len 4096` 可覆盖（自担 OOM） |
| M3 | `open_answers.jsonl` 只有 40 行（仅 mc） | 旧脚本跳过 mc | 已修复（run_eval.py 现对全题型生成）；重跑步骤 A |
| M3 | mc 准确率异常高/低 | 判分口径 | 当前口径：含正确陈述且不含错误项→对；如不符预期检查 `eval_questions.jsonl` 的 `answer`/`options` |

---

## 7. 输出文件清单（交付物核对）

```
data/sample_m0.jsonl              # M0 验证数据（~112 行）
data/fulltext_cot_data.jsonl      # M1 正文/摘要级数据
data/manuscript_cot_data.jsonl    # M1 你的稿件数据（--manuscript 时）
data/review_cot_data.jsonl        # M1 审稿偏好数据（--reviews 路径 B 时）
data/training_all.jsonl           # M1 合并训练集（M2 输入）
outputs/m0_verify/                # M0 1.5B 适配器
outputs/qwen25-3b-tmlr/           # M2 3B LoRA 适配器
outputs/qwen25-3b-tmlr-merged/    # M2 合并权重（推理用）
open_answers.jsonl                # M3 200 题回答
```

---
*本清单依据各脚本真实打印与产物生成，与 `run_all.py` / `train/train_lora.py` / `eval/run_eval.py` / `data/*.py` 当前实现一致。最后更新：2026-07-12。*
