# Demo asset provenance

- `demo.gif` / `demo.png`: rendered 2026-10-25 from a curated view of the real
  `python3 demo.py` stdout in `demo.txt` (rc=0, 91 ms).
- `demo.txt`: raw stdout of that run.
- No API calls, no GPU, no third-party package. The script re-scores the
  committed answer files with `copilot/score_copilot_run_v2.py`.
