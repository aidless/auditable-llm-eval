# 训练排错速查（RTX 3060 6GB · Qwen2.5-3B QLoRA）

本速查针对本工程在 **RTX 3060 6GB / Windows** 上跑 M0→M3 时最常见的失败与卡点，按"现象 → 根因 → 处置"组织。先定位阶段，再查表。

> 训练（M0/M2）与 M3 推理**必须在 3060 上执行**；M1 数据腿与 `eval_mc` 判分可在任意环境。所有训练前先 `pip install -r requirements_win3060.txt`。

---

## 0. 你卡在哪一步？

| 阶段 | 典型失败信号 | 跳到 |
|---|---|---|
| 安装 | `pip install` 报 torch/CUDA 错配、unsloth import 失败 | §2.1 / §2.2 |
| M0 训练 | 启动即 `未检测到 CUDA` / 中途 CUDA OOM | §2.2 / §2.3 |
| M1 数据 | `arxiv` 报错、`正文级成功 0 / 降级 N` | §2.4 / §2.5 |
| M2 训练 | OOM、eval_loss 早期反弹、训练极慢 | §2.3 / §2.6 / §2.7 |
| M2 合并 | `--merge` 后推理 OOM / 输出乱码 | §2.8 / §2.9 |
| 通用 | C 盘爆满 | §2.5 |

---

## 1. 显存预算拆解（3060 6.0GB）

理解钱的去向，才能决定升/降档：

| 占用项 | 估算 | 备注 |
|---|---|---|
| 3B 4bit 权重（GPU） | ~2.0 GB | `load_in_4bit=True` 后常驻 |
| 优化器状态（paged_adamw_8bit） | ~1.0–1.5 GB | 8bit 分页，按需换页 |
| 激活 + 梯度检查点 | 取决于 `batch × seq_len` | 主要可变项 |
| 框架/碎片 | ~0.3–0.5 GB | CUDA context 等 |

- **安全默认（low 档）`batch=2 / seq=2048`**：峰值约 **4.0–4.5 GB**，余量充足。
- **进阶目标 `batch=4 / seq=4096`**：峰值可能到 **5.0–5.5 GB**，临界。
- **经验阈值**：`nvidia-smi` 峰值 **< 5.0 GB** 才建议尝试升档；≥ 5.5 GB 随时 OOM。

---

## 2. 故障 → 处置表

### 2.1 pip 安装失败 / 版本错配
- **现象**：`pip install -r requirements_win3060.txt` 报 `torch` 与 CUDA 不匹配，或装完 `import torch` 提示无 CUDA。
- **根因**：先单独装了 `torch`（默认 CPU 版或错配 CUDA 版），再装 `unsloth` 时冲突。
- **处置**：卸载残留 `pip uninstall torch torchvision`；重跑 `pip install -r requirements_win3060.txt`，让 `unsloth[windows-torch230]` 决定 torch 版本（自带 CUDA 12.1）。**勿单独先装 torch**。

### 2.2 unsloth / CUDA 不可用（M0 启动即 fatal）
- **现象**：`train_lora.py` 打印 `[fatal] 未检测到 CUDA` 或 `torch.cuda.is_available() == False`。
- **根因**：torch 装成 CPU 版；或驱动过旧不支持 CUDA 12.x。
- **处置**：确认装的是 `unsloth[windows-torch230]` 自带 torch（见 §2.1）；`nvidia-smi` 能看到 GPU 且驱动 ≥ 527。仍不行则重装依赖。

### 2.3 CUDA OOM（M2 训练中）
- **现象**：训练中途 `CUDA out of memory`。
- **处置（逐级降载）**：
  1. 默认已是 `batch=2 / seq=2048`；若仍 OOM → `--batch 1 --seq-len 2048`。
  2. 降 LoRA 容量：`--lora-r 16`（更少参数/激活）。
  3. 降序列：`--seq-len 1024`（公式/长文样本会被截断，质量降）。
  4. 升 `gradient_accumulation_steps` 至 8 以在更小 batch 下保有效批大小。
- **仍 OOM**：3B 在 6GB 上已接近极限，考虑把数据量砍半或迁移云端（A100/H100）。**不要在 6GB 上试 7B 全量训练**。

### 2.4 arxiv 报错（M1）
- **现象**：`Client.results() missing 1 required positional argument: 'search'`，或 `AttributeError: 'Result' object has no attribute 'download_source'`。
- **根因**：装了 `arxiv` 4.x（破坏性变更）。脚本已兼容，但要求 `arxiv==1.4.2`（已锁版）。
- **处置**：`pip install "arxiv==1.4.2"`。若已锁版仍报错，确认 `requirements` 正确安装、未被其它环境覆盖。

### 2.5 C 盘爆满 / 缓存重定向失效
- **现象**：训练/抓取时 C 盘空间骤降，或写缓存报"磁盘满"。
- **根因**：HF 缓存 / arXiv 源码缓存写到了 C 盘。
- **处置**：脚本默认已重定向 `HF_HOME→F:/hf_cache`、`arXiv 源码→F:/arxiv_src`（治本）。若你机器 F 盘不存在，用 `--hf-cache D:/hf_cache` 覆盖。确认 F 盘（或你指定的盘）有 ≥ 15GB 余量（3B 权重 ~6GB + 中间缓存）。

