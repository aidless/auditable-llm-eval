"""R7（auditable-llm-eval 侧）：从推理路径自动采集 tool_calls。

runner 的 --tool-calls 是「喂入观测证据」；本模块补上另一半：直接调
OpenAI 兼容 /v1/chat/completions（Magpie 网关 127.0.0.1:3425 等云端 provider）
带 tools 定义，解析响应里的 message.tool_calls，产出与 write_tool_calls
完全同形的 run-dir 记录（arg_keys + call_digest，默认 digest-only）。

独立模块、不改动 run_copilot_eval.py——那个文件当前有另一会话的未提交
改动（2026-11-08 00:20），runner 内 3 行接线（--auto-tool-calls）留作
显式待办，避免同文件纠缠。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path


def call_digest(tool: str, cargs: dict) -> str:
    """与 run_copilot_eval._call_digest 同形：tool + canonical args 的 sha256。"""
    payload = json.dumps({"tool": tool, "args": cargs or {}},
                         sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_tool_calls(message: dict) -> list[dict]:
    """OpenAI 协议：message.tool_calls[].function.{name, arguments}，
    arguments 是 JSON 字符串；解析失败保留原始串（不静默丢参）。"""
    out = []
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function") or {}
        name = fn.get("name") or "?"
        raw_args = fn.get("arguments")
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args) if raw_args.strip() else {}
            except json.JSONDecodeError:
                args = {"_unparsed": raw_args}
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            args = {}
        out.append({"tool": name, "args": args})
    return out


def collect(base_url: str, model: str, prompt: str, tools: list[dict],
            api_key: str | None = None, timeout: int = 180) -> dict:
    """一次 chat completions 推理 + tool_calls 解析。

    tools 是 mcp-guard 形状的定义列表（[{name, description, inputSchema}]），
    发出去之前转成 OpenAI function 形状；响应里的 message/finish_reason 原样带回。
    """
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "tools": [{"type": "function",
                   "function": {"name": t.get("name", "?"),
                                "description": t.get("description", ""),
                                "parameters": t.get("inputSchema") or {"type": "object", "properties": {}}}}
                  for t in tools],
        "tool_choice": "auto",
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read().decode("utf-8"))
    choice = (resp.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    return {
        "finish_reason": choice.get("finish_reason"),
        "message_content": message.get("content") or "",
        "tool_calls": _parse_tool_calls(message),
    }


def write_record(calls: list[dict], out_path: Path, source: str,
                 store_raw_args: bool = False) -> dict:
    """与 run_copilot_eval.write_tool_calls 同形的落盘记录。"""
    by_tool: dict[str, list[dict]] = {}
    for i, call in enumerate(calls):
        tool = call.get("tool") or "?"
        cargs = call.get("args")
        if not isinstance(cargs, dict):
            cargs = {}
        entry = {
            "seq": i,
            "tool": tool,
            "arg_keys": sorted(cargs),
            "call_digest": call.get("call_digest") or call_digest(tool, cargs),
        }
        if store_raw_args:
            entry["args"] = cargs
        else:
            entry["args_redacted"] = True
        by_tool.setdefault(tool, []).append(entry)
    record = {
        "source": source,
        "n_calls": len(calls),
        "n_tools_called": len(by_tool),
        "tools_called": sorted(by_tool),
        "args_policy": "raw" if store_raw_args else "digest-only",
        "calls": [e for lst in by_tool.values() for e in lst],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False,
                                   indent=2) + "\n", encoding="utf-8")
    return record


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="auto-collect tool_calls from an OpenAI-compatible chat endpoint (R7)")
    ap.add_argument("--base-url", required=True, help="e.g. http://127.0.0.1:3425")
    ap.add_argument("--model", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--tools", required=True,
                    help="mcp-guard 形状的工具定义 JSON（数组或 {tools:[...]})")
    ap.add_argument("--out", required=True, help="tool_calls.json 输出路径")
    ap.add_argument("--api-key-env", default=None,
                    help="从哪个环境变量读 Bearer token（不传则匿名）")
    ap.add_argument("--store-raw-args", action="store_true")
    args = ap.parse_args(argv)

    doc = json.loads(Path(args.tools).read_text(encoding="utf-8"))
    tools = doc["tools"] if isinstance(doc, dict) else doc
    api_key = os.environ.get(args.api_key_env) if args.api_key_env else None

    t0 = time.time()
    result = collect(args.base_url, args.model, args.prompt, tools,
                     api_key=api_key)
    record = write_record(result["tool_calls"], Path(args.out),
                          source=f"auto-collect {args.base_url} model={args.model}",
                          store_raw_args=args.store_raw_args)
    print(f"[auto-tool-calls] finish={result['finish_reason']} "
          f"n_calls={record['n_calls']} tools={record['tools_called']} "
          f"elapsed={time.time()-t0:.1f}s -> {args.out}", flush=True)
    if result["message_content"]:
        print(f"[auto-tool-calls] message: {result['message_content'][:200]}")
    return 0


import os  # noqa: E402  (main() 用到；置于文件尾部避免顶部 import 噪音)

if __name__ == "__main__":
    raise SystemExit(main())
