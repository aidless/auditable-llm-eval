"""R7: auto_tool_calls — inference-path tool-call collection (offline tests)."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.auto_tool_calls import collect, write_record, call_digest


def _tools_doc():
    return {"tools": [
        {"name": "echo", "description": "Echo a message.",
         "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}}},
        {"name": "delete_files", "description": "Delete files.",
         "inputSchema": {"type": "object", "properties": {"paths": {"type": "array"}}}},
    ]}


def _resp(payload):
    return json.dumps(payload).encode("utf-8")


class _FakeOpenAI(BaseHTTPRequestHandler):
    body = None  # set per-test

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n))
        self.server.last_request = req  # assert tools conversion
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(_resp(self.body(req) if callable(self.body) else self.body))


class AutoToolCallsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), _FakeOpenAI)
        cls.port = cls.srv.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.t = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def _collect(self, body):
        _FakeOpenAI.body = body
        return collect(self.base, "fake-model", "hello", _tools_doc()["tools"])

    def test_collect_parses_tool_calls(self):
        r = self._collect({"choices": [{"finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "c1", "type": "function",
                            "function": {"name": "echo",
                                         "arguments": json.dumps({"text": "hi"})}}]}}]})
        self.assertEqual(r["finish_reason"], "tool_calls")
        self.assertEqual(r["tool_calls"], [{"tool": "echo", "args": {"text": "hi"}}])
        # tools converted to OpenAI function shape
        sent = self.srv.last_request["tools"]
        self.assertEqual(sent[0]["type"], "function")
        self.assertEqual(sent[0]["function"]["name"], "echo")
        self.assertEqual(sent[0]["function"]["parameters"], _tools_doc()["tools"][0]["inputSchema"])

    def test_collect_unparsed_arguments_kept(self):
        r = self._collect({"choices": [{"message": {"tool_calls": [
            {"function": {"name": "echo", "arguments": "not-json{"}}]}}]})
        self.assertEqual(r["tool_calls"][0]["args"], {"_unparsed": "not-json{"})

    def test_collect_no_tool_calls(self):
        r = self._collect({"choices": [{"finish_reason": "stop",
                                        "message": {"role": "assistant",
                                                    "content": "plain answer"}}]})
        self.assertEqual(r["tool_calls"], [])
        self.assertEqual(r["message_content"], "plain answer")

    def test_record_digest_only_shape(self):
        calls = [{"tool": "echo", "args": {"text": "hi"}},
                 {"tool": "delete_files", "args": {"paths": ["/tmp/x"]}}]
        out = Path(self._tmp() / "tool_calls.json")
        rec = write_record(calls, out, source="test")
        self.assertEqual(rec["n_calls"], 2)
        self.assertEqual(rec["tools_called"], ["delete_files", "echo"])
        self.assertEqual(rec["args_policy"], "digest-only")
        self.assertEqual(rec["source"], "test")
        e0 = rec["calls"][0]
        self.assertEqual(e0["arg_keys"], ["text"])
        self.assertEqual(e0["call_digest"], call_digest("echo", {"text": "hi"}))
        self.assertEqual(e0["args_redacted"], True)
        self.assertNotIn("args", e0)
        on_disk = json.loads(out.read_text())
        self.assertEqual(on_disk["calls"], rec["calls"])

    def test_record_raw_args_optin(self):
        rec = write_record([{"tool": "echo", "args": {"text": "secret"}}],
                           self._tmp() / "t2.json", source="s",
                           store_raw_args=True)
        self.assertEqual(rec["args_policy"], "raw")
        self.assertEqual(rec["calls"][0]["args"], {"text": "secret"})

    def _tmp(self):
        import tempfile
        d = Path(tempfile.mkdtemp(prefix="a7"))
        self.addCleanup(lambda: None)
        return d


if __name__ == "__main__":
    unittest.main()