### 2.6 eval_loss 早期反弹（过拟合）
- **现象**：训练几十步后 `eval_loss` 不降反升。
- **根因**：lr 偏高 / 数据量小且同质（学术领域语料易记）。
- **处置**：降 lr（`1e-4 → 5e-5 → 1e-5`）；降 epoch（已是 2，必要时 1）；升 `lora_dropout` 至 0.2；升 `eval_ratio` 至 0.1。推理类微调宁可轻微欠拟合，不要背下来。

### 2.7 训练极慢（batch=2）
- **现象**：每步耗时高，预计数小时。
- **根因**：3060 low 档默认 `batch=2 / seq=2048`，每 epoch 步数翻倍。
- **处置**：`nvidia-smi -l 1` 盯峰值；若 < 5.0 GB，显式 `--batch 4 --seq-len 4096` 覆盖提速（OOM 即回退）。`gradient_checkpointing` 已开（用算力换显存），属正常。

### 2.8 合并权重后推理 OOM
- **现象**：M3 `run_eval.py` 加载 `qwen25-3b-tmlr-merged` 时 OOM。
- **根因**：合并后是 fp16 全精度 ~6GB，推理也要装进 6GB。
- **处置**：推理用 4bit 加载（改 `run_eval.py` 加 `load_in_4bit`），或先 `--skip-m3` 只生成 mc 答案（mc 量小）；或评估时只抽部分题（改 `eval_questions.jsonl` 行数）。

### 2.9 输出乱码 / 不像 Instruct 模型
- **现象**：模型输出不遵循指令、中文乱码、重复。
- **根因**：chat template 错配；或训练数据 `conversations` 格式不对。
- **处置**：确认数据每行是 `{"conversations":[{"role":"user",...},{"role":"assistant",...}]}`；Instruct 基座用其原生 chat 模板（Unsloth 直接喂 `conversations` 即可，勿手拼）。检查 `training_all.jsonl` 非空且格式合法。

---

## 3. 升档 / 降档决策树（M2）

```
开始 M2（默认安全：batch=2 / seq=2048，low 档自动）
   │
   ├─ 训练顺利，nvidia-smi 峰值 < 5.0 GB？
   │      └─ 是 → 试进阶：--batch 4 --seq-len 4096（恢复"舒适区"吞吐）
   │             ├─ 仍顺利（峰值 < 5.5 GB）→ 保留
   │             └─ OOM → 回退到 --batch 2 --seq-len 4096 或默认
   │
   └─ 默认即 OOM？
          └─ 降载：--batch 1 --seq-len 2048 → 仍 OOM？ --lora-r 16
                 → 仍 OOM？ 砍数据量 或 迁移云端（A100/H100）
```

**不要**在 6GB 上尝试 7B 全量 / 大 batch——收益不抵 OOM 风险。

---

## 4. 监控与诊断命令

```bash
nvidia-smi -l 1            # 实时盯显存/利用率（训练时另一终端常开）
nvidia-smi --query-gpu=memory.used,memory.total --format=csv  # 单次快照
# 看训练进度（loss 应稳步下降；eval_loss 不应反弹）
# 合并后确认产物：
ls outputs/qwen25-3b-tmlr-merged/   # 应有 config.json + 权重文件
```

进程卡死/显存不释放时，任务管理器结束 Python 进程，或：
```bash
# Windows：按 PID 结束
taskkill /PID <pid> /F
```

---

## 5. 路径 B（审稿偏好）专属注意

- **小语料易过拟合**：审稿语料通常远少于领域语料。第二轮训练务必降 lr（`5e-5` 起），或对新数据用**独立 LoRA 适配器**，避免冲刷首轮领域能力。
- **务必替换模板**：`review_corpus_TEMPLATE.jsonl` 仅为格式示例；直接拿它训练会学到示例噪声。用真实审稿语料（#47–51 审稿意见 / PC 评语 / 偏好清单）替换。
- **格式校验**：`python data/convert_reviews.py --make-template review_corpus_TEMPLATE.jsonl` 先看格式；运行后查 `data/review_cot_data.jsonl` 行数是否符合预期（X 条语料 → 至多 X 条样本，空/畸形条目会被跳过）。

---

## 6. 紧急最小可跑配置

若一切不顺，先用最小配置确认管道本身没问题：

```bash
# 最小 M0 验证（1.5B，1 epoch，无验证集，最快暴露环境/格式问题）
python run_all.py --skip-m2 --skip-m3 --papers 20
# 若 M0 训练能结束并产出 outputs/m0_verify/，说明环境+数据格式 OK，
# 再逐步放量到 M2（3B）。
```

*本速查与 `RUN_GUIDE.md`（运行监控清单）、`M2_CONFIG_REVIEW.md`（超参审计）、技能 `finetune_playbook.md` §8（排错要点）互为补充。最后更新：2026-07-12。*
