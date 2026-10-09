# Portfolio case: Public Data Discovery and Reconciliation

**Category:** Independent engineering demonstration, October 2026.

**Customer:** None. Created as a genuine runnable technical demonstration,
not as a fabricated paid customer case.

**Problem:** Independent data providers describe overlapping entities
with different IDs. Repeated imports can create duplicates, undetected
conflicts and misleading new-record statistics.

**Solution:** A small Python data pipeline that consumes real public
publication metadata from Crossref and OpenAlex, normalizes DOI identity,
separates new records from replayed and changed observations, logs
conflicts, and exposes bounded read-only search through an authenticated
HTTP API and MCP stdio tools.

**Reliability:** Transactional ingestion, conservative identity decisions
(no fuzzy title merging), reproducible fixture tests, source provenance,
and read-only access boundaries.

**Demonstration:** On 2026-10-08, live 8+8 public records produced
14 confirmed DOI identities, 1 matched cross-source DOI, 1 provisional
record. A repeat run produced zero additional entities and 16 unchanged
observations. These are deliberately small test numbers.

**Technology:** Python 3.12, SQLite, Crossref REST, OpenAlex REST, MCP
JSON-RPC stdio, authenticated localhost HTTP, standard-library tests.

**Scope note:** NOT a commissioned client delivery, a PostgreSQL
production system, or evidence of multi-million-record throughput.

**Repository:** https://github.com/levkohimins/scholar-discovery-mcp
