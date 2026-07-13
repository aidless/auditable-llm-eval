#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_copilot_eval.py — copilot 评测统一入口（整合 scorer）

流程：
  1) 对 test_50 每题调本地 ollama 生成回答（temperature=0，repeat_penalty 抑制重复）
  2) 写 outputs.jsonl（真实模型输出，审计证据）
  3) 写 verdicts.jsonl —— "假绿"检查器：只查非空 + 长度，不查质量
  4) 调 copilot/score_copilot_run_v2.py 得权威分（reference_checks 真正打分）
  5) 写 config.yaml（钉死 model + temperature，呼应"锁版本"）

输出目录：outputs/llm-lab/datasets/llm_lab_copilot/runs/<run_id>/

用法：
  python eval/run_copilot_eval.py --model copilot-3b-lora-v3c:latest
  python eval/run_copilot_eval.py --model copilot-3b-lora-v3:latest --limit 50
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl"
RUNS = ROOT / "outputs/llm-lab/datasets/llm_lab_copilot/runs"
SCORER = ROOT / "copilot/score_copilot_run_v2.py"
PY = sys.executable


def gen(prompt, model, base_url, temperature, num_predict, repeat_penalty):
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
            "repeat_penalty": repeat_penalty,
            "repeat_last_n": 64,
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/generate",
        data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.loads(r.read().decode("utf-8"))
    return resp.get("response", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="copilot-3b-lora-v3c:latest")
    ap.add_argument("--tests", default=str(DATASET))
    ap.add_argument("--run-dir", default=None, help="不传则自动生成 runs/<ts>-<tag>")
    ap.add_argument("--base-url", default="http://localhost:11434")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--num-predict", type=int, default=400)
    ap.add_argument("--repeat-penalty", type=float, default=1.15)
    ap.add_argument("--verdict-min-len", type=int, default=20)
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 题（冒烟测试）")
    args = ap.parse_args()

    tests = [json.loads(l) for l in Path(args.tests).read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        tests = tests[:args.limit]

    tag = args.model.split(":")[0].replace("/", "_")
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + tag
    run_dir = Path(args.run_dir) if args.run_dir else (RUNS / run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    outputs, verdicts = [], []
    t0 = time.time()
    for i, t in enumerate(tests, 1):
        out = gen(t["prompt"], args.model, args.base_url,
                  args.temperature, args.num_predict, args.repeat_penalty)
        outputs.append({"id": t["id"], "task": t.get("task"),
                        "prompt": t["prompt"], "output": out})
        ok = bool(out.strip()) and len(out.strip()) >= args.verdict_min_len
        verdicts.append({"id": t["id"], "verdict": "pass" if ok else "fail",
                         "reason": "non-empty + length>=%d" % args.verdict_min_len if ok
                         else "empty or too short (live check only)"})
        print(f"[{i}/{len(tests)}] {t['id']} ({t.get('task')}) "
              f"len={len(out.strip())} verdict={'pass' if ok else 'fail'}",
              flush=True)

    (run_dir / "outputs.jsonl").write_text(
        "\n".join(json.dumps(o, ensure_ascii=False) for o in outputs) + "\n", encoding="utf-8")
    (run_dir / "verdicts.jsonl").write_text(
        "\n".join(json.dumps(v, ensure_ascii=False) for v in verdicts) + "\n", encoding="utf-8")

    # 权威 scorer
    out_jsonl = run_dir / "report.jsonl"
    summary_json = run_dir / "summary.json"
    r = subprocess.run(
        [PY, str(SCORER), "--tests", str(args.tests),
         "--predictions", str(run_dir / "outputs.jsonl"),
         "--out", str(out_jsonl), "--summary", str(summary_json)],
        capture_output=True, text=True)
    print("--- scorer stdout ---")
    print(r.stdout)
    if r.returncode != 0:
        print("!! scorer failed:", r.stderr[-1000:], file=sys.stderr)

    # config 钉死
    (run_dir / "config.yaml").write_text(
        f"model: {args.model}\ntemperature: {args.temperature}\n"
        f"num_predict: {args.num_predict}\nverdict_policy: live-nonempty-only\n",
        encoding="utf-8")

    print(f"\nrun -> {run_dir}")
    print(f"elapsed {time.time()-t0:.1f}s | verdicts pass="
          f"{sum(1 for v in verdicts if v['verdict']=='pass')}/{len(verdicts)}")
    if summary_json.exists():
        s = json.loads(summary_json.read_text(encoding="utf-8"))
        print(f"REFERENCE_CHECK_RATE = {s.get('overall_reference_check_rate')} "
              f"(scored {s.get('semantic_scored')}/{s.get('total')}, "
              f"runtime_err {s.get('runtime_errors')})")
        print("by_task:", s.get("by_task"))


if __name__ == "__main__":
    main()
