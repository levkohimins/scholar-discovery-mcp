"""Small authenticated, localhost-only HTTP read API.

Deliberately no POST, no CORS, and no mutable endpoints.
Run behind an appropriate authenticated service only after a security review.
"""
from __future__ import annotations

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from .store import search, stats

def make_handler(db_path: str,secret: str):
    class Handler(BaseHTTPRequestHandler):
        def _send(self,status:int,body:dict):
            payload=json.dumps(body,ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Content-Length",str(len(payload)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if not hmac.compare_digest(
                self.headers.get("Authorization",""),"Bearer "+secret):
                self._send(401,{"error":"Unauthorized"})
                return
            parsed=urlsplit(self.path)
            try:
                if parsed.path=="/health":
                    self._send(200,{"status":"ok"})
                elif parsed.path=="/v1/stats":
                    self._send(200,stats(db_path))
                elif parsed.path=="/v1/search":
                    params=parse_qs(parsed.query)
                    if set(params)-{"q","limit"}:
                        raise ValueError("Unknown search parameters")
                    query=params.get("q",[""])[0]
                    lim=int(params.get("limit",["10"])[0])
                    records=search(db_path,query,lim)
                    self._send(200,{"items":records,"count":len(records)})
                else:
                    self._send(404,{"error":"Not found"})
            except (ValueError,FileNotFoundError) as exc:
                self._send(400,{"error":str(exc)})

        def do_POST(self):
            self._send(405,{"error":"This API is read-only"})

        def log_message(self,fmt,*args):
            # No user-supplied query strings or credentials in access logs.
            pass
    return Handler

def serve(db_path:str,port:int=8099) -> None:
    secret=os.environ.get("SCHOLAR_API_TOKEN")
    if not secret or len(secret)<16:
        raise RuntimeError("Set SCHOLAR_API_TOKEN to a random token of at least 16 characters")
    server=ThreadingHTTPServer(("127.0.0.1",port),make_handler(db_path,secret))
    print(f"Read-only API on http://127.0.0.1:{port}",flush=True)
    try: server.serve_forever()
    finally: server.server_close()
