# Phase 1: Intent Discovery MVP

Delivery uses one stacked PR per task; no automatic merges. Each PR records
actual checks and limitations in SPECS/reports. Human labels and acceptance
cannot be inferred from agent-generated evaluation results.

- [x] P1-T1 Product Contract and Evaluation Corpus (preparation; labels provisional)
- [x] P1-T2 Safe Import and Search Documents
- [x] P1-T3 Lexical Search Baseline
- [x] P1-T4 Local Embedding Providers
- [x] P1-T5 Hybrid Search API and CLI
- [x] P1-T6 Discovery and Comparison UI
- [x] P1-T7 Retrieval Evaluation and Hardening (measured; quality not accepted)
- [x] P1-T8 Docker Delivery and MVP Exit (delivery verified; PARTIAL exit)

## Exit Decision

Working local prototype delivered. Quality acceptance remains pending; no claim
of production readiness or maintainer-confirmed retrieval quality is made.
See [delivery evidence](reports/P1-T8.md).

- [ ] Maintainer confirms or corrects frozen relevance labels before acceptance.
- [ ] Expand diverse package coverage and hard RU/EN negatives; freeze new holdout.
- [ ] Correct LM Studio negative strong-match behavior using dev data only.
- [ ] Measure model cold start and uncached indexing separately from warm load.

Quality targets: RU/EN Recall@5 >= .85, nDCG@5 >= .75, negative strong-match
rate <= .10; hybrid no worse than BM25. Maintainer-confirmed labels required.
Warm search p95 <= 2s at 1000 packages; synthetic load is performance only.

Out of scope: canonical meaning, publication, installation, package execution,
remote multi-user deployment, generative explanations and automatic scraping.
