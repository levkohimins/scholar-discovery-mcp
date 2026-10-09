"""Conservative multi-source entity reconciliation, using the Python standard library.

DOI is the only automatic cross-source entity key. Similar titles alone never
cause merges: such records remain provisional until a reliable ID is supplied.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS entities (
  id INTEGER PRIMARY KEY,
  doi TEXT UNIQUE,
  title TEXT NOT NULL,
  normalized_title TEXT NOT NULL,
  published_year INTEGER,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observations (
  source TEXT NOT NULL,
  source_id TEXT NOT NULL,
  entity_id INTEGER NOT NULL REFERENCES entities(id),
  title TEXT NOT NULL,
  published_year INTEGER,
  fingerprint TEXT NOT NULL,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  PRIMARY KEY(source, source_id)
);
CREATE TABLE IF NOT EXISTS sync_runs (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  started_at TEXT NOT NULL,
  new_doi_entities INTEGER NOT NULL,
  provisional_entities INTEGER NOT NULL,
  linked_existing INTEGER NOT NULL,
  updated_records INTEGER NOT NULL,
  unchanged_records INTEGER NOT NULL,
  conflicts INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS identity_conflicts (
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES sync_runs(id),
  source TEXT NOT NULL,
  source_id TEXT NOT NULL,
  incoming_doi TEXT,
  existing_doi TEXT,
  reason TEXT NOT NULL,
  observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entities_title ON entities(normalized_title);
CREATE INDEX IF NOT EXISTS idx_observations_entity ON observations(entity_id);
CREATE INDEX IF NOT EXISTS idx_runs_source ON sync_runs(source, id);
"""

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def normalize_doi(raw: str | None) -> str | None:
    """Canonical DOI, or None. This does not try to infer one from a title."""
    if not raw or not isinstance(raw, str):
        return None
    s = unquote(raw.strip()).lower()
    s = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", s)
    s = s.strip().rstrip(".,);")
    if not re.fullmatch(r"10\.\d{4,9}/\S+", s):
        return None
    return s

def normalize_title(title: str) -> str:
    return " ".join(re.findall(r"\w+", title.casefold(), flags=re.UNICODE))

