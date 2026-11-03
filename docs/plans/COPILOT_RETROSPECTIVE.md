# llm-lab-copilot：Prompt 优化 + 3B QLoRA 微调 —— 完整踩坑与执行纪实

> 记录周期：2026-07-12（部分延续至 07-13）
> 范围：`llm-lab-copilot` 评估平台的提示词迭代（v3.1→v3.2→v3.2.1）与 3B QLoRA 微调全流程
> 目的：把踩过的每一个坑、走过的每一步命令、以及得出的方法论沉淀成可复用的文档

---

## 0. 一句话结论

- Prompt 工程：**v3.2 填空模板 → 87.80%，是当前 7B 基线最佳**。
- 3B QLoRA 微调：**失败**。实测 68.29%，比 3B few-shot（82.11%）还低 14 分，根因是微调让模型在 YAML 行内列表后多打标点导致解析崩溃。
- 两条贯穿全程的纪律：**① 预测值不能当结果；② 警惕 live verdicts 的"假绿"**。

---

## 1. 项目背景

- **平台**：`llm-lab-copilot`（Agent OS 模型评估平台），权威代码路径
  `outputs/llm-lab`
- **评分系统**：`reference_checks`（YAML 任务定义里每条 prompt 带一组可程序化校验的检查项）；
  权威打分脚本 `scripts/score_copilot_run.py`（覆盖 ~80 类检查，依赖 `yaml` + `llm_lab.models`）。
- **演进目标**：先优化 prompt（zero-shot → few-shot）→ 再尝试用 3B QLoRA 微调 beats 7B v3.2 基线。

---

## 2. 评分演进时间线

| 阶段 | 方案 | 实测分（micro） | 备注 |
|---|---|---:|---|
| zero-shot | 基线 | 47.97% | 裸提示 |
| few-shot v1 | 首版示例 | 61.98% | |
| few-shot v2 | 优化示例 | 79.67% | |
| **v3** | 契约式提示 | **82.93%** | 修复 tamper bug 后的公平基线（旧 scorer 82.11%） |
| v3.1 | 三版合成 | 80.49% | ❌ 预测证伪，net −2.44pp |
| **v3.2** | 填空模板重构 | **87.80%** | ✅ 新最佳基线 |
| v3.2.1 | P1 修 Contract D | 86.18% | ❌ 净亏 2 checks |
| 3B 零样本 | — | 48.78% | 异数据集 test_50，仅参考 |
| 3B few-shot v3.2 | 同 7B 提示 | 82.11% | 3B 体量最佳 |
| **3B-LoRA-v2** | QLoRA 微调 | **68.29%** | ❌ 微调回退 |

> 注：所有"实测分"均来自 `score_copilot_run.py` 在统一数据集（`few_shot_v3.2.jsonl`，123 项检查）上的结果，口径一致。

---

## 3. Prompt 工程：踩坑与步骤

### 3.1 v3.1 合成 —— "预测不能当结果"

- 把 v1/v2/v3 三版取长补短合成 v3.1，并**预测**"report_summary 会回升、总分冲 85%"。
- **实测证伪**：v3.1 真跑 = 80.49%（99/123），比 v3 公平基线 82.93% 还低 2.44pp。
- 逐任务：eval_yaml 91→85、reviewer_qa 90→86、report_summary 59→59（无回升）、其余持平。
- **坑**：在 few-shot 共享前缀下，改任一 Contract 的词汇/概念/结构都会扩散污染其他任务
  （yaml_007 被 Contract B 的 bullet 清单牵引、reviewer_006 被 Contract E "traceable" 泄漏）。
- **纪律确立**：预测值不能当结果，必须先真跑、用真实 scorer 取分。

### 3.2 实证核实 —— "先找文件"

- 用户要求先核实数字是否真测出、文件是否真在磁盘。
- **坑**：用户之前只搜了 `F:\test\2026-07-11-...` 与 D:/F:/用户目录，漏了 `AppData`，误以为文件不存在。
- **事实**：所有交付物与 run 都在 `outputs\llm-lab`（见 §1 路径）。
- **修复**：scorer 的 `must_not_claim_tamper_proof` 原纯子串匹配、非否定感知，把"not a tamper-proof audit system"
  （正确否认）误判为违规。落地否定感知补丁 `TAMPER_PROOF_PHRASES` + `denied_before()`，重跑 v3 由 82.11%→82.93%。
- 产出验收脚本 `verify_copilot_run.py`（七项证据链校验：outputs 真实条数/非空、verdicts 对齐、真实 scorer 复现、
  tamper 审计、model/temp 钉死等）。

### 3.3 v3.2 填空模板重构 —— 成功

