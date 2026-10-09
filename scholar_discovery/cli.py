"""CLI for fixtures, live public discovery, inspection and read-only services."""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from . import sources
from . import store
from . import mcp
from . import http_api

def create_parser():
    p=argparse.ArgumentParser(prog="scholar-discovery")
    p.add_argument("--db",default=os.environ.get("SCHOLAR_DB","./scholar-demo.sqlite3"),
                   help="Local SQLite database path (default ./scholar-demo.sqlite3)")
    sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("init",help="Create an empty database")
    ingest=sub.add_parser("ingest",help="Ingest a batch of public metadata from a JSON file")
    ingest.add_argument("--file",type=Path,required=True)
    ingest.add_argument("--source",help="Override source in the JSON envelope")
    live=sub.add_parser("live",help="Query Crossref and OpenAlex (public endpoints, no auth)")
    live.add_argument("--query",required=True)
    live.add_argument("--limit",type=int,default=10)
    sr=sub.add_parser("search",help="Bounded read-only title or DOI search")
    sr.add_argument("query")
    sr.add_argument("--limit",type=int,default=10)
    sub.add_parser("stats",help="Show discovery and conflict metrics")
    sub.add_parser("mcp",help="Run local read-only MCP stdio server")
    api=sub.add_parser("api",help="Run authenticated localhost read API")
    api.add_argument("--port",type=int,default=8099)
    return p

def main(argv=None):
    args=create_parser().parse_args(argv)
    try:
        if args.command=="init":
            store.initialize(args.db)
            result={"created":str(Path(args.db).resolve())}
        elif args.command=="ingest":
            payload=json.loads(args.file.read_text(encoding="utf-8"))
            if isinstance(payload,dict):
                source=args.source or payload.get("source")
                records=payload.get("records")
            else:
                source=args.source
                records=payload
            result=store.ingest(args.db,source,records)
        elif args.command=="live":
            if not 1<=args.limit<=100:
                raise ValueError("limit must be between 1 and 100")
            store.initialize(args.db)
            result={}
            failed=0
            for name,fn in (("crossref",sources.crossref),("openalex",sources.openalex)):
                try:
                    records=fn(args.query,args.limit)
                    result[name]=store.ingest(args.db,name,records)
                except Exception as exc:
                    failed+=1
                    result[name]={"error":str(exc)}
            result["status"]="partial" if failed else "ok"
            print(json.dumps(result,indent=2,ensure_ascii=False))
            return 1 if failed else 0
        elif args.command=="search":
            result=store.search(args.db,args.query,args.limit)
        elif args.command=="stats":
            result=store.stats(args.db)
        elif args.command=="mcp":
            mcp.serve(args.db);return 0
        elif args.command=="api":
            http_api.serve(args.db,args.port);return 0
        else:
            raise ValueError("Unknown command")
        print(json.dumps(result,indent=2,ensure_ascii=False))
        return 0
    except (ValueError,FileNotFoundError,RuntimeError) as exc:
        print(f"Error: {exc}",file=sys.stderr)
        return 2
