from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import numpy as np

from .embeddings import EmbeddingError
from .ingest import local_package, registry_json, registry_package
from .models import SearchRequest, now
from .store import Store, collapse, predicate, tokens


class SearchService:
    def __init__(self, store: Store, embedder=None, threshold=None):
        self.store, self.embedder, self.threshold = store, embedder, threshold
        self.requests = 0
        self.degraded_count = 0
        self.last_latency_ms = None

    def vector(self, query, filters, snapshot):
        with self.store.connect(snapshot) as con:
            meta = json.loads(
                con.execute("SELECT value FROM metadata WHERE key='status'").fetchone()[0]
            )
            if self.embedder is None or meta["provider"] is None:
                raise EmbeddingError("vector_index_unavailable")
            if self.embedder.identity() != meta["provider"]:
                raise EmbeddingError("model_fingerprint_mismatch")
            vector = self.embedder.query(query)
            if self.embedder.identity() != meta["provider"]:
                raise EmbeddingError("model_fingerprint_mismatch")
            where, args = predicate(filters)
            rows = con.execute(
                f"""SELECT d.record,d.payload,v.vector
                FROM vectors v JOIN docs d ON d.id=v.id JOIN packages p ON p.id=d.record
                WHERE {where} ORDER BY d.id""",
                args,
            ).fetchall()
        if not rows:
            return []
        matrix = np.array([np.frombuffer(row[2], dtype=np.float32) for row in rows])
        if matrix.shape[1] != len(vector) or not np.isfinite(matrix).all():
            raise EmbeddingError("corrupt_vector_index")
        scores = matrix @ vector
        order = np.argsort(-scores, kind="stable")[:50]
        return [
            {"record_id": rows[i][0], "document": json.loads(rows[i][1]), "score": float(scores[i])}
            for i in order
        ]

    def search(self, request: SearchRequest):
        start = time.perf_counter()
        snapshot = self.store.active()
        with self.store.connect(snapshot) as con:
            metadata = json.loads(
                con.execute("SELECT value FROM metadata WHERE key='status'").fetchone()[0]
            )
        query = request.query.strip()
        if not query:
            raise ValueError("empty_query")
        exact = self.store.exact(query, request.filters, snapshot)
        lexical, vector, error = [], [], None
        if exact:
            ids = [p.record_id for p in exact][: request.top_k]
            scores = {rid: None for rid in ids}
            effective = "exact"
        else:
            if request.mode in ("lexical", "hybrid"):
                lexical = self.store.lexical(query, request.filters, snapshot)
            if request.mode in ("vector", "hybrid"):
                try:
                    vector = self.vector(query, request.filters, snapshot)
                except (EmbeddingError, httpx.HTTPError, OSError, KeyError, ValueError):
                    if request.mode == "vector":
                        raise EmbeddingError("vector_search_unavailable") from None
                    error = "embedding_unavailable_or_index_mismatch"
            ranks = [collapse(hits) for hits in (lexical, vector) if hits]
            scores = {}
            for ranked in ranks:
                for rank, rid in enumerate(ranked, 1):
                    scores[rid] = scores.get(rid, 0) + 1 / (60 + rank)
            ids = sorted(scores, key=lambda rid: (-scores[rid], rid))[: request.top_k]
            effective = "lexical" if error else request.mode
        results = []
        query_tokens = set(tokens(query))
        for rank, rid in enumerate(ids, 1):
            package = self.store.package(rid, snapshot)
            hits = [h for h in lexical + vector if h["record_id"] == rid]
            snippets = []
            fields = [f for hit in hits for f in hit["document"]["fields"]]
            if not fields:
                fields = [f.model_dump() for doc in package.documents for f in doc.fields]
            fields.sort(key=lambda f: -len(query_tokens.intersection(tokens(f["text"]))))
            seen = set()
            for field in fields:
                if field["path"] not in seen:
                    snippets.append({"path": field["path"], "text": field["text"][:600]})
                    seen.add(field["path"])
                if len(snippets) == 3:
                    break
            cosine = next((h["score"] for h in vector if h["record_id"] == rid), None)
            strength = "exact" if exact else "uncalibrated"
            if not exact and cosine is not None and self.threshold is not None:
                strength = "strong" if cosine >= self.threshold else "weak"
            results.append(
                {
                    "record_id": rid,
                    "package_id": package.package_id,
                    "version": package.version,
                    "name": package.name,
                    "summary": package.summary,
                    "license": package.license,
                    "source_id": package.source_id,
                    "source": package.source_kind,
                    "metadata_only": package.metadata_only,
                    "digest": package.digest,
                    "yanked": package.yanked,
                    "deprecated": package.deprecated,
                    "rank": rank,
                    "ranking_score": scores[rid],
                    "cosine": cosine,
                    "match_strength": strength,
                    "snippets": snippets,
                }
            )
        elapsed = (time.perf_counter() - start) * 1000
        self.requests += 1
        self.degraded_count += bool(error)
        self.last_latency_ms = elapsed
        return {
            "snapshot": snapshot,
            "indexed_at": metadata["created_at"],
            "provider": metadata["provider"],
            "mode": effective,
            "degraded": bool(error),
            "diagnostic": error,
            "latency_ms": elapsed,
            "results": results,
            "authority": "discovery_only",
        }

    def verify(self, rid, snapshot=None):
        old = self.store.package(rid, snapshot)
        try:
            if old.source_kind == "candidates":
                fresh = local_package(Path(old.locator["path"]), old.source_id)
            else:
                base = old.locator["registry"]
                with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
                    status = registry_json(client, base, "/v0/status")
                    fresh = registry_package(
                        client, base, old.source_id, old.package_id, old.version, status
                    )
            state = "drift" if fresh.digest != old.digest else "matched_metadata"
            if fresh.yanked or fresh.deprecated:
                state = "lifecycle_blocked"
            return {
                "status": state,
                "expected_digest": old.digest,
                "observed_digest": fresh.digest,
                "observed_at": now(),
                "source": old.source_kind,
                "publication_authorized": False,
                "runtime_verified": False,
            }
        except (OSError, httpx.HTTPError):
            return {"status": "unavailable", "observed_at": now()}
        except (ValueError, KeyError, TypeError):
            return {"status": "invalid", "observed_at": now()}

    def status(self):
        return {
            **self.store.status(),
            "requests": self.requests,
            "degraded_requests": self.degraded_count,
            "last_latency_ms": self.last_latency_ms,
            "query_logging": False,
            "authority": "discovery_only",
        }
