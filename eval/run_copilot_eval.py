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
import hashlib
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
    ap.add_argument("--tool-allowlist", default=None,
                    help="本次 run 允许 agent 使用的工具定义 JSON（mcp-guard 形状）；"
                         "传入则把 name + digest 钉成 tool_manifest.json，供 trace 交叉校验")
    ap.add_argument("--tool-calls", default=None,
                    help="本次 run 实际发生的工具调用日志（JSONL 或 JSON 数组，"
                         "每项 {tool, args, ...}）；传入则落成 tool_calls.json，"
                         "由 trace 校验『实际调用的』是否都在白名单内")
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

    write_tool_manifest(run_dir, args.tool_allowlist)
    write_tool_calls(run_dir, args.tool_calls)

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


def write_tool_manifest(run_dir: Path, allowlist_path: str | None):
    """Pin "which tools this run was allowed to use" as a run-dir evidence file.

    Digests come from mcp-guard when it is importable (the same digest function
    the BEFORE gate pins), otherwise from a local sha256 over the canonical JSON
    so the manifest is still reproducible without mcp-guard on the path. When no
    allowlist is given, no file is written -- an absent manifest means "this run
    did not declare a tool allowlist", not an empty one.
    """
    if not allowlist_path:
        return
    src = Path(allowlist_path)
    data = json.loads(src.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("tools", [data])
    digest_fn = _import_guard_digest()
    tools = []
    for tool in data:
        digest = digest_fn(tool) if digest_fn else hashlib.sha256(
            json.dumps(tool, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        tools.append({"name": tool.get("name", "?"), "digest": digest})
    manifest = {
        "source": str(src.resolve()),
        "n_tools": len(tools),
        "tools": tools,
        "digest_algo": "mcp-guard.digest_tool" if digest_fn else "sha256(canonical-json)",
    }
    (run_dir / "tool_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"[tool-allowlist] pinned {len(tools)} tool(s) -> {run_dir / 'tool_manifest.json'}")


def _import_guard_digest():
    try:
        from guard.scan import digest_tool  # type: ignore
        return digest_tool
    except Exception:
        return None


def _call_digest(tool: str, cargs: dict) -> str:
    """Stable digest of ONE observed tool call: identity + canonical arguments.

    Distinct from the definition digest in tool_manifest.json: this pins what was
    actually invoked (name + args), so the trace can report both "which tool was
    allowed" and "which tool was called with which arguments".
    """
    payload = json.dumps({"tool": tool, "args": cargs or {}},
                         sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_tool_calls(run_dir: Path, calls_path: str | None):
    """Pin the OBSERVED tool calls as a run-dir evidence file.

    A call log is an observation, not a declaration -- the runner cannot invent
    it, so it is fed in from whatever actually observed the calls (an MCP proxy,
    an agent harness). Accepts JSONL (one {tool, args, ...} per line) or a JSON
    array. When not given, no file is written: absent means "no call log was
    supplied for this run", which is the common case and is not an error.
    """
    if not calls_path:
        return
    src = Path(calls_path)
    raw = src.read_text(encoding="utf-8")
    stripped = raw.strip()
    if src.suffix == ".jsonl" or ("\n" in stripped and not stripped.startswith("[")):
        calls_in = [json.loads(line) for line in raw.splitlines() if line.strip()]
    else:
        calls_in = json.loads(stripped)
    by_tool: dict[str, list[dict]] = {}
    for i, call in enumerate(calls_in):
        tool = call.get("tool") or call.get("name") or "?"
        cargs = call.get("args")
        if cargs is None and isinstance(call.get("arguments"), dict):
            cargs = call["arguments"]
        entry = {"seq": i, "tool": tool, "args": cargs,
                 "call_digest": _call_digest(tool, cargs)}
        by_tool.setdefault(tool, []).append(entry)
    record = {
        "source": str(src.resolve()),
        "n_calls": len(calls_in),
        "n_tools_called": len(by_tool),
        "tools_called": sorted(by_tool),
        "calls": [e for lst in by_tool.values() for e in lst],
    }
    (run_dir / "tool_calls.json").write_text(
        json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"[tool-calls] recorded {len(calls_in)} call(s) over "
          f"{len(by_tool)} tool(s) -> {run_dir / 'tool_calls.json'}")


if __name__ == "__main__":
    main()