- 从 v3 派生，**只改 Contract B**：保留 v3 "Use exactly four sentences: 1./2./3./4." 编号结构作风格锚，
  每句从抽象→**填空模板 + 格式示例**（如 `example 'Status is partial, 15 outputs, ... total duration 29202 ms, local provider at...'`）。
  Contract E 完全不动。
- 实测 **87.80%（108/123，+4.88pp vs v3）**，report_summary 59→86%（+27pp），eval_yaml/reviewer_qa 零回归（零扩散成立）。
- **三条设计纪律**：① 风格锚不丢；② 零概念泄漏；③ 填空模板 > 事实清单。

### 3.4 v3.2.1 P1 修 —— 净亏

- 只改 Contract D（YAML 代码块），预期 88.62%。
- **实测 86.18%**，净亏 2 checks：Contract D 的 YAML 代码块与 eval_yaml 混淆，拖累 yaml_007/reviewer_006。
- **结论**：v3.2 仍为最佳，P1 未采纳。

---

## 4. 3B QLoRA 微调：环境灾难链（最重头）

目标基座 `Qwen/Qwen2.5-Coder-3B-Instruct`，在 **Windows + RTX 3060 6GB** 上做 4bit QLoRA。
以下按踩坑顺序记录，每一步都是真金白银耗掉的时间。

### 4.1 完整踩坑清单

| # | 现象 | 根因 | 解决 |
|---|---|---|---|
| 1 | `pip` 无法识别 | 激活的 venv 未在 PATH | 用 `python -m pip` 显式调用 |
| 2 | `NO GPU FOUND — aborting` | 装错 torch 2.5.1（CPU 版） | 指定 CUDA 版 |
| 3 | `module 'torch' has no attribute 'cuda'` | 又装成 CPU 版 torch | 重装 CUDA 版 |
| 4 | `torch.int1` 报错 | unsloth 需要 torch 2.10 | 但 2.10 只有 CPU wheel… |
| 5 | `ver: 2.10.0+cpu CUDA: False` | unsloth 把 torch 2.10 **CPU 版**覆盖进来 | `unsloth<2026` + `--no-cache-dir` 仍不稳 |
| 6 | `operator torchvision::nms does not exist` | triton 与 torch 版本冲突 | 放弃 unsloth/triton 链 |
| 7 | `transformers 5.x` 强制 `torchao` | transformers 升到 5.x | 降级 `transformers==4.48.3` |
| 8 | C 盘又满 | pip 默认 cache 在 C 盘 | `pip cache` 与 `HF_HOME` 全重定向到 F 盘 |
| 9 | `git clone` GitHub 被墙 | 网络限制 | 放弃本地 llama.cpp 转 GGUF |
| 10 | ollama 导入相对路径失败 | Modelfile `FROM` 需绝对路径 | 改为绝对路径 |
| 11 | merge 时 VRAM 不足 | 6GB 装不下 fp16 合并 | `device_map="cpu"` + `offload_folder` |
| 12 | eval v1 全失败（tensor 形状不兼容） | 4bit `merge_and_unload()` 产出畸形权重 | 改用 CPU 干净合并 |
| 13 | `No module named llm_lab` | 系统 python 无项目包 | 用 hermes venv（含 yaml+pydantic）跑 scorer |

### 4.2 最终可用环境

```
F:\train_env\  (venv)
  torch       2.6.0+cu124      # CUDA 版，关键！
  torchvision 0.21.0+cu124
  transformers 4.48.3
  trl         0.17
  peft / accelerate / bitsandbytes / datasets
  pip cache → F:\pip_cache
  HF_HOME    → F:\hf_cache
  offload    → F:\offload       # CPU merge 兜底
```

**核心决策**：彻底放弃 `unsloth`/`triton`/`torchao` 这套在 Windows 上相互拖后腿的组合，
改用**纯 `transformers` + `bitsandbytes`** 做 QLoRA，稳定跑通。

---

## 5. 3B QLoRA 微调：执行步骤（可复现）

> 所有命令在 `F:\test\2026-07-12-00-12-06` 下执行，用 `F:\train_env\Scripts\python.exe`。

### 5.1 数据准备

- 训练集：`train_seed_200.jsonl`（200 条 ShareGPT 格式 `{"instruction","input","output"}`）。
- 每条需对齐 v3.2 风格（填空模板），否则微调会学偏（见 §6.3）。

### 5.2 训练（`train_copilot_3b.py`）

