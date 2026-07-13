# Specs — Contract Layer

> Each JSON in this directory is a **machine-checkable contract**. Each is paired with usage notes (this README). Together they are the source of truth for what the eval pipeline **must** do.

This follows a **Spec-First** discipline (the same pattern used by sibling projects where contracts precede code, JSON serves machines, Markdown serves humans). For the falsifiable chain that motivates this layer, see [`analysis/004-false-green-evidence.md`](../analysis/004-false-green-evidence.md).

---

## 📑 Index

| File | Purpose | Pairing code |
|---|---|---|
| [`scoring-rules.json`](./scoring-rules.json) | 10 `reference_check` types + runtime/overclaim detection rules | `copilot/score_copilot_run_v2.py` |
| [`eval.endpoints.json`](./eval.endpoints.json) | Entry-point CLI contracts (args, outputs, exit codes) for the three eval scripts | `eval/run_copilot_eval.py` · `verify_copilot_run.py` · `copilot/score_copilot_run_v2.py` |
| [`test_50.schema.json`](./test_50.schema.json) | JSON Schema for the benchmark file `test_50.jsonl` | `outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl` |

---

## 🛡️ Maintenance Rules

1. **Spec changes precede code changes.** When you change a check semantics, update `scoring-rules.json` **first**, then change `score_copilot_run_v2.py` to match.
2. **A spec without code is a bug.** If `scoring-rules.json` lists 10 check types but `DISPATCH` only has 8, that's a P0 inconsistency.
3. **A code change without spec is a regression.** If a new check type is added in code, it must appear in `scoring-rules.json` first (or simultaneously).

---

## 🧪 How to verify specs are consistent with code

```bash
# Check DISPATCH in code matches scoring-rules.json check list
python - <<'PY'
import re, json
src = open('copilot/score_copilot_run_v2.py', encoding='utf-8').read()
m = re.search(r'DISPATCH\s*=\s*\{([^}]+)\}', src, re.S)
code_types = set(re.findall(r'"([^"]+)"\s*:\s*\(check_', m.group(1)))
spec = json.load(open('specs/scoring-rules.json', encoding='utf-8'))
spec_types = {c['type'] for c in spec['checks']}
print('code has but spec missing:', code_types - spec_types)
print('spec has but code missing:', spec_types - code_types)
print('PASS' if not (code_types - spec_types or spec_types - code_types) else 'DRIFT')
PY
```

If `DRIFT` is printed, one side is stale — fix it before merging.