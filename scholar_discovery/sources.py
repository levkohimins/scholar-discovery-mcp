"""Adapters for two public, read-only scholarly-metadata APIs.

These sources provide genuine public records with shared DOI identifiers.
No access-control bypass, account crawling or personal contact enrichment.
"""
from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = "ScholarDiscoveryDemo/0.1 (public academic metadata; no scraping)"
MAX_RESPONSE_BYTES = 3 * 1024 * 1024

def fetch_json(base: str, params: dict) -> dict:
    url = base + "?" + urlencode(params)
    req = Request(url,headers={"User-Agent":USER_AGENT,"Accept":"application/json"})
    with urlopen(req,timeout=18) as response:
        payload=response.read(MAX_RESPONSE_BYTES+1)
        if len(payload)>MAX_RESPONSE_BYTES:
            raise ValueError("API response exceeded 3 MB safety limit")
        return json.loads(payload)

def crossref(query: str, limit: int = 10) -> list[dict]:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be 1-100")
    d=fetch_json("https://api.crossref.org/works",{
        "query.title":query,"rows":limit,
        "select":"DOI,title,published,URL"
    })
    records=[]
    for item in (d.get("message") or {}).get("items") or []:
        titles=item.get("title") or []
        title=titles[0] if titles else None
        if not title or not item.get("DOI"):continue
        year=None
        parts=(item.get("published") or {}).get("date-parts") or []
        if parts and parts[0]:
            value=parts[0][0]
            if type(value) is int and 1800<=value<=2200:year=value
        records.append({
            "source_id":item["DOI"].lower(),
            "doi":item["DOI"],
            "title":title,
            "year":year
        })
    return records

def openalex(query: str, limit: int = 10) -> list[dict]:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be 1-100")
    d=fetch_json("https://api.openalex.org/works",{
        "search":query,"per-page":limit,
        "select":"id,doi,title,publication_year"
    })
    records=[]
    for item in d.get("results") or []:
        if not item.get("id") or not item.get("title"):continue
        records.append({
            "source_id":item["id"],
            "doi":item.get("doi"),
            "title":item["title"],
            "year":item.get("publication_year") if type(item.get("publication_year")) is int and 1800<=item["publication_year"]<=2200 else None
        })
    return records