```bat
:: 安装（已有 torch 2.6.0+cu124 可跳过第一步）
F:\train_env\Scripts\python.exe -m pip install torch==2.6.0+cu124 torchvision==0.21.0+cu124 --index-url https://download.pytorch.org/whl/cu124
F:\train_env\Scripts\python.exe -m pip install transformers trl peft accelerate bitsandbytes datasets

:: 跑训练
set HF_HOME=F:/hf_cache
F:\train_env\Scripts\python.exe train_copilot_3b.py
```

关键超参（脚本内常量）：

```python
MODEL_ID   = "Qwen/Qwen2.5-Coder-3B-Instruct"
EPOCHS     = 2
BATCH_SIZE = 2          # + GRAD_ACCUM=2 → 有效 batch 4（6GB 舒适）
SEQ_LEN    = 2048
LR         = 5e-5
LORA_R     = 16
LORA_ALPHA = 32
# 4bit NF4 + 双量化；target_modules 覆盖全部 7 个线性层
```

实测：train 190 / eval 10，loss 3.84→1.17，token acc 43%→75%，约 3 分 48 秒跑完。
产出 `outputs/copilot_3b_lora/adapter/`（LoRA 权重）+ `merged/`（4bit 合并，见 5.3 坑）。

### 5.3 合并与导出（4bit merge 坑 → CPU 干净 merge）

- **坑**：脚本内 `model.merge_and_unload()` 在 4bit 模型上合并，产出张量形状不兼容 → eval 全失败（§4.1 #12）。
- **解决**：`merge_clean.py` 用 CPU 加载 base(fp16) + adapter，干净合并后导出 safetensors：

```bat
F:\train_env\Scripts\python.exe merge_clean.py
:: 产出 outputs/copilot_3b_lora/merged_clean/（safe_serialization=True）
```

> `merge_clean.py` 要点：`device_map="cpu"`、`offload_folder="F:/offload"`（6GB 显存放不下 fp16 合并时兜底）。

### 5.4 ollama 导入（相对路径坑）

- **坑**：Modelfile `FROM` 写相对路径 → ollama 找不到模型。
- **解决**：`FROM` 用绝对路径。Modelfile_copilot2 内容：

```
FROM F:\test\2026-07-12-00-12-06\outputs\copilot_3b_lora\merged_clean
```

```bat
ollama create copilot-3b-lora-v2 -f Modelfile_copilot2
:: v1（copilot-3b-lora，4bit merged）因 tensor 不兼容全失败，已弃用
```

### 5.5 eval（v1 全失败 → v2 干净合并）

- eval 配置 `examples/copilot_eval_3b_lora.yaml`：model 指向 `copilot-3b-lora-v2`，provider ollama，
  `base_url: http://localhost:11434`，`temperature: 0`，dataset = `few_shot_v3.2.jsonl`（50 条）。
- 在评估平台触发 run（run id `20260712-233918-...`）。50/50 完成，0 provider error。

```bat
:: 平台内执行（示例）
python -m llm_lab run --config examples/copilot_eval_3b_lora.yaml
```

### 5.6 打分（llm_lab 缺失坑 + 假绿陷阱）

- **坑 A**：系统 `python` 跑 `score_copilot_run.py` 报 `No module named llm_lab` / `No module named yaml`。
  **解决**：用 hermes venv（含 yaml + pydantic + 可导入 llm_lab）。
- **坑 B（假绿）**：平台 `verdicts.jsonl` 显示 **49/50 = 100% pass**，但那只过结构性 verifier
  （non_empty / min_chars / max_chars）。真实 `reference_checks` 分仅 **68.29%**。
  **解决**：永远以 `score_copilot_run.py` 的分为准。

```bat
:: 用 python venv 跑权威打分
python ^
  scripts/score_copilot_run.py ^
  runs/20260712-233918-copilot_base_few_shot_v3.2_3b_lora_full ^
  --dataset examples/copilot_eval/few_shot_v3.2.jsonl
```

---

## 6. 结果与根因分析

### 6.1 同口径对比（统一数据集 / 123 检查 / 同一 scorer）

| 模型 | micro | macro | YAML 解析 | YAML schema |
|---|---:|---:|---:|---:|
| 3B few-shot v3.2 (run 152341) | **82.11%** | 82.40% | 35/50 | 8/50 |
| 7B v3.2 基线 (run 140642) | **87.80%** | 87.30% | 40/50 | 9/50 |
| **3B-LoRA-v2 (run 233918)** | **68.29%** | 72.32% | 27/50 | 1/50 |

- LoRA vs 3B few-shot：−13.8pp（micro）/ −10.1pp（macro）
- LoRA vs 7B v3.2：−19.5pp（micro）/ −15.0pp（macro）

### 6.2 分任务拆解

