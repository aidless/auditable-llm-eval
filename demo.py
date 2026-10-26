#!/usr/bin/env python3
"""Re-score the two committed runs with the authoritative reference checks.

No model, no API key, no third-party package. The naive verdicts and the
answers are the committed artifacts; this script only recomputes the score.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from copilot.score_copilot_run_v2 import run  # noqa: E402

TESTS = ROOT / "outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl"
RUNS = ROOT / "outputs/llm-lab/datasets/llm_lab_copilot/runs"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    runs = []
    for run_dir in RUNS.iterdir():
        preds = run_dir / "outputs.jsonl"
        verdicts = run_dir / "verdicts.jsonl"
        summary = run_dir / "summary.json"
        if preds.exists() and verdicts.exists() and summary.exists():
            runs.append(run_dir)

    print("Two committed runs, same 50 tasks, two judges:\n")
    rows = []
    for run_dir in sorted(runs, key=lambda p: json.loads((p / "summary.json").read_text())["overall_reference_check_rate"]):
        naive = load_jsonl(run_dir / "verdicts.jsonl")
        green = sum(1 for v in naive if v.get("verdict") == "pass")
        _, summary = run(str(TESTS), str(run_dir / "outputs.jsonl"), None, None)
        committed = json.loads((run_dir / "summary.json").read_text())
        rate = summary["overall_reference_check_rate"]
        match = rate == committed["overall_reference_check_rate"]
        label = run_dir.name.split("-")[-1]
        rows.append((label, green, len(naive), rate, summary["items_with_unsupported_claims"], match))
        print(f"{label}")
        print(f"  naive checker : {green}/{len(naive)} green ({green / len(naive) * 100:.0f}%)")
        print(f"  authoritative : {rate:.2f}  (committed {committed['overall_reference_check_rate']:.2f}, match={match})")
        print(f"  unsupported   : {summary['items_with_unsupported_claims']}")
        print()

    if rows and all(r[1] == r[2] for r in rows):
        avg = sum(r[3] for r in rows) / len(rows)
        print(f"deception gap : naive 100% green vs authoritative {avg:.0%} — {100 - avg * 100:.0f} points")
    print("\ndemo: 2 runs · 100 answers re-scored · 0 API calls")


if __name__ == "__main__":
    main()
