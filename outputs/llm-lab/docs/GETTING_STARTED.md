# 新手指南：从零跑通「可审计 LLM 评测」（小白版）

> 这份指南假设你是**完全的小白**：没碰过命令行、没训过模型也没关系。照着复制命令一步步做就行。
> 如果你已经会 Python / 会用 Ollama，可以直接跳到 [§2.5](#25-跑评测评测入口) 或看仓库根 `README.md`。

---

## 0. 这个仓库到底能让你做什么

一句话：**拿一个本地大模型，跑一套"它会不会自己骗自己"的评测。**

我们做了一件反直觉的事：很多评测平台告诉你"100% 通过 ✅"，但其实模型答得很烂。我们把这种"假绿"现象做成了一个**可以复现的标本**——你跑完会亲眼看到：

- **naive 实时验证器**说：100% 通过（全绿 ✅）
- **权威评分器**说：只有约 **67%–69%** 真通过

这个落差，就是本项目的全部意义。

你有两种玩法：

| 路径 | 需要什么 | 耗时 | 你能得到 |
|---|---|---|---|
| **A. 快速体验**（推荐先走） | 任意电脑 + Python + Ollama | 5 分钟 | 用你自己的模型跑出"假绿"证据 |
| **B. 完整复现**（需显卡） | NVIDIA GPU + 训练依赖 + 训练数据 | 数小时 | 从零训练 LoRA → 合并 → 导入 → 复现论文里的 69%/67% |

> 💡 评测相关的三个脚本（`eval/run_copilot_eval.py`、`verify_copilot_run.py`、`copilot/score_copilot_run_v2.py`）**只用到 Python 自带的功能，不需要 `pip install` 任何东西**。所以路径 A 极度友好。

---

## 1. 你需要准备什么

### 路径 A（快速体验）只需：
1. 一台电脑（Windows / macOS / Linux 都行）
2. **Python 3.8 或更高**（系统自带或官网下载均可）
3. **Ollama**（一个在本机跑大模型的工具）+ 任意一个模型（比如 `qwen2.5:3b`）

### 路径 B（完整训练）额外需要：
1. **NVIDIA 显卡**（本项目在 RTX 3060 6GB 上验证可行；其他 6GB+ 显卡通常也行）
2. **Python 3.10–3.12**（训练依赖对 3.13 支持不全，请用 3.12 或 3.11）
3. 训练依赖（`requirements_win3060.txt`）
4. 训练数据文件 `train_seed_200_aug.jsonl`（约 100KB）——**注意：此文件未纳入 git 仓库**（体积/版权原因），训练前需自备或向作者索取

---

## 2. 路径 A：快速体验（5 分钟，不用显卡、不用训练）

### 2.0 一分钟最小验证（连 Ollama 都不用装！）

仓库里已经附带了**真实跑过的评测结果**（`runs/` 目录）。你甚至可以先不装任何大模型，直接用校验器证明"69% 是从磁盘真实算出来的，不是写死的"：

```bat
cd 仓库根目录
python verify_copilot_run.py ^
  --run-dir outputs/llm-lab/datasets/llm_lab_copilot/runs/20260713-211540-copilot-3b-lora-v3c ^
  --dataset outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl ^
  --scorer  copilot/score_copilot_run_v2.py
```

> macOS / Linux 把 `^` 换行符去掉，写成一行：
> ```bash
> python verify_copilot_run.py --run-dir outputs/llm-lab/datasets/llm_lab_copilot/runs/20260713-211540-copilot-3b-lora-v3c --dataset outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl --scorer copilot/score_copilot_run_v2.py
> ```

你会看到 7 项检查逐条打印 `[PASS]`，最后一行：
```
PASS（WARN ×0）→ 该 run 的证据链闭合，分数可作为结论
```
这就说明：**仓库头版的 69.00% 是真实从磁盘算出来的**。这一步只需要 Python，不需要显卡、不需要 Ollama。

---

### 2.1 安装 Python

1. 打开 <https://www.python.org/downloads/>
2. 下载最新 3.x（3.8+ 都行，路径 A 不挑版本）
3. **Windows 安装时务必勾选 "Add Python to PATH"**（最下面那个方框）
4. 验证：打开"命令提示符"（Win+R 输入 `cmd` 回车），输入：
   ```bat
   python --version
   ```
   能看到 `Python 3.x.x` 就成功了。
   > 如果提示"不是内部或外部命令"，说明 PATH 没加好，重装并勾选 Add to PATH。

---

### 2.2 安装并启动 Ollama

- **Windows**：去 <https://ollama.com/download> 下载 `OllamaSetup.exe` 安装。装完任务栏右下角会出现一个羊驼图标 = 已在运行。
- **macOS**：`brew install ollama`，然后终端跑 `ollama serve`。
- **Linux**：按官网脚本安装，`ollama serve` 启动。

验证：
```bat
ollama --version
```
能看到版本号即成功。

> ⚠️ 跑评测时 Ollama 必须处于**运行中**状态（桌面版开着就行，或手动 `ollama serve`）。

---

### 2.3 拉取一个模型

随便挑一个能跑得动的模型（3B 级别最省资源）。在命令行输入：
```bat
ollama pull qwen2.5:3b
```
这会从网上下载约 2GB 的模型，等进度条走完。

> 想复现仓库里的 69%？那得用你自己训练/导入的 `copilot-3b-lora-v3c` 模型（见路径 B）。但**路径 A 用任意模型都行**，目的是让你熟悉整套流程、亲眼看到"假绿"。

用 `ollama list` 可以查看你已经有哪些模型。

---

### 2.4 下载本仓库

- 方式一（有 git）：`git clone <仓库地址>` 然后 `cd` 进目录
- 方式二（没 git）：在 GitHub 页面点 **Code → Download ZIP**，解压后得到一个文件夹

进入仓库根目录（里面应有 `eval/`、`copilot/`、`outputs/` 等文件夹）：
```bat
cd 你解压或克隆的目录
```

---

### 2.5 跑评测（评测入口）

```bat
python eval/run_copilot_eval.py --model qwen2.5:3b
```

运行时会一题一题打印（共 50 题）：
```
[1/50] id_001 (reviewer_qa) len=312 verdict=pass
[2/50] id_002 (failure_diagnosis) len=288 verdict=pass
...
run -> outputs/llm-lab/datasets/llm_lab_copilot/runs/20260713-XXXXXX-copilot-3b-lora-v3c
elapsed 42.3s | verdicts pass=50/50
REFERENCE_CHECK_RATE = 0.66 (scored 50/50, runtime_err 0)
by_task: {'reviewer_qa': 0.7, ...}
```

- `verdicts pass=50/50` → **naive 验证器说全绿 ✅**
- `REFERENCE_CHECK_RATE = 0.66` → **权威评分器只给 66%（你的模型可能不同）**

这就是"假绿"：全绿，但真实分只有约 2/3。

> 评测结果会自动保存到 `runs/` 下带时间戳的新文件夹里。**记下最后那行 `run -> ...` 的路径**，下一步要用。

---

### 2.6 跑纪律校验（证明分数没造假）

把上一步的路径填进去：
```bat
python verify_copilot_run.py ^
  --run-dir outputs/llm-lab/datasets/llm_lab_copilot/runs/20260713-XXXXXX-copilot-3b-lora-v3c ^
  --dataset outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl ^
  --scorer  copilot/score_copilot_run_v2.py
```
（把 `20260713-XXXXXX-...` 换成你 2.5 步实际生成的目录名；macOS/Linux 同样去掉 `^` 写成一行。）

它会**重新从磁盘读取你的输出、重新调用评分器**，逐项核对：
```
[1] outputs.jsonl 真实性 ... [PASS]
[2] verdicts.jsonl 对齐 ... [PASS]
[3][4] 真实 scorer 重跑 ... [PASS] overall_reference_check_rate = 66.00% ...
[5] tamper 审计 ... [PASS]
[6] report_summary 检查名 ... [PASS]
[7] 配置钉死 ... [PASS]
总判定: PASS → 该 run 的证据链闭合
```
看到 `总判定: PASS`，就说明你的分数**可审计、可复现**，不是报告里写死的。

---

## 3. 路径 B：完整训练复现（需要 NVIDIA 显卡）

> ⚠️ 这条路径**硬需求**：NVIDIA 显卡 + CUDA 驱动 + Python 3.10–3.12。没有显卡请用路径 A。
> ⚠️ 训练数据 `train_seed_200_aug.jsonl` 未纳入 git（版权/体积）。先用路径 A 跑通，训练数据请向作者索取或自行准备同格式数据。

### 3.1 准备 Python 环境并装依赖

```bat
:: 在仓库根目录
python -m venv train_env
train_env\Scripts\activate
pip install -r requirements_win3060.txt
```
激活后命令行前面会出现 `(train_env)`。装完依赖再继续。

> macOS / Linux：用 `python3 -m venv train_env` 和 `source train_env/bin/activate`。

---

### 3.2 准备基座模型

训练脚本默认用 `Qwen/Qwen2.5-Coder-3B-Instruct`（从 HuggingFace 自动下载）。需要联网，且会把模型缓存到 `HF_HOME` 指定的目录。

**强烈建议把缓存放到非系统盘**，否则容易塞满 C 盘：
```bat
set HF_HOME=F:/hf_cache
```
（把 `F:/hf_cache` 换成你机器上有空间的绝对路径。）

第一次训练时脚本会自动下载基座模型（约 6GB），请耐心等待。

---

### 3.3 训练 LoRA

```bat
set HF_HOME=F:/hf_cache
python train_copilot_3b_v3c.py
```

预期控制台顺序出现：
1. `GPU: NVIDIA GeForce RTX 3060 | ...` —— 确认识别到显卡
2. `Loading Qwen/Qwen2.5-Coder-3B-Instruct ...` → `Model loaded`
3. 每 10 步打印 `{'loss': ...}`，loss 应**逐步下降**
4. `Training done` → `LoRA adapter -> outputs/copilot_3b_lora_v3c/adapter`

**耗时**：RTX 3060 上约数小时（2 个 epoch）。产物 `outputs/copilot_3b_lora_v3c/adapter/` 已被 `.gitignore` 忽略，属正常现象。

> 如果报 `CUDA out of memory`：3060 已自动降档到最小配置；仍 OOM 就把 `train_copilot_3b_v3c.py` 里的 `BATCH_SIZE = 1` 或 `SEQ_LEN = 1024`。
> 如果报"未检测到 CUDA"：说明装成了 CPU 版 torch，请用 `requirements_win3060.txt` 里的 `unsloth` 自带 torch，**不要单独先 `pip install torch`**。

---

### 3.4 合并权重（CPU，离线，几分钟）

LoRA 训练只产出"补丁"（adapter），需要合并回完整模型才能给 Ollama 用：

```bat
python merge_clean_v3c_local.py
```

⚠️ **这个脚本里有写死的路径，换机器必须改！** 用记事本打开 `merge_clean_v3c_local.py`，找到这两行：
```python
BASE = "F:/hf_cache/hub/models--Qwen--Qwen2.5-Coder-3B-Instruct/snapshots/488639f1ff808d1d3d0ba301aef8c11461451ec5"
ADAPTER = "outputs/copilot_3b_lora_v3c/adapter"
```
- **`BASE` 必须改成你自己机器上的真实路径**：去你的 `HF_HOME\hub\models--Qwen--Qwen2.5-Coder-3B-Instruct\snapshots\` 目录下，会有一个类似 `488639...` 的长串文件夹，把它的完整路径填进去。
- `ADAPTER` / `OUT` 一般不用改（相对仓库根目录）。

成功会打印 `Done — clean merged model v3c ready for ollama.`，产物在 `outputs/copilot_3b_lora_v3c/merged_clean/`。

---

### 3.5 导入 Ollama

用记事本打开 `Modelfile_copilot3c`，把 `FROM` 那行改成你自己的 `merged_clean` 绝对路径：
```
FROM C:/你的路径/outputs/copilot_3b_lora_v3c/merged_clean
```
（Windows 用 `/` 或 `\\` 都行，别用中文路径。）

然后在命令行（仍在仓库根目录、且已 `ollama serve`）执行：
```bat
ollama create copilot-3b-lora-v3c -f Modelfile_copilot3c
```
成功后 `ollama list` 里会多出 `copilot-3b-lora-v3c:latest`。

---

### 3.6 评测 + 校验（同路径 A 的 2.5 / 2.6，模型名换成你训练的）

```bat
python eval/run_copilot_eval.py --model copilot-3b-lora-v3c:latest
python verify_copilot_run.py ^
  --run-dir outputs/llm-lab/datasets/llm_lab_copilot/runs/20260713-XXXXXX-copilot-3b-lora-v3c ^
  --dataset outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl ^
  --scorer  copilot/score_copilot_run_v2.py
```

预期权威分 **≈ 69.00%**（不同机器/驱动可能有 ±几个点的波动，属正常）。对照仓库自带的 `runs/20260713-213920-...-v3`（对照模型）应得 **≈ 67.00%**——两个模型在 naive 验证器眼里都是 100% 绿，但权威分只有约 2/3，这就是"假绿"标本。

---

## 4. 结果怎么读（核心概念）

| 名词 | 是什么 | 为什么重要 |
|---|---|---|
| **verdicts（实时验证器）** | 只检查"回答非空、够长" | 几乎永远 100% 绿——这正是"假绿"陷阱：绿灯 ≠ 答得好 |
| **reference_check_rate（权威评分器）** | 按 10 类 `reference_checks` 真打分 | 真实质量，v3c=69% / v3=67% |
| **by_task** | 拆到 5 类任务各自的分 | `report_summary`（要求"必含事实"）最低，约 33%——最难的一类 |
| **unsupported_claims** | 模型是否自我过度声称（如谎称"防篡改"） | 认知诚实维度；v3c 有 3 条、v3 有 7 条 |

**为什么 v3 比 v3c 差？** 两者训练数据相同，差别只在超参：
- `v3` 用"低侵入"超参（`r=8, α=16, 1 epoch, LR=2e-5`）→ 学得太少，质量差（67%）
- `v3c` 用"高容量"超参（`r=16, α=32, 2 epoch, LR=3e-5`）→ 学到结构又不贪，质量更好（69%）

---

## 5. 常见问题（排错表）

| 现象 | 根因 | 怎么解决 |
|---|---|---|
| `Failed to connect to localhost:11434` | Ollama 没启动 | 打开 Ollama 桌面程序，或命令行 `ollama serve` |
| `model not found` / `Model not found` | 模型名拼错，或没 pull / 没 `ollama create` | `ollama list` 看真实名字；路径 A 先 `ollama pull qwen2.5:3b` |
| `python` 不是内部命令 | PATH 没加 Python | 重装 Python 勾选 "Add to PATH" |
| 训练报 `CUDA out of memory` | 显存不够 | 把脚本 `BATCH_SIZE=1` 或 `SEQ_LEN=1024`；3060 已自动降档 |
| 训练报"未检测到 CUDA" | 装了 CPU 版 torch | 用 `requirements_win3060.txt` 的 `unsloth` 自带 torch，别单独先装 torch |
| 合并脚本报找不到 snapshot 路径 | 换机器硬路径失效 | 按 [§3.4](#34-合并权重cpu离线几分钟) 改 `BASE` 为你的真实路径 |
| `python` 启动后无反应 / 闪退 | 可能 Python 版本太旧 | 评测需 3.8+；训练需 3.10–3.12 |
| 评测卡住很久 | 模型生成慢或 `num_predict` 大 | 正常；50 题在 3060 上约数十秒到几分钟 |

---

## 6. 目录结构速查

```
仓库根目录/
├── eval/
│   ├── run_copilot_eval.py      # ★ 评测入口：生成回答 + 假绿验证 + 权威打分
│   └── run_eval.py              # 另一个通用评测平台（llm-lab）的入口，非 copilot 草稿
├── copilot/
│   └── score_copilot_run_v2.py  # ★ 权威评分器（10 类 reference_checks）
├── verify_copilot_run.py        # ★ 纪律校验器：重跑 scorer，证明分数可复现
├── train_copilot_3b_v3c.py      # 训练脚本（路径 B，需 GPU）
├── merge_clean_v3c_local.py     # 合并 LoRA 到完整模型（路径 B，需改 BASE 路径）
├── Modelfile_copilot3c          # Ollama 导入描述文件（路径 B，需改 FROM 路径）
├── requirements_win3060.txt     # 训练依赖清单（路径 B）
├── train_seed_200_aug.jsonl     # 训练数据（路径 B，未入库，需自备）
└── outputs/llm-lab/
    ├── README.md                # 门户文档
    ├── REPORT.md                # 完整过程报告（中英双语）
    ├── docs/
    │   ├── GETTING_STARTED.md   # 本文件
    │   ├── LESSONS.md           # 可审计评测五条纪律
    │   ├── blog/001-...md       # 英文长文
    │   └── adr/                 # 架构决策记录
    └── datasets/llm_lab_copilot/
        ├── test_50.jsonl        # ★ 50 题基准（5 类任务）
        └── runs/                # ★ 已提交的真实评测结果（证据）
            ├── 20260713-211540-...-v3c/   # v3c 修复模型，69.00%
            └── 20260713-213920-...-v3/     # v3 对照模型，67.00%
```

标 ★ 的是路径 A 必须有的文件，都在仓库里，开箱即用。

---

## 7. 想深入？

- **`outputs/llm-lab/REPORT.md`** — 完整过程：从"假绿"发现到根因分析到修复，中英双语
- **`outputs/llm-lab/docs/LESSONS.md`** — 可审计评测的五条纪律（可独立阅读）
- **`outputs/llm-lab/docs/blog/001-auditable-llm-eval-no-green-lights.md`** — 英文长文（HN 风格）
- **`outputs/llm-lab/docs/adr/`** — 4 篇架构决策记录（内容哈希 / 顺序同步 / 本地审计 / verifier≠scorer）

---

*本指南依据仓库真实脚本（`eval/run_copilot_eval.py`、`verify_copilot_run.py`、`copilot/score_copilot_run_v2.py`、`train_copilot_3b_v3c.py`、`merge_clean_v3c_local.py`、`Modelfile_copilot3c`）的实际接口与产物编写。最后更新：2026-07-13。*