| 任务类型 | 3B few-shot | 3B-LoRA-v2 | 差值 |
|---|---:|---:|---:|
| eval_yaml_generation | 76.47% | **29.41%** | **−47.1** ⬇️ |
| failure_diagnosis | 88.46% | 84.62% | −3.8 |
| report_summary | 86.36% | 86.36% | 0.0 |
| reviewer_qa | 85.71% | 76.19% | −9.5 |
| verifier_design | 75.00% | **85.00%** | **+10.0** ⬆️ |

回退 100% 集中在 `eval_yaml_generation`；`verifier_design` 反而提升 → 微调"学到了东西"，但学歪了。

### 6.3 根因：YAML 标点退化（已核验输出）

`yaml_001` 等 23 条解析失败，典型：

```yaml
verifier:
  checks:
    any_keywords: ["trace", "log", "record", ...].   # ← 结尾多了个 .
```

YAML 中 flow sequence `[...]` 后跟 `.` 是语法错误，`yaml.safe_load` 直接抛异常 →
`must_parse_yaml` / `required_keys` / `min_models` 等一连串检查全挂。
解析失败统计（27/50）：16 个 block mapping 错 + 10 个 simple key 错 + 1 个 token 错。

**结论**：200 样本 + 2 epoch 的 QLoRA 覆盖了基座自带的合法 YAML 生成能力，转而输出带多余标点的退化格式。
这是灾难性遗忘/格式退化，**不是能力问题**。

---

## 7. 可复用纪律清单（Checklist）

1. **预测 ≠ 结果**：任何"预期分数/应该回升"都必须真跑 + 真实 scorer 验证后才算数。
2. **先找文件**：数字存疑时，先去权威路径（`outputs\llm-lab\runs\<run_id>\`）确认 run/verdicts/scores 真实存在。
3. **警惕假绿**：平台的 `verdicts.passed` 往往只过结构检查；权威分永远看 `reference_checks` scorer。
4. **同口径对比**：比较不同模型/方案，必须用同一数据集 + 同一 scorer + 同一检查集合。
5. **Windows 微调避坑**：别碰 `unsloth`/`triton`/`torchao` 组合，纯 `transformers`+`bitsandbytes` 最稳；
   torch 必须 CUDA 版（验 `torch.cuda.is_available()`）；pip/HF cache 重定向到数据盘。
6. **4bit merge 畸形**：训练后合并优先用 **CPU 干净合并**（`device_map="cpu"` + offload），别直接用 4bit `merge_and_unload()`。
7. **ollama 导入**：Modelfile `FROM` 用绝对路径。
8. **打分环境**：scorer 依赖 `yaml`+`pydantic`+`llm_lab`，挑一个装齐这些包的 python 跑。
9. **共享前缀污染**：few-shot 改任一 Contract 词汇/概念会扩散 → 小步改、逐任务验零回归。

---

## 8. 复现命令速查

```bat
:: 1) 训练
set HF_HOME=F:/hf_cache
F:\train_env\Scripts\python.exe train_copilot_3b.py

:: 2) 干净合并（CPU）
F:\train_env\Scripts\python.exe merge_clean.py

:: 3) ollama 导入（Modelfile 用绝对路径）
ollama create copilot-3b-lora-v2 -f Modelfile_copilot2

:: 4) eval（平台触发，或）
python -m llm_lab run --config examples/copilot_eval_3b_lora.yaml

:: 5) 权威打分（python venv，避开假绿）
python ^
  scripts/score_copilot_run.py ^
  runs/<run_id> --dataset examples/copilot_eval/few_shot_v3.2.jsonl

:: 6) 证据链验收（可选）
python verify_copilot_run.py <run_dir> <dataset> <scorer>
```

---

## 9. 结论与下一步

- **Prompt 侧**：v3.2 填空模板（87.80%）是当前 7B 最佳；3B few-shot（82.11%）是 3B 体量最佳。
- **微调侧**：本次 3B QLoRA **失败**（68.29%），根因 YAML 格式退化。
- 若仍要微调路线，按性价比排序：
  1. 修 `train_seed_200.jsonl` 的 YAML 格式（全过 `yaml.safe_load`），把 eval_yaml 类任务显式纳入训练集；
  2. 降 LoRA 侵入度（r=8/α=16、1 epoch、更低 lr）缓解灾难性遗忘；
  3. 资源允许则上 7B/14B QLoRA + few-shot 更可能 beats 87.80%。
- **当前最高优先级**：接受"3B few-shot 82.11% 为该体量 SOTA"，把微调当作未验证的高风险选项。

> 配套文档：`reports/copilot_prompt_v3.2_report.md`（prompt 最佳）、
> `reports/copilot_prompt_3b_lora_report.md`（微调实测）、`COPILOT_NEXT_STEPS.md`（方案与决策）。
