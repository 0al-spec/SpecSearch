# SpecSearch

Local hybrid discovery for SpecPM metadata and SpecHarvester candidates.
BM25 + Nomic embeddings + package-level RRF. Search is not acceptance,
installation, canonical intent mapping or a runtime compatibility guarantee.

## Local Run

Python 3.12, uv 0.8.17+, Node 22+, and a running Ollama embedding service:

```sh
uv sync --frozen --extra dev
npm ci
npm run build
```

Start from `config.example.json`. Configure explicit local package directories
under a `candidates` source (`id`, `kind`, `paths`) or a read-only SpecPM registry
source (`id`, `kind: registry`, `url`). No wildcard repository scraping or archive
downloads. Paths and data_dir are relative to the working directory unless absolute.

For the frozen P56 comparison bundle, prepare the ignored operator config:

```sh
uv run python scripts/local_config.py "$P56_BUNDLE"
uv run specsearch import
uv run specsearch index build
uv run specsearch serve
```

Open http://127.0.0.1:8030/?source=candidates. The registry collection is the
default; candidates and the combined collection require explicit selection.
Use `index build --lexical` for a model-free index. Hybrid then reports BM25
fallback; vector-only refuses to pretend it ran embeddings.

```sh
uv run specsearch search 'compress shell output' --source candidates
uv run specsearch search rtk.shell_output_proxy --source candidates
uv run specsearch status
uv run specsearch calibrate
uv run specsearch evaluate --split test --out .data/evaluation.json
```

Import failures return nonzero and preserve the preceding packages.json. Inspect
import-report.json; `--allow-rejected` explicitly permits a partial import.
Successful imports replace source membership, including deletions. Builds publish
an immutable snapshot atomically; failure leaves the active snapshot untouched.
Old snapshots remain readable and consume disk; remove an unused data workspace
only after stopping its server and retaining needed evidence. No automatic GC.

## LM Studio

Use a separate data_dir and provider config: kind `lmstudio`, URL
`http://127.0.0.1:1234`, model `text-embedding-nomic-embed-text-v1.5`, dimension
768, and artifact_path pointing to the served GGUF. Its hash plus API metadata
bind the configured variant; the API does not attest the operator's file mapping.
Ollama discovers the model digest through /api/tags. Different fingerprints never
share vector indexes. Both APIs must be loopback/local Docker host endpoints.

LM Studio must have the embedding model loaded with at least 1100 context tokens;
otherwise the adapter refuses to risk silent truncation. Document chunks are
bounded to 1024 UTF-8 bytes plus a short prefix; no text is silently discarded.

For P56, `scripts/local_config.py` also accepts `--provider lmstudio --artifact
<GGUF> --data .data/lmstudio --out .data/lmstudio-config.json`; pass that config to
each command with `specsearch --config .data/lmstudio-config.json ...`.

## Docker

The service runs non-root, read-only except its named data volume and temporary
validation copies; model services stay on the host. Docker port is **8031** so
it can coexist with the native server. The P56 bundle mount is read-only.
The compiled UI is versioned; CI rebuilds TypeScript and rejects a stale bundle.
The Docker build therefore needs Python dependencies but no npm downloads.

```sh
mkdir -p .data
ln -s "$P56_BUNDLE" .data/corpus
uv run python scripts/local_config.py "$P56_BUNDLE" --path-prefix /corpus \
  --data /data --provider-url http://host.docker.internal:11434 \
  --registry http://host.docker.internal:8081 --out .data/docker-config.json
docker compose build
docker compose run --rm specsearch import
docker compose run --rm specsearch index build
docker compose up -d
make dev-smoke
```

The combined smoke requires the local SpecPM registry on 8081 (`make dev-reload`
in SpecPM). Omit `--registry` for candidate-only operation. Open
http://127.0.0.1:8031/. `docker compose restart` retains the active index.
Do not expose the service publicly: there is no multi-user authentication.
For containerized LM Studio also bind its served GGUF read-only and configure
artifact_path to that container path. Do not reuse the Ollama volume index.

## API and Verification

POST `/v1/search` accepts query, mode, top_k, and filters: source, source_id,
package, version, license, capability, intent, include_inactive. No arbitrary
URLs, local paths or database selection are accepted. GET `/v1/packages/{id}`
accepts an optional snapshot; POST `/v1/verify` takes record_id and snapshot.
GET `/v1/status` reports index age/counts/provider and lightweight request metrics.

Results cite fields and digests, not generated rationales. `metadata_only`
registry records do not imply full-spec coverage. Candidate and registry identity
remain separate even for identical package IDs. Verification rechecks exact
metadata or the local package and reports drift/invalid/unavailable; it does not
execute code or prove evidence fidelity. Old indexed metadata may be stale.

## Evaluation and Limits

The frozen corpus contains 89 directories, heavily skewed toward n8n. Forty
paired RU/EN queries have fixed splits; ten are negative. Labels are provisional,
not exhaustive maintainer judgments. Do not call quality accepted until reviewed.
`calibrate` reads only dev cases and binds its threshold to model/corpus/query
digests. Test evaluates, never tunes. Provisional thresholds are visibly labeled.

Reports: [evaluation](SPECS/reports/P1-T7.md), [workplan](SPECS/Workplan.md).
The review follow-up evaluation in `SPECS/reports/review-ollama-test.json`
supersedes the original combined language metrics: exact-ID lookup is now
reported separately and never contributes to RU/EN quality gates. The frozen
query corpus itself is unchanged. Calibration from another corpus/model or a
changing snapshot aborts evaluation rather than producing a passing report.
Ollama meets current numeric test targets; LM Studio fails the negative strong
match target. This is not model superiority or population reliability evidence.
The synthetic 1000-package test measures load only, with a warm embedding cache.
No LLM reranker, translation, or generative query expansion is included.

## Checks

### Upstream Project Links

Search results, package details, and comparison expose optional
`upstream: {url, revision?}` separately from registry `source.url` (the spec
archive). Registry imports read this from the **exact version**, never from a
different/latest version. Local imports read only the manifest's unique
`foreignArtifacts` entry with `id: upstream_repository` and
`role: primary_intent_source`. Unsafe or ambiguous local declarations remain
unavailable; invalid registry upstream objects reject that version's import.

Only credential-free HTTP(S) project links without query/fragment are accepted.
Hosts must be DNS/IDNA names or standard IPv4/IPv6 addresses; escaped authority
delimiters and ambiguous numeric hosts are rejected. Unicode control, format,
and surrogate characters are rejected in URLs and revisions.
Revision is a declaration, not proof of a checkout, ownership, or runtime
behavior. No upstream fetching, cloning, or execution occurs. Missing metadata
stays unavailable, not inferred from IDs or archive links. Upstream fields do not
enter ranking documents or embeddings; this change improves result inspection,
not measured retrieval quality.

After the SpecPM registry publishes the optional field, re-run `specsearch
--config <config> import` and `specsearch --config <config> index build`. Existing
snapshots still load but cannot acquire previously omitted metadata without a
rebuild. New snapshots are not rollback-compatible with older binaries that
reject unknown package fields; retain the old snapshot when rolling back. A
registry metadata change also changes record digests, so recalibrate separately
before making quality claims about the new corpus.

```sh
make check
npm run test:e2e
```

Browser E2E requires an imported local P56 index/config and checks desktop/mobile,
comparison, exact verification and hostile text. Set SPECSEARCH_TEST_CORPUS to
the frozen bundle to include the optional 89-package import test. Package code is
never executed. Query bodies are not logged; performance counters reset on restart.
UI identity assets carry a separate notice under static/logos/NOTICE.md.
