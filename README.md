# Scholar Discovery: multi-source data reconciliation + read-only MCP

**Repository:** https://github.com/levkohimins/scholar-discovery-mcp

An **independent engineering demonstration** by Levko Burburas.
This is **not a commissioned client project**, a production deployment,
or a claim that millions of records have been processed.

This project discovers public scholarly publications from Crossref and
OpenAlex, reconciles data from the two sources, detects genuinely new
DOI-backed entities, preserves uncertainty, and exposes safe read-only
search tools. It does not collect contact information or bypass access controls.

## Why this project matters

An API integration must distinguish a *new entity* from a second provider
describing the same entity. It must also identify replayed or changed
observations without silently merging uncertain matches.

The engine implements:
- Canonical DOI matching across different provider record IDs.
- Transactional ingestion, stable source keys and idempotent replay.
- Provenance: every entity retains its source observations.
- A conflict ledger for changed or incompatible identifiers.
- Provisional records without DOI: never claimed as verified new entities.
- Bounded database searches, an authenticated HTTP API and two read-only
  MCP stdio tools (search_publications and discovery_stats).
- Automated tests for data integrity, uncertainty and interface security.

Architecture:

~~~text
Crossref API ------+
                   +--> DOI normalizer --> entity resolver --> SQLite
OpenAlex API ------+                             |              |
                                                 |              +--> readonly search API
                                                 +--> conflicts +--> readonly MCP tools
~~~

## Run without installing dependencies (Python 3.12)

Run these commands from the repository directory:

~~~bash
python3 -m scholar_discovery --db demo.sqlite3 init
python3 -m scholar_discovery --db demo.sqlite3 ingest --file examples/crossref_sample.json
python3 -m scholar_discovery --db demo.sqlite3 ingest --file examples/openalex_sample.json
python3 -m scholar_discovery --db demo.sqlite3 stats
python3 -m scholar_discovery --db demo.sqlite3 search 'resilient api' --limit 5
~~~

Fixture records and DOIs are **artificial test data**. The fixture result:
4 entities, 5 observations, 3 confirmed DOI identities, 1 provisional
record and 1 cross-source match.

For live public metadata:

~~~bash
python3 -m scholar_discovery --db live.sqlite3 live --query "distributed tracing" --limit 8
python3 -m scholar_discovery --db live.sqlite3 stats
# Run the same command again to demonstrate idempotency.
python3 -m scholar_discovery --db live.sqlite3 live --query "distributed tracing" --limit 8
~~~

On 2026-10-08, a live 8-record-per-provider run identified 14 confirmed
DOI entities, 1 cross-source match and 1 provisional record. An immediate
rerun showed zero new entities and 16 unchanged source observations.
This is an observed *small demo*, not a large-scale performance benchmark.
Live search rankings and public data can change. If one provider fails,
the CLI marks the run as partial rather than reporting a false zero.

## MCP stdio server (read-only)

~~~bash
python3 -m scholar_discovery --db demo.sqlite3 mcp
~~~

The server speaks newline-delimited JSON-RPC 2.0. Send an initialize
request followed by tools/list and tools/call. Only search_publications
(1-50 results) and discovery_stats exist. No write, send-message,
arbitrary SQL or HTTP fetch tools are exposed. The local subprocess runs
with the calling user's OS permissions.

Example initialize JSON-RPC message:

~~~json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"example","version":"1"}}}
~~~

## Authenticated local HTTP API

~~~bash
export SCHOLAR_API_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
python3 -m scholar_discovery --db demo.sqlite3 api --port 8099
~~~

In another terminal:

~~~bash
curl -H "Authorization: Bearer $SCHOLAR_API_TOKEN" \
  "http://127.0.0.1:8099/v1/search?q=api&limit=10"
curl -H "Authorization: Bearer $SCHOLAR_API_TOKEN" \
  "http://127.0.0.1:8099/v1/stats"
~~~

Only localhost is bound. The API requires a token, has bounded queries,
does not allow writes and does not enable CORS. This is not an
internet-ready deployment: add TLS, service-level access controls,
auditing and a security review before publishing a service.

## Testing

~~~bash
python3 -m unittest discover -s tests -v
~~~

The suite covers cross-source links, genuinely new DOI records,
idempotent replay, conflicting identifiers, conservative no-DOI
handling, validation and atomicity, search bounds, HTTP authentication
and denial of MCP write operations. CI uses local fixtures only,
without external credentials.

## Explicit limitations

- Uses SQLite. PostgreSQL production operations and multi-million-row
  benchmarks are future work, not claimed as completed.
- DOI is an identifier for publications. Resolving people, organisations,
  podcasts or contact details requires a different evidence-based model.
- First/last seen are ingestion timestamps, not proof that a profile or
  contact field is currently valid.
- Does not implement a front end, billing, contact enrichment, complex
  scheduling or production observability.
- Similar titles without DOI are *provisional* and are never silently merged.
- Only official public metadata API endpoints are queried.

Future extensions could add PostgreSQL, a controlled manual resolution
queue, provider budgeting, scheduled refresh, source-specific identity
rules, and tested database backup/restore.
