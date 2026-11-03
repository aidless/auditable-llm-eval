"""eval/run_copilot_eval.py -- tool-call evidence must not leak secrets.

A run dir is meant to be committable evidence. Tool-call args can carry tokens,
message bodies or chat content, so the default policy is digest-only: keys and a
digest, never the values. Raw args are an explicit local-debug opt-in.
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "_test_runner", REPO / "eval" / "run_copilot_eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


runner = _load_runner()

SECRET = "sk-live-SECRET-DO-NOT-PERSIST"


class TestToolCallRedaction(unittest.TestCase):
    def _write(self, store_raw):
        d = Path(tempfile.mkdtemp())
        log = d / "calls.jsonl"
        log.write_text(
            json.dumps({"tool": "send_message",
                        "args": {"body": SECRET, "channel": "#general"}}) + "\n"
            + json.dumps({"tool": "get_weather", "args": {"city": "Beijing"}}) + "\n",
            encoding="utf-8")
        runner.write_tool_calls(d, str(log), store_raw_args=store_raw)
        return json.loads((d / "tool_calls.json").read_text(encoding="utf-8"))

    def test_default_never_persists_raw_args(self):
        record = self._write(store_raw=False)
        blob = json.dumps(record)
        self.assertNotIn(SECRET, blob)
        self.assertEqual(record["args_policy"], "digest-only")
        for call in record["calls"]:
            self.assertNotIn("args", call)
            self.assertTrue(call["args_redacted"])
            self.assertIn("arg_keys", call)
            self.assertIn("call_digest", call)

    def test_digest_still_identifies_the_call(self):
        record = self._write(store_raw=False)
        digs = [c["call_digest"] for c in record["calls"]]
        self.assertTrue(all(len(d) == 64 for d in digs))
        self.assertEqual(len(set(digs)), 2)  # distinct args -> distinct digests

    def test_raw_args_only_with_explicit_opt_in(self):
        record = self._write(store_raw=True)
        self.assertEqual(record["args_policy"], "raw")
        self.assertIn(SECRET, json.dumps(record))
        for call in record["calls"]:
            self.assertIn("args", call)

    def test_absent_call_log_writes_nothing(self):
        d = Path(tempfile.mkdtemp())
        runner.write_tool_calls(d, None)
        self.assertFalse((d / "tool_calls.json").exists())


if __name__ == "__main__":
    unittest.main()
