#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_release.py — One-shot local validation for a reproducible open-source release.

Runs four checks and exits 0 only if all pass:
  [1] Scorer self-test (if a scorer file with --selftest is discoverable)
  [2] Spec <-> code consistency (DISPATCH keys match specs/scoring-rules.json check types)
  [3] verify_copilot_run.py (or analogous verifier) on every committed run dir
  [4] .gitignore sanity (no .zip / no .safetensors / no .workbuddy in git tree)

Usage:
  python validate_release.py [--repo-root <path>] [--scorer <path>] [--verifier <path>] [--spec <path>] [--runs-glob <pattern>]

Defaults assume the auditable-llm-eval layout (specs/, copilot/, verify_copilot_run.py,
runs/ under outputs/llm-lab/datasets/llm_lab_copilot/runs/).
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Tiny reporting helpers (ASCII-only to avoid PowerShell GBK noise)
# ---------------------------------------------------------------------------

def _section(n: int, title: str) -> None:
    print(f"\n[{n}] {title}")
    print("=" * (4 + len(title)))


def _ok(msg: str) -> None:
    print(f"  [PASS] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def _warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


# ---------------------------------------------------------------------------
# Check 1: scorer --selftest
# ---------------------------------------------------------------------------

def check_scorer_selftest(scorer: Path) -> bool:
    if not scorer.exists():
        _warn(f"scorer not found at {scorer} -- skipping self-test")
        return True
    if not os.access(scorer, os.X_OK):
        # not executable; python invocation still works
        pass
    try:
        r = subprocess.run(
            [sys.executable, str(scorer), "--selftest"],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as e:
        _fail(f"selftest raised: {e}")
        return False
    out = (r.stdout or "") + (r.stderr or "")
    if "SELFTEST: PASS" in out:
        _ok("scorer --selftest passed")
        return True
    _fail(f"selftest did not report PASS; tail:\n{out[-400:]}")
    return False


# ---------------------------------------------------------------------------
# Check 2: spec <-> code DISPATCH consistency
# ---------------------------------------------------------------------------

def check_spec_consistency(spec: Path, scorer: Path) -> bool:
    if not spec.exists():
        _warn(f"spec not found at {spec} -- skipping consistency check")
        return True
    if not scorer.exists():
        _warn(f"scorer not found at {scorer} -- skipping consistency check")
        return True
    try:
        spec_doc = json.loads(spec.read_text(encoding="utf-8"))
        spec_types = {c["type"] for c in spec_doc.get("checks", [])}
        src = scorer.read_text(encoding="utf-8")
        m = re.search(r"DISPATCH\s*=\s*\{([^}]+)\}", src, re.S)
        if not m:
            _warn("could not locate DISPATCH dict in scorer; skipping")
            return True
        code_types = set(re.findall(r'"([^"]+)"\s*:\s*\(check_', m.group(1)))
    except Exception as e:
        _fail(f"parse error: {e}")
        return False
    only_code = code_types - spec_types
    only_spec = spec_types - code_types
    if not only_code and not only_spec:
        _ok(f"DISPATCH ({len(code_types)}) == spec.checks ({len(spec_types)})")
        return True
    if only_code:
        _fail(f"in code but not in spec: {sorted(only_code)}")
    if only_spec:
        _fail(f"in spec but not in code: {sorted(only_spec)}")
    return False


# ---------------------------------------------------------------------------
# Check 3: verifier on every committed run dir
# ---------------------------------------------------------------------------

def check_verifier(runs_glob: str, dataset: Path, scorer: Path, verifier: Path) -> bool:
    if not verifier.exists():
        _warn(f"verifier not found at {verifier} -- skipping")
        return True
    if not dataset.exists():
        _fail(f"dataset not found at {dataset}")
        return False
    import glob
    runs = sorted(glob.glob(runs_glob))
    if not runs:
        _warn(f"no runs found at {runs_glob} -- skipping")
        return True
    all_ok = True
    for run_dir in runs:
        if not (Path(run_dir) / "outputs.jsonl").exists():
            _warn(f"{run_dir}: missing outputs.jsonl; skip")
            continue
        try:
            r = subprocess.run(
                [sys.executable, str(verifier),
                 "--run-dir", run_dir,
                 "--dataset", str(dataset),
                 "--scorer", str(scorer)],
                capture_output=True, text=True, timeout=600,
            )
        except Exception as e:
            _fail(f"{run_dir}: verifier raised {e}")
            all_ok = False
            continue
        out = (r.stdout or "") + (r.stderr or "")
        ok = ("ALL CHECKS PASSED" in out) or ("PASS" in out and r.returncode == 0)
        if ok:
            _ok(f"{Path(run_dir).name}: verifier PASSED (exit={r.returncode})")
        else:
            _fail(f"{Path(run_dir).name}: verifier failed (exit={r.returncode}); tail:\n{out[-400:]}")
            all_ok = False
    return all_ok


# ---------------------------------------------------------------------------
# Check 4: gitignore / git sanity
# ---------------------------------------------------------------------------

def check_gitignore(repo_root: Path) -> bool:
    if not (repo_root / ".git").exists():
        _warn(f"{repo_root} is not a git repo -- skipping gitignore sanity")
        return True
    try:
        r = subprocess.run(
            ["git", "ls-files"],
            cwd=str(repo_root), capture_output=True, text=True, timeout=30,
        )
    except Exception as e:
        _fail(f"git ls-files raised: {e}")
        return False
    tracked = (r.stdout or "").splitlines()
    bad = []
    for line in tracked:
        low = line.lower()
        if low.endswith(".zip"):
            bad.append((line, "release zip should be a Release asset, not a tracked file"))
        elif low.endswith((".safetensors", ".gguf", ".pt", ".pth", ".onnx")):
            bad.append((line, "model weight should not be tracked"))
        elif "/.workbuddy/" in low or low.startswith(".workbuddy/"):
            bad.append((line, "agent scratch dir should not be tracked"))
    if not bad:
        _ok(f"{len(tracked)} tracked files: no zip/weights/.workbuddy present")
        return True
    for path, why in bad:
        _fail(f"{path}: {why}")
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo-root", default=".", help="repo root (default: cwd)")
    ap.add_argument("--scorer", default="copilot/score_copilot_run_v2.py", help="path to scorer script")
    ap.add_argument("--verifier", default="verify_copilot_run.py", help="path to discipline verifier")
    ap.add_argument("--spec", default="specs/scoring-rules.json", help="path to scoring spec JSON")
    ap.add_argument("--runs-glob", default="outputs/llm-lab/datasets/llm_lab_copilot/runs/*/", help="glob for committed run dirs")
    ap.add_argument("--dataset", default="outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl", help="path to test jsonl")
    args = ap.parse_args()

    repo = Path(args.repo_root).resolve()
    scorer = (repo / args.scorer).resolve()
    verifier = (repo / args.verifier).resolve()
    spec = (repo / args.spec).resolve()
    dataset = (repo / args.dataset).resolve()

    print(f"repo:   {repo}")
    print(f"scorer: {scorer}")
    print(f"verify: {verifier}")
    print(f"spec:   {spec}")
    print(f"data:   {dataset}")
    print(f"runs:   {args.runs_glob}")

    results = {}

    _section(1, "Scorer --selftest")
    results["selftest"] = check_scorer_selftest(scorer)

    _section(2, "Spec <-> code consistency")
    results["spec"] = check_spec_consistency(spec, scorer)

    _section(3, "Verifier on every committed run")
    results["verifier"] = check_verifier(args.runs_glob, dataset, scorer, verifier)

    _section(4, "gitignore / git tracked-file sanity")
    results["gitignore"] = check_gitignore(repo)

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    for k, v in results.items():
        print(f"  {k:<12} {'PASS' if v else 'FAIL'}")
    overall = all(results.values())
    print()
    print("OVERALL:", "PASS" if overall else "FAIL")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())