def fingerprint(title: str, doi: str | None, year: int | None) -> str:
    payload = json.dumps([title, doi, year], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def db_connect(db_path: str | Path, *, readonly: bool = False) -> sqlite3.Connection:
    path = Path(db_path).expanduser().resolve()
    if readonly:
        if not path.is_file():
            raise FileNotFoundError(f"Database not found: {path}")
        conn = sqlite3.connect("file:" + quote(str(path)) + "?mode=ro", uri=True, timeout=5)
        conn.execute("PRAGMA query_only=ON")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn

def initialize(db_path: str | Path) -> None:
    with closing(db_connect(db_path)) as conn, conn:
        conn.executescript(SCHEMA)

def clean_input(record: dict) -> tuple[str, str, str | None, int | None]:
    if not isinstance(record, dict):
        raise ValueError("Each input record must be a JSON object")
    source_id = record.get("source_id")
    title = record.get("title")
    if not isinstance(source_id, str) or not source_id.strip() or len(source_id)>500:
        raise ValueError("source_id must be a nonempty string of at most 500 characters")
    if not isinstance(title, str) or not title.strip() or len(title)>1000:
        raise ValueError("title must be a nonempty string of at most 1000 characters")
    year = record.get("year")
    if year is not None and (type(year) is not int or not 1800 <= year <= 2200):
        raise ValueError("year must be an integer from 1800 through 2200")
    return source_id.strip(), title.strip(), normalize_doi(record.get("doi")), year

def ingest(db_path: str | Path, source: str, records: list[dict]) -> dict:
    """Atomic batch ingest. Returns observed new and changed entities.

    Never extrapolate the number of real-world new entities from provisional
    records lacking a DOI. Conflicting identifiers are recorded, not merged.
    """
    if not isinstance(source, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{1,39}", source):
        raise ValueError("source must be 2-40 lowercase letters, digits, underscores or hyphens")
    if not isinstance(records, list) or len(records)>5000:
        raise ValueError("records must be a list with at most 5000 entries per batch")
    prepared = [clean_input(r) for r in records]
    initialize(db_path)
    counters = dict(new_doi_entities=0, provisional_entities=0,
                    linked_existing=0, updated_records=0,
                    unchanged_records=0, conflicts=0)
    timestamp=now_utc()
    with closing(db_connect(db_path)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        run_id = conn.execute(
            "INSERT INTO sync_runs(source,started_at,new_doi_entities,provisional_entities,"
            "linked_existing,updated_records,unchanged_records,conflicts) "
            "VALUES(?,?,0,0,0,0,0,0)", (source,timestamp)
        ).lastrowid
        for source_id,title,doi,year in prepared:
            fp=fingerprint(title,doi,year)
            observed=conn.execute(
                "SELECT o.*, e.doi AS entity_doi FROM observations o "
                "JOIN entities e ON e.id=o.entity_id WHERE o.source=? AND o.source_id=?",
                (source, source_id)
            ).fetchone()
            canonical=conn.execute("SELECT id FROM entities WHERE doi=?", (doi,)).fetchone() if doi else None
            if observed:
                conflicting = (doi and observed["entity_doi"] and observed["entity_doi"]!=doi) or (
                    canonical and canonical["id"]!=observed["entity_id"])
                if conflicting:
                    conn.execute(
                        "INSERT INTO identity_conflicts(run_id,source,source_id,incoming_doi,"
                        "existing_doi,reason,observed_at) VALUES(?,?,?,?,?,?,?)",
                        (run_id,source,source_id,doi,observed["entity_doi"],
                         "source key and DOI point to different entities",timestamp))
                    counters["conflicts"]+=1
                    continue
                entity_id=observed["entity_id"]
                if doi and not observed["entity_doi"]:
                    conn.execute("UPDATE entities SET doi=? WHERE id=?", (doi,entity_id))
                if observed["fingerprint"]==fp:
                    counters["unchanged_records"]+=1
                else:
                    conn.execute(
                        "UPDATE observations SET title=?,published_year=?,fingerprint=?,"
                        "last_seen=? WHERE source=? AND source_id=?",
                        (title,year,fp,timestamp,source,source_id))
                    counters["updated_records"]+=1
                conn.execute(
                    "UPDATE observations SET last_seen=? WHERE source=? AND source_id=?",
                    (timestamp,source,source_id))
                conn.execute("UPDATE entities SET last_seen=? WHERE id=?", (timestamp,entity_id))
            else:
                if canonical:
                    entity_id=canonical["id"]
                    counters["linked_existing"]+=1
                    conn.execute("UPDATE entities SET last_seen=? WHERE id=?", (timestamp,entity_id))
                else:
                    entity_id=conn.execute(
                        "INSERT INTO entities(doi,title,normalized_title,published_year,first_seen,last_seen)"
                        " VALUES(?,?,?,?,?,?)",
                        (doi,title,normalize_title(title),year,timestamp,timestamp)
                    ).lastrowid
                    if doi: counters["new_doi_entities"]+=1
                    else: counters["provisional_entities"]+=1
                conn.execute(
                    "INSERT INTO observations(source,source_id,entity_id,title,published_year,"
                    "fingerprint,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?)",
                    (source,source_id,entity_id,title,year,fp,timestamp,timestamp))
        conn.execute(
            "UPDATE sync_runs SET new_doi_entities=?,provisional_entities=?,"
            "linked_existing=?,updated_records=?,unchanged_records=?,conflicts=? WHERE id=?",
            (*counters.values(),run_id))
    return {"run_id":run_id,"source":source,"processed":len(prepared),**counters}

def stats(db_path: str | Path) -> dict:
    with closing(db_connect(db_path,readonly=True)) as conn:
        out={}
        for table in ("entities","observations","sync_runs","identity_conflicts"):
            out[table]=conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        out["confirmed_doi_entities"]=conn.execute(
            "SELECT count(*) FROM entities WHERE doi IS NOT NULL").fetchone()[0]
        out["provisional_entities"]=out["entities"]-out["confirmed_doi_entities"]
        last=conn.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()
        out["latest_run"]=dict(last) if last else None
        return out

def search(db_path: str | Path, query: str, limit: int = 10) -> list[dict]:
    if not isinstance(query,str) or not query.strip() or len(query)>200:
        raise ValueError("query must be a nonempty string of at most 200 characters")
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("limit must be an integer from 1 to 50")
    normalized=normalize_title(query)
    if not normalized:
        raise ValueError("query must contain searchable characters")
    with closing(db_connect(db_path,readonly=True)) as conn:
        rows=conn.execute(
            "SELECT id,doi,title,published_year,first_seen,last_seen FROM entities "
            "WHERE normalized_title LIKE ? OR doi LIKE ? OR EXISTS "
            "(SELECT 1 FROM observations o WHERE o.entity_id=entities.id AND lower(o.title) LIKE ?) "
            "ORDER BY last_seen DESC,id LIMIT ?",
            ("%"+normalized+"%","%"+query.strip().lower()+"%","%"+query.strip().lower()+"%",limit)
        ).fetchall()
        result=[]
        for row in rows:
            sources=conn.execute(
                "SELECT source,source_id FROM observations WHERE entity_id=? ORDER BY source,source_id",
                (row["id"],)).fetchall()
            result.append({**dict(row),"provisional":row["doi"] is None,
                           "sources":[dict(x) for x in sources]})
        return result