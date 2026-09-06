# Stack review follow-up

Corrections are delivered above PR #9 without rewriting the nine reviewed
branches. Source review threads reference this integration PR; their historical
heads are not retroactively fixed. Merge the complete corrected stack, not an
intermediate release assembled from only its lower PRs.

## Disposition

- #1: exact-ID lookup is deduplicated separately and excluded from RU/EN metrics.
  Frozen queries remain unchanged. The CLI target was already supplied by #5;
  delivery tests now exercise its import and the served static bundle.
- #2: registry failures are reported per exact version; later versions still
  import. Registry capabilities each have their own document. Non-metadata YAML
  remains inert; declared manifests/specs still receive bounded validation.
- #3: acronym token boundaries split HTTPClient/JSONParser. Once publication
  starts, interruption cannot delete the possibly published DB. A failure may
  leave an unreferenced DB, which is safer than deleting an active snapshot.
- #4: provider locality uses parsed hostnames, including IPv6 loopback. GGUF
  digest caching uses device/inode/size/mtime/ctime and checks changes while hashing.
- #5: absent snapshot IDs map to not-found; deleted source roots are unavailable.
  Malformed provider shapes raise controlled embedding errors, preserving hybrid
  fallback and vector-only failure semantics.
- #6: app.js was already versioned in #8. Pending comparison slots now enforce
  the three-package limit and cancellation; registry metadata feeds comparison.
- #7: calibration binds to active provider/corpus and dev split; non-finite
  thresholds or snapshot changes reject evaluation.
- #8: Docker readiness requires an active snapshot, not just HTTP 200.

## Evaluation

Re-ran Ollama test evaluation against the existing 89-package candidate snapshot.
Natural-language positives: five per language; negatives: three per language.
Recall@5 RU/EN: 1.00/1.00. nDCG@5 RU/EN: .926/1.00. Negative strong-match rate:
0/0. Three unique exact queries are recorded outside language metrics. Numeric
targets pass but quality_accepted remains false because labels are provisional.

LM Studio rerun did not complete: /api/v0/models reported the embedding model
as not-loaded. No replacement successful LM report is claimed. Adapter shape,
cache and failure behavior is covered by deterministic tests.

## Validation

- make check: Ruff lint/format passed; 109 passed, one optional corpus skip,
  coverage 93.84%, two dependency deprecation warnings.
- Explicit SPECSEARCH_TEST_CORPUS ingest suite: 26 passed, including all 89
  frozen local package directories.
- npm run build and Docker browser E2E: 15 passed, including delayed comparison
  response/cancellation cases and registry/candidate comparison at both widths.
- uv build --wheel: CLI, app.js and self-hosted fonts included in the wheel.
- Docker reload healthy; reimport: 99 records, zero errors. Rebuild: 438 documents
  with separate registry capabilities, snapshot 474045b97d6a4fe793f3d6521f183b25.
  make dev-smoke passed exact registry/candidate verification and hybrid search.
- A fresh read-only agent reviewed the integrated core fixes and found no new
  blockers; main agent reviewed the contributed diffs and ran the full gate.

Three bounded agents edited disjoint import, storage/provider, and UI scopes.
Main owned service/evaluation/readiness fixes, integration, deployment, commits,
PR publication and thread disposition. No agent mutated Git or registry state.
