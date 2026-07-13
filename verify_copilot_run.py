#!/usr/bin/env python3
"""
verify_copilot_run.py — 实证纪律证据校验器（llm-lab copilot 评测）

用途：在 3060 真跑完一个 copilot 评测 run 之后，用本脚本把"声称 vs 证据"的落差
逐项勾掉。所有结论都来自磁盘上的真实文件 + 真实 scorer 重跑，不依赖任何报告里的
断言数字。

检查项（对应反思里的 P0/P1/P2）：
  [1] outputs.jsonl 真实条数 + 全部非空
  [2] verdicts.jsonl 真实条数 + 与 outputs 对齐
  [3] 用真实 scorer 重跑，复现 overall 分（预测不能当结果）
  [4] 逐任务分（eval_yaml / report_summary / failure_diagnosis / verifier_design / reviewer_qa）
  [5] tamper 审计：输出里若出现 tamper 词，判定是"正确否认"(应过)还是"真实声称"(应挂)，
      标记任何残留误判
  [6] report_summary 的"必含事实"reference_checks 是否真编码进数据集 + scorer 是否实现
  [7] 配置钉死：model 字符串 + temperature==0（呼应"锁版本"）

用法：
  python verify_copilot_run.py \
      --run-dir "C:/.../outputs/llm-lab/runs/20260712-115605-copilot_base_few_shot_v3_full" \
      --dataset "C:/.../outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl" \
      --scorer  "C:/.../outputs/llm-lab/scripts/score_copilot_run.py" \
      --scorer-python "C:/.../venv/Scripts/python.exe"   # 需含 pyyaml

输出：每项 PASS/FAIL/WARN + 末尾一句总判定。退出码 0=全部 PASS/WARN，1=有 FAIL。
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# ---- 与 scorer 保持一致的否定感知逻辑（stdlib 复刻，避免 import 依赖）----
TAMPER_PHRASES = ["tamper-proof", "防篡改", "不可篡改"]


def denied_before(text: str, index: int, window: int = 48) -> bool:
    prefix = text[max(0, index - window):index].lower().strip()
    en = r"(?:\bnot\b|\bnever\b|\bno\b|\bwithout\b|\bcannot\b|\bcan't\b|" \
         r"\bdoes\s+not\b|\bdo\s+not\b|\bdid\s+not\b|\bis\s+not\b|\bare\s+not\b)[\s\w-]{0,32}$"
    zh = r"(?:不是|并非|不属于|不能|无法|没有|无).{0,20}$"
    return bool(re.search(en, prefix) or re.search(zh, prefix))


def has_unsupported_claim(text: str, phrases) -> bool:
    low = text.lower()
    for ph in phrases:
        start = 0
        while True:
            i = low.find(ph.lower(), start)
            if i < 0:
                break
            if not denied_before(text, i):
                return True
            start = i + len(ph)
    return False


def read_jsonl(p: Path):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def section(title):
    print("\n" + "=" * 70 + f"\n{title}\n" + "=" * 70)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--dataset", required=True, type=Path)
    ap.add_argument("--scorer", required=True, type=Path)
    ap.add_argument("--scorer-python", default=sys.executable)
    ap.add_argument("--model-expected", default=None, help="配置里应钉死的 model 字符串，如 qwen2.5-coder:7b")
    ap.add_argument("--temp-expected", type=float, default=0.0)
    args = ap.parse_args()

    fails = 0
    warns = 0

    def mark(ok, label, detail=""):
        nonlocal fails, warns
        if ok is True:
            print(f"  [PASS] {label}" + (f" — {detail}" if detail else ""))
        elif ok is False:
            fails += 1
            print(f"  [FAIL] {label}" + (f" — {detail}" if detail else ""))
        else:  # WARN
            warns += 1
            print(f"  [WARN] {label}" + (f" — {detail}" if detail else ""))

    section("[1] outputs.jsonl 真实性与条数")
    outs_path = args.run_dir / "outputs.jsonl"
    if not outs_path.exists():
        mark(False, "outputs.jsonl 存在", str(outs_path))
        print("\n总判定: FAIL（无 outputs，无法继续）")
        return 1
    outs = read_jsonl(outs_path)
    nonempty = sum(1 for o in outs if (o.get("output") or o.get("text") or "").strip())
    mark(len(outs) == 50, f"outputs 条数 == 50（实际 {len(outs)}）")
    mark(nonempty == len(outs), f"全部非空（非空 {nonempty}/{len(outs)}）")

    section("[2] verdicts.jsonl 真实性与对齐")
    ver_path = args.run_dir / "verdicts.jsonl"
    if ver_path.exists():
        vers = read_jsonl(ver_path)
        mark(len(vers) == len(outs), f"verdicts 与 outputs 对齐（{len(vers)} vs {len(outs)}）")
    else:
        mark(False, "verdicts.jsonl 存在", str(ver_path))

    section("[3][4] 真实 scorer 重跑（复现分数，预测不当结果）")
    out_json = args.run_dir / "report.jsonl"
    summary_json = args.run_dir / "_verify_summary.json"
    r = subprocess.run(
        [args.scorer_python, str(args.scorer),
         "--tests", str(args.dataset),
         "--predictions", str(args.run_dir / "outputs.jsonl"),
         "--out", str(out_json),
         "--summary", str(summary_json)],
        capture_output=True, text=True,
    )
    scores = None
    if r.returncode != 0 or not summary_json.exists():
        mark(False, "scorer 可运行", r.stderr[-500:])
    else:
        s = json.loads(summary_json.read_text(encoding="utf-8"))
        rate = s["overall_reference_check_rate"]
        mark(True, f"overall_reference_check_rate = {rate*100:.2f}% "
                   f"(scored {s['semantic_scored']}/{s['total']}, runtime_err {s['runtime_errors']})")
        print("  逐任务分(by_task):")
        for tt, v in s.get("by_task", {}).items():
            print(f"    - {tt}: {v*100:.2f}%")
        rows = []
        if out_json.exists():
            with open(out_json, encoding="utf-8") as _f:
                rows = [json.loads(l) for l in _f if l.strip()]
        scores = {"summary": s, "rows": rows}

    section("[5] tamper 审计（残留误判 vs 真实声称）")
    # 用 outputs 原文做审计（scorer 的 rows 不含原文，这里直接读 outputs）
    residual_fp = 0
    real_claims = 0
    for o in outs:
        txt = (o.get("output") or o.get("text") or "")
        if has_unsupported_claim(txt, TAMPER_PHRASES):
            real_claims += 1
            pid = o.get("prompt_id") or o.get("id")
            print(f"    [真实声称] {pid}: 输出含未否认的 tamper 词 → 应判挂（合理）")
        else:
            # 含词但被否认 → 正确，不计入问题；完全不含词 → 无关
            low = txt.lower()
            if any(p in low for p in TAMPER_PHRASES):
                pid = o.get("prompt_id") or o.get("id")
                print(f"    [正确否认] {pid}: 含 tamper 词但附近有否定 → 应判过（无误判）")
    if scores:
        # 交叉核对：scorer 把 must_not_claim_tamper_proof 判挂的行，是否其实是否认（残留误判）
        for row in scores["rows"]:
            chk = (row.get("exact_checks") or {}).get("must_not_claim_tamper_proof")
            if chk and not chk.get("passed"):
                pid = row.get("id")
                # 找到原文
                o = next((x for x in outs if (x.get("prompt_id") or x.get("id")) == pid), {})
                txt = (o.get("output") or o.get("text") or "")
                if has_unsupported_claim(txt, TAMPER_PHRASES) is False:
                    residual_fp += 1
                    print(f"    [残留误判] {pid}: scorer 判挂，但原文是否认 → BUG 仍活")
        mark(residual_fp == 0, "无 tamper 残留误判",
             f"残留误判 {residual_fp} 处" if residual_fp else "")
        mark(True, f"真实 tamper 声称 {real_claims} 处（这些判挂是合法的）")
    else:
        mark(None, "tamper 审计（scorer 未跑，仅做原文扫描）",
             f"原文含未否认 tamper 词 {real_claims} 处")

    section("[6] report_summary 必含事实是否真编码（预测可测性）")
    test = read_jsonl(args.dataset)
    rs_names = set()
    for rec in test:
        if (rec.get("task") or rec.get("task_type")) == "report_summary":
            for c in (rec.get("reference_checks") or []):
                nm = c.get("type") or c.get("name") or c.get("check")
                if nm:
                    rs_names.add(nm)
    if rs_names:
        src = args.scorer.read_text(encoding="utf-8")
        not_impl = [n for n in sorted(rs_names) if f'"{n}":' not in src]
        mark(len(not_impl) == 0,
             f"report_summary 的 {len(rs_names)} 个检查名全部被 scorer 实现",
             f"未实现: {not_impl}" if not_impl else "")
        print(f"   检查名: {sorted(rs_names)}")
    else:
        mark(False, "test_50 含 report_summary 样本")

    section("[7] 配置钉死（model + temperature）")
    cfg = args.run_dir / "config.yaml"
    if cfg.exists():
        txt = cfg.read_text(encoding="utf-8")
        m = re.search(r"model:\s*(\S+)", txt)
        t = re.search(r"temperature:\s*([0-9.]+)", txt)
        if args.model_expected:
            mark(m and args.model_expected in (m.group(1) if m else ""),
                 f"model 钉死为 {args.model_expected}",
                 m.group(1) if m else "未找到")
        else:
            mark(bool(m), f"model 字符串存在（{m.group(1) if m else '?'})")
        mark(t and float(t.group(1)) == args.temp_expected,
             f"temperature == {args.temp_expected}",
             f"实际 {t.group(1) if t else '未找到'}")
    else:
        mark(False, "run 内 config.yaml 存在", str(cfg))

    section("总判定")
    if fails:
        print(f"  FAIL ×{fails}，WARN ×{warns} → 证据不足，结论不能成立")
        return 1
    print(f"  PASS（WARN ×{warns}）→ 该 run 的证据链闭合，分数可作为结论")
    return 0


if __name__ == "__main__":
    sys.exit(main())
