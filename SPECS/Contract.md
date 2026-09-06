# SpecSearch MVP Contract

SpecSearch consumes SpecPM metadata and explicit local candidate directories.
SpecPM remains the validation and exact-lookup substrate. SpecHarvester authors
packages; neither search rank nor validation promotes a candidate to accepted.

Sources are operator configured. Registry imports consume /v0/status, packages
and exact version metadata, never archives. Local imports snapshot bounded,
safe files before running the pinned SpecPM validator. Published search uses
the registry namespace; candidates are opt-in, with a separate combined mode.

Search documents represent package purpose and individual capabilities, with
related interfaces, requirements, scope and constraints. Evidence contents and
README bodies are not indexed. Every snippet retains source field provenance.
Missing fields remain unknown, not assertions of absent requirements/effects.

SQLite FTS5/BM25 and normalized NumPy cosine retrieval each collect 50 document
hits, collapse by version identity and fuse package ranks with RRF k=60.
Exact IDs use an explicit exact path. Source/lifecycle/metadata filters precede
retrieval. Default top-k is ten, at most three snippets per result.

Ollama Nomic is the default embedding provider. LM Studio uses a separate index.
Fingerprint, dimensions, preprocessing and document digests bind vector/cache
identity. Failed builds leave the active immutable snapshot unchanged.

HTTP API: POST /v1/search, GET /v1/packages/{record_id}, POST /v1/verify,
GET /v1/status. Operator CLI owns import/build/evaluate. Local-only by default;
no arbitrary URL or source-path inputs in HTTP search/verify. Raw queries are
not logged. HTML and package content remain inert. Scores are not probabilities.

Provider failure may degrade hybrid to BM25 explicitly; vector-only fails.
Verification distinguishes drift, invalid, unavailable and exact metadata
matches. Matching metadata never establishes runtime compatibility or safety.

Evaluation queries are frozen before ranking. Related RU/EN formulations share
a split. Draft labels require human confirmation; no empirical success claim is
allowed until they are reviewed. Dev selects thresholds; test cannot tune them.
