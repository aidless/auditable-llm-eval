# 运行日志模板（3060 实跑记录）

> 复制本表，每跑完一个阶段填一行。重点记录**实际耗时**与**显存峰值**（决定能否升档 `--batch 4 --seq-len 4096`）。
> 显存峰值观测：`nvidia-smi -l 1` 训练期间看 `MiB` 峰值；或 `nvidia-smi --query-gpu=memory.used --format=csv -l 1 > vram.log` 后取最大值。

| 阶段 | 实际命令 | 开始 | 结束 | 耗时 | 显存峰值 | 关键指标（loss/acc） | 退出码 | 备注 / 异常 |
|---|---|---|---|---|---|---|---|---|
| 0 装环境 | `pip install -r requirements_win3060.txt` | | | | — | `torch.cuda.is_available()==True` | | |
| 1 M0 (1.5B) | `python run_all.py --skip-m2 --skip-m3 --papers 20` 中的 M0 腿 | | | | | M0 loss 末值： | | |
| 1 M1 (数据) | 同上命令中的 M1 腿 | | | | — | `training_all.jsonl` 行数： | | arXiv 是否降级摘要？ |
| 2 M2 (3B) | `python run_all.py --skip-m0 --skip-m1 --skip-m3 --papers 200 [--manuscript ...]` | | | | | eval_loss 末值： / 早停轮： | | batch/seq 实际值： |
| 3 M3 (评估) | `python run_all.py --skip-m0 --skip-m1 --skip-m2` | | | | | mc 正确率（基座 vs 微调后）： | | 开放题评分： |
| 4 路径B | `python run_all.py --papers 200 --manuscript ... --reviews review_corpus.jsonl` | | | | | mc 正确率： / 审稿偏好质量： | | lr 是否降档？ |

## 升档判定（填阶段 2 时参考）
- 显存峰值 **< 5.0GB** 且训练稳定 → 可进阶 `--batch 4 --seq-len 4096`（峰值约 5.5GB）。
- 显存峰值 **≥ 5.5GB** 或触发 OOM → 保持默认 `batch=2/seq=2048`，或按 `TRAINING_TROUBLESHOOTING.md` 降档。

## 异常速记
- 报错粘贴区（把完整报错贴这里，便于回看 / 交给我诊断）：

```
<在此粘贴报错>
```
