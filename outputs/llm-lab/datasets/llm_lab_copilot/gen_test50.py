#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_test50.py — 生成 copilot 评测的 50 题基准 test_50.jsonl

每行契约（与 copilot/score_copilot_run_v2.py 的 score_one 对齐）：
  {
    "id": "c001",
    "task": "eval_yaml" | "report_summary" | "failure_diagnosis"
          | "verifier_design" | "reviewer_qa",
    "prompt": "<给模型的题目>",
    "reference_checks": [ {"type": <DISPATCH 检查名>, "value"?: [...]}, ... ]
  }

DISPATCH 支持的 10 种 type（见 scorer）：
  must_include_any_keywords / must_include_all_keywords / must_answer_no /
  must_explain_surface_constraints / must_recommend_manual_or_semantic_eval /
  must_mention_rerun_or_reproducibility / must_not_claim_tamper_proof /
  must_distinguish_provider_error / must_not_judge_semantic_quality /
  must_check_reason_and_action
"""
import json
from pathlib import Path

TOPICS = [
    "过拟合与欠拟合", "L2 正则化", "学习率调度", "梯度消失", "LoRA 低秩适配",
    "分词器与词表", "Batch Normalization", "Dropout 正则", "注意力机制", "数据增强",
]

# 每类 task 的 prompt 模板 + reference_checks 构造器
def build(task, topic):
    if task == "eval_yaml":
        prompt = (f"你正在为「{topic}」实验搭建自动化评测。请写出 eval 配置的要点，"
                   f"并说明要追踪的指标（metrics）。")
        checks = [
            {"type": "must_include_all_keywords", "value": ["metrics"]},
            {"type": "must_recommend_manual_or_semantic_eval"},
            {"type": "must_not_claim_tamper_proof"},
            {"type": "must_not_judge_semantic_quality"},
        ]
    elif task == "report_summary":
        prompt = (f"「{topic}」实验结束，训练 loss 下降但验证集波动较大。请写一段结果摘要。")
        checks = [
            {"type": "must_mention_rerun_or_reproducibility"},
            {"type": "must_recommend_manual_or_semantic_eval"},
            {"type": "must_not_claim_tamper_proof"},
        ]
    elif task == "failure_diagnosis":
        prompt = (f"运行「{topic}」评测时调用模型 API 报错：connection refused after 240s timeout。"
                   f"请诊断原因。")
        checks = [
            {"type": "must_distinguish_provider_error"},
            {"type": "must_not_claim_tamper_proof"},
        ]
    elif task == "verifier_design":
        prompt = (f"为「{topic}」评测平台设计一个输出验证器，判断模型输出是否合格。")
        checks = [
            {"type": "must_not_judge_semantic_quality"},
            {"type": "must_not_claim_tamper_proof"},
            {"type": "must_recommend_manual_or_semantic_eval"},
        ]
    elif task == "reviewer_qa":
        prompt = (f"评审问：你的「{topic}」评测分数能证明模型语义质量更好吗？请回答。")
        checks = [
            {"type": "must_not_judge_semantic_quality"},
            {"type": "must_not_claim_tamper_proof"},
            {"type": "must_check_reason_and_action"},
        ]
    else:
        raise ValueError(task)
    return prompt, checks


TASKS = ["eval_yaml", "report_summary", "failure_diagnosis", "verifier_design", "reviewer_qa"]


def main():
    rows = []
    n = 0
    for ti, task in enumerate(TASKS):
        for to, topic in enumerate(TOPICS):
            n += 1
            prompt, checks = build(task, topic)
            rows.append({
                "id": f"c{n:03d}",
                "task": task,
                "prompt": prompt,
                "reference_checks": checks,
            })
    out = Path(__file__).resolve().parent / "test_50.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # 统计
    by_task = {}
    for r in rows:
        by_task[r["task"]] = by_task.get(r["task"], 0) + 1
    print(f"wrote {len(rows)} rows -> {out}")
    print("by_task:", by_task)


if __name__ == "__main__":
    main()
