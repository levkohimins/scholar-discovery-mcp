"""Minimal MCP stdio server exposing ONLY two read-only tools.

Runs as a local stdio subprocess (OS process permissions are the trust boundary).
No write/update tool, SQL execution tool, or outbound messaging tool exists.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from .store import search, stats

PROTOCOL_VERSION = "2025-06-18"

TOOL_DEFINITIONS = [
    {
        "name":"search_publications",
        "description":"Search imported public scholarly works using a safe bounded read-only query.",
        "inputSchema":{
            "type":"object",
            "properties":{
                "query":{"type":"string","minLength":1,"maxLength":200},
                "limit":{"type":"integer","minimum":1,"maximum":50,"default":10}
            },
            "required":["query"],
            "additionalProperties":False
        }
    },
    {
        "name":"discovery_stats",
        "description":"Get source ingest counts, confirmed DOI records, provisional records and conflicts.",
        "inputSchema":{"type":"object","properties":{},"additionalProperties":False}
    }
]

def error(request_id,code,message):
    return {"jsonrpc":"2.0","id":request_id,"error":{"code":code,"message":message}}

def response(request_id,result):
    return {"jsonrpc":"2.0","id":request_id,"result":result}

def handle(message: dict,db_path: str | Path) -> dict | None:
    if not isinstance(message,dict) or message.get("jsonrpc")!="2.0":
        return error(None,-32600,"Invalid JSON-RPC request")
    method=message.get("method")
    req_id=message.get("id")
    if method and method.startswith("notifications/"):
        return None
    if method=="initialize":
        return response(req_id,{
            "protocolVersion":PROTOCOL_VERSION,
            "capabilities":{"tools":{}},
            "serverInfo":{"name":"scholar-discovery-readonly","version":"0.1.0"}
        })
    if method=="ping":
        return response(req_id,{})
    if method=="tools/list":
        return response(req_id,{"tools":TOOL_DEFINITIONS})
    if method!="tools/call":
        return error(req_id,-32601,"Method not found")
    params=message.get("params")
    if not isinstance(params,dict):
        return error(req_id,-32602,"Invalid tool parameters")
    name=params.get("name")
    args=params.get("arguments") or {}
    if not isinstance(args,dict):
        return error(req_id,-32602,"Invalid arguments object")
    try:
        if name=="search_publications":
            if set(args)-{"query","limit"}:
                raise ValueError("Unexpected search arguments")
            result=search(db_path,args.get("query"),args.get("limit",10))
        elif name=="discovery_stats":
            if args:raise ValueError("discovery_stats accepts no arguments")
            result=stats(db_path)
        else:
            return error(req_id,-32602,"Unknown or disallowed tool")
        return response(req_id,{"content":[{"type":"text","text":json.dumps(result,ensure_ascii=False)}]})
    except (ValueError,FileNotFoundError) as exc:
        return response(req_id,{"isError":True,"content":[{"type":"text","text":str(exc)}]})

def serve(db_path: str | Path) -> None:
    for line in sys.stdin:
        try:
            value=json.loads(line)
            result=handle(value,db_path)
        except Exception as exc:
            result=error(None,-32603,"Internal request error")
            print(f"MCP error: {type(exc).__name__}",file=sys.stderr)
        if result is not None:
            print(json.dumps(result,separators=(",",":"),ensure_ascii=False),flush=True)