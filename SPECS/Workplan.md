# Phase 1: Intent Discovery MVP

Delivery uses one stacked PR per task; no automatic merges. Each PR records
actual checks and limitations in SPECS/reports. Human labels and acceptance
cannot be inferred from agent-generated evaluation results.

- [x] P1-T1 Product Contract and Evaluation Corpus (preparation; labels provisional)
- [ ] P1-T2 Safe Import and Search Documents
- [ ] P1-T3 Lexical Search Baseline
- [ ] P1-T4 Local Embedding Providers
- [ ] P1-T5 Hybrid Search API and CLI
- [ ] P1-T6 Discovery and Comparison UI
- [ ] P1-T7 Retrieval Evaluation and Hardening
- [ ] P1-T8 Docker Delivery and MVP Exit

Quality targets: RU/EN Recall@5 >= .85, nDCG@5 >= .75, negative strong-match
rate <= .10; hybrid no worse than BM25. Maintainer-confirmed labels required.
Warm search p95 <= 2s at 1000 packages; synthetic load is performance only.

Out of scope: canonical meaning, publication, installation, package execution,
remote multi-user deployment, generative explanations and automatic scraping.
