#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
score_copilot_run_v2.py — llm-lab-copilot 评分器升级版（对应 NEXT_STEPS_PLAN 的 A1）

实现反思里要求的 10 类 reference_checks + 结构化输出：
    exact_checks / soft_checks / unsupported_claims / missing_required_points / score

设计说明（重要）：
- 这是从用户反思推导出的「草稿实现」，不依赖真实仓库即可跑通自测。
- 接入真实仓库时需确认 test_50.jsonl 的字段名（loader 已做多别名容错）。
- exact_checks = 确定性（关键词/格式）检查；soft_checks = 语义检查，当前为
  启发式实现并标记 needs_llm=True，后续应接 LLM judge 升级。
- 新增 runtime_error 分类：timeout / connection refused 等归为 provider reliability，
  不计入 answer-quality 评分（解决 summary_002 类 240s timeout 误判模型能力的问题）。

用法：
  python score_copilot_run_v2.py --tests test_50.jsonl --predictions preds.jsonl --out report.jsonl --summary summary.json
  python score_copilot_run_v2.py --selftest        # 无仓库也能验证逻辑
"""
import argparse
import json
import re
import sys
from pathlib import Path

# ----------------------------------------------------------------------------
# 1) 检查实现：每个函数 (spec, output_text) -> (passed: bool, detail: str[, soft])
# ----------------------------------------------------------------------------
def _norm(s):
    return (s or "").lower()


# 否定词：出现在宣称短语前若干字符内，则该宣称应视为「否认」而非「断言」
NEG = re.compile(
    r"(不|没|没有|无法|不能|不应|禁止|并非|does not|doesn't|not|cannot|"
    r"can't|never|no|isn't|won't|without)"
)


def _denied_before(text, start, window=8):
    """match 前 window 字符内是否含否定词（粗略但够用）。"""
    return bool(NEG.search(text[max(0, start - window):start]))


def _kw(spec):
    return spec.get("value") or spec.get("keywords") or spec.get("args") or []


def check_must_include_any(spec, out):
    kws = _kw(spec)
    low = _norm(out)
    hit = [k for k in kws if _norm(k) in low]
    return (len(hit) > 0, f"命中: {hit}" if hit else f"未命中任何: {kws}")


def check_must_include_all(spec, out):
    kws = _kw(spec)
    low = _norm(out)
    miss = [k for k in kws if _norm(k) not in low]
    return (len(miss) == 0, f"缺失: {miss}" if miss else "全部命中")


def check_must_answer_no(spec, out):
    first = re.split(r"[.。\n]", out.strip(), 1)[0]
    low = _norm(first)
    neg = re.search(r"\b(no|not|cannot|can't|不能|无法|没有|否|不应该|不建议|不行)\b", low)
    pos = re.search(r"\b(yes|是|可以|能|应该|建议|可行)\b", low)
    passed = bool(neg) and not (pos and (neg is None or pos.start() < neg.start()))
    return (passed, f"首句: {first[:60]!r}")


def check_must_explain_surface_constraints(spec, out):
    low = _norm(out)
    hints = ["structural", "surface", "结构", "表面", "verifier", "verify", "约束",
             "constraint", "format", "格式", "schema", "字段", "校验"]
    hit = [h for h in hints if h in low]
    return (len(hit) > 0, f"启发式命中: {hit}", True)  # soft


def check_must_recommend_manual_or_semantic_eval(spec, out):
    low = _norm(out)
    hints = ["manual", "人工", "semantic", "语义", "human", "专家", "进一步评估",
             "人工复核", "人工审查"]
    hit = [h for h in hints if h in low]
    return (len(hit) > 0, f"命中: {hit}")


def check_must_mention_rerun_or_reproducibility(spec, out):
    low = _norm(out)
    hints = ["rerun", "re-run", "重跑", "reproduc", "可复现", "复现", "reproduce", "重新运行"]
    hit = [h for h in hints if h in low]
    return (len(hit) > 0, f"命中: {hit}")


def check_must_not_claim_tamper_proof(spec, out):
    low = _norm(out)
    bad = ["tamper-proof", "tamper proof", "防篡改", "不可篡改", "无法篡改",
           "绝对安全", "100% secure", "完全安全", "cannot be tampered"]
    hit = []
    for b in bad:
        for m in re.finditer(re.escape(b), low):
            if not _denied_before(low, m.start()):
                hit.append(b)
                break
    return (len(hit) == 0, f"发现过度宣称: {hit}" if hit else "未宣称防篡改")


def check_must_distinguish_provider_error(spec, out):
    low = _norm(out)
    hints = ["provider error", "provider 错误", "provider 故障", "连接失败",
             "connection refused", "timeout", "超时", "网络", "api error", "服务错误", "连接错误"]
    hit = [h for h in hints if h in low]
    return (len(hit) > 0, f"命中: {hit}")


def check_must_not_judge_semantic_quality(spec, out):
    low = _norm(out)
    bad = ["proves semantic", "证明语义", "语义质量更好", "语义上更好", "better quality",
           "语义更优", "保证质量", "guarantees quality", "语义层面更好", "语义上更优"]
    hit = []
    for b in bad:
        for m in re.finditer(re.escape(b), low):
            if not _denied_before(low, m.start()):
                hit.append(b)
                break
    return (len(hit) == 0, f"发现越界断言: {hit}" if hit else "未越界评判语义质量")


def check_must_check_reason_and_action(spec, out):
    low = _norm(out)
    hints = ["reason", "原因", "because", "因为", "action", "建议", "修复", "fix",
             "should", "应该", "下一步", "next step", "recommend", "推荐"]
    hit = [h for h in hints if h in low]
    return (len(hit) > 0, f"启发式命中: {hit}", True)  # soft


# 类型 -> (函数, 是否 soft)
DISPATCH = {
    "must_include_any_keywords": (check_must_include_any, False),
    "must_include_all_keywords": (check_must_include_all, False),
    "must_answer_no": (check_must_answer_no, False),
    "must_explain_surface_constraints": (check_must_explain_surface_constraints, True),
    "must_recommend_manual_or_semantic_eval": (check_must_recommend_manual_or_semantic_eval, False),
    "must_mention_rerun_or_reproducibility": (check_must_mention_rerun_or_reproducibility, False),
    "must_not_claim_tamper_proof": (check_must_not_claim_tamper_proof, False),
    "must_distinguish_provider_error": (check_must_distinguish_provider_error, False),
    "must_not_judge_semantic_quality": (check_must_not_judge_semantic_quality, False),
    "must_check_reason_and_action": (check_must_check_reason_and_action, True),
}

# 过度宣称检测（全局，针对整个 output）
OVERCLAIM_PATTERNS = [
    r"tamper[- ]?proof", r"防篡改", r"不可篡改", r"无法篡改",
    r"proves? (semantic|quality)", r"证明(语义|质量)", r"语义(质量|上)?更好", r"语义更优",
    r"100%\s*(secure|accurate|correct|通过|准确|正确)", r"完全(准确|正确|通过|安全)",
    r"guarantee[s]? (quality|correct|语义|质量)", r"保证(质量|正确|语义)",
]

# 运行时错误（provider reliability，不计入 answer quality）
RUNTIME_PATTERNS = [
    r"timeout", r"timed out", r"\b240s\b", r"connection refused", r"connection error",
    r"连接失败", r"网络错误", r"network error", r"api error", r"rate limit", r"服务错误",
]


def find_unsupported_claims(out):
    low = _norm(out)
    found = []
    for p in OVERCLAIM_PATTERNS:
        for m in re.finditer(p, low):
            if not _denied_before(low, m.start()):  # 否定表述不算过度宣称
                found.append(m.group(0))
    return found


def classify_runtime(out):
    # 只对"短的 harness 报错回显"触发（如 "Error: connection refused ..."）。
    # 长答案里出现 timeout/connection refused 往往是 failure_diagnosis 题的
    # 正当诊断内容，不能误判为运行时错误（否则会把答对的题排除、低估真实分）。
    text = (out or "").strip()
    if len(text) >= 200:
        return False
    low = _norm(text)
    for p in RUNTIME_PATTERNS:
        if re.search(p, low):
            return True
    return False


# ----------------------------------------------------------------------------
# 2) 单条评分
# ----------------------------------------------------------------------------
def score_one(item, pred_text, harness_error=False):
    checks = item.get("reference_checks") or item.get("checks") or []
    out = pred_text or ""
    exact_checks, soft_checks = {}, {}
    missing_required_points = []

    for c in checks:
        ctype = c.get("type") or c.get("name") or c.get("check")
        if ctype not in DISPATCH:
            # 未知检查类型：跳过但记录
            soft = False
            res = (None, f"未知检查类型: {ctype}")
        else:
            fn, soft = DISPATCH[ctype]
            res = fn(c, out)
        passed, detail = res[0], res[1]
        entry = {"passed": passed, "detail": detail}
        if soft:
            entry["needs_llm"] = True
            soft_checks[ctype] = entry
        else:
            exact_checks[ctype] = entry
        # 缺失必需点（仅对 include 类失败项）
        if passed is False and ctype in ("must_include_any_keywords", "must_include_all_keywords"):
            missing_required_points.extend([k for k in _kw(c) if _norm(k) not in _norm(out)])

    unsupported = find_unsupported_claims(out)
    # 优先信任生成阶段 harness 记录的真实 error；无则回退到（收紧后的）文本启发式
    runtime_err = bool(harness_error) or classify_runtime(out)

    # 评分：runtime 错误时 answer-quality 单独标记，不计入
    exact_total = len(exact_checks)
    exact_pass = sum(1 for v in exact_checks.values() if v["passed"] is True)
    if runtime_err:
        score = None  # 运行时问题，无法评判语义质量
    elif exact_total > 0:
        score = round(exact_pass / exact_total, 4)
    else:
        score = None

    return {
        "id": item.get("id"),
        "task": item.get("task") or item.get("type"),
        "runtime_error": runtime_err,
        "exact_checks": exact_checks,
        "soft_checks": soft_checks,
        "unsupported_claims": unsupported,
        "missing_required_points": sorted(set(missing_required_points)),
        "score": score,
    }


# ----------------------------------------------------------------------------
# 3) 批量 + 汇总
# ----------------------------------------------------------------------------
def _load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _out_text(pred):
    return pred.get("output") or pred.get("answer") or pred.get("prediction") or ""


def run(tests_path, preds_path, out_path, summary_path):
    tests = _load(tests_path)
    preds = {p.get("id"): p for p in _load(preds_path)}
    results = []
    for t in tests:
        pred = preds.get(t.get("id"))
        ptxt = _out_text(pred) if pred else ""
        herr = bool(pred.get("error")) if pred else False
        results.append(score_one(t, ptxt, harness_error=herr))

    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 汇总（分离运行时与语义）
    semantic = [r for r in results if not r["runtime_error"] and r["score"] is not None]
    runtime = [r for r in results if r["runtime_error"]]
    overall = round(sum(r["score"] for r in semantic) / len(semantic), 4) if semantic else None
    by_task = {}
    for r in semantic:
        by_task.setdefault(r["task"], []).append(r["score"])
    by_task_avg = {k: round(sum(v) / len(v), 4) for k, v in by_task.items()}

    summary = {
        "total": len(results),
        "semantic_scored": len(semantic),
        "runtime_errors": len(runtime),
        "overall_reference_check_rate": overall,
        "by_task": by_task_avg,
        "items_with_unsupported_claims": sum(1 for r in results if r["unsupported_claims"]),
    }
    if summary_path:
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
    return results, summary


# ----------------------------------------------------------------------------
# 4) 自测（无需真实仓库）
# ----------------------------------------------------------------------------
def selftest():
    cases = [
        {  # 全过
            "id": "t_pass", "task": "eval_yaml",
            "reference_checks": [
                {"type": "must_include_all_keywords", "value": ["eval.yaml", "metrics"]},
                {"type": "must_recommend_manual_or_semantic_eval"},
                {"type": "must_not_claim_tamper_proof"},
                {"type": "must_not_judge_semantic_quality"},
            ],
            "pred": "生成 eval.yaml，包含 metrics 字段。建议人工复核语义。本验证仅结构层，不证明语义质量。",
        },
        {  # 过度宣称 + 缺失
            "id": "t_fail", "task": "failure_diagnosis",
            "reference_checks": [
                {"type": "must_include_all_keywords", "value": ["provider", "timeout"]},
                {"type": "must_not_claim_tamper_proof"},
            ],
            "pred": "这是 tamper-proof 的系统，完全安全。未提及 provider。",
        },
        {  # 运行时错误（不计入语义）
            "id": "t_rt", "task": "report_summary",
            "reference_checks": [{"type": "must_include_all_keywords", "value": ["summary"]}],
            "pred": "Error: connection refused after 240s timeout.",
        },
    ]
    ok = True
    for c in cases:
        r = score_one({"id": c["id"], "task": c["task"], "reference_checks": c["reference_checks"]}, c["pred"])
        print(f"[{c['id']}] task={r['task']} runtime_error={r['runtime_error']} score={r['score']}")
        print("   exact:", {k: v["passed"] for k, v in r["exact_checks"].items()})
        print("   unsupported:", r["unsupported_claims"], "missing:", r["missing_required_points"])
        # 断言
        if c["id"] == "t_pass" and r["score"] != 1.0:
            ok = False; print("  !! FAIL: t_pass 应得 1.0")
        if c["id"] == "t_fail":
            if not r["unsupported_claims"]:
                ok = False; print("  !! FAIL: t_fail 应检出过度宣称")
            if "timeout" not in r["missing_required_points"]:
                ok = False; print("  !! FAIL: t_fail 应标记缺失 timeout")
        if c["id"] == "t_rt" and (not r["runtime_error"] or r["score"] is not None):
            ok = False; print("  !! FAIL: t_rt 应判 runtime_error 且 score=None")
    print("\nSELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tests", help="测试集 jsonl（含 reference_checks）")
    ap.add_argument("--predictions", help="模型输出 jsonl（id -> output）")
    ap.add_argument("--out", help="逐条结构化评分输出 jsonl")
    ap.add_argument("--summary", help="汇总 json")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测（无需仓库）")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(selftest())
    if not (args.tests and args.predictions):
        ap.error("需要 --tests 与 --predictions（或 --selftest）")
    results, summary = run(args.tests, args.predictions, args.out, args.summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
