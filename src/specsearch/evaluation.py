from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from .models import Filters, SearchRequest, digest, now


def read_queries(path: Path):
    value = json.loads(path.read_text())
    groups = {}
    ids = set()
    for row in value["queries"]:
        if row["id"] in ids or row["split"] not in ("dev", "test"):
            raise ValueError("invalid_query_identity_or_split")
        ids.add(row["id"])
        groups.setdefault(row["group"], set()).add(row["split"])
        if row["negative"] != (not row["relevance"]):
            raise ValueError("negative_label_conflict")
    if any(len(splits) != 1 for splits in groups.values()):
        raise ValueError("split_leakage")
    if value["labels_status"] == "confirmed" and not value.get("reviewer"):
        raise ValueError("confirmed_labels_require_reviewer")
    return value


def calibrate(service, path):
    data = read_queries(path)
    observations = []
    for row in data["queries"]:
        if row["split"] != "dev":
            continue
        result = service.search(
            SearchRequest(
                query=row["query"], mode="vector", top_k=5, filters=Filters(source="candidates")
            )
        )
        hits = result["results"]
        observations.append(
            {
                "query_id": row["id"],
                "negative": row["negative"],
                "score": hits[0]["cosine"] if hits else None,
                "correct": bool(hits and hits[0]["package_id"] in row["relevance"]),
            }
        )
    negatives = [o for o in observations if o["negative"] and o["score"] is not None]
    positives = [o for o in observations if not o["negative"] and o["score"] is not None]
    if not negatives or not positives:
        raise ValueError("calibration_requires_positive_and_negative_vector_cases")
    candidates = {1.000001, -1.0}
    candidates.update(o["score"] + 1e-7 for o in observations if o["score"] is not None)
    eligible = []
    for threshold in candidates:
        fpr = sum(o["score"] >= threshold for o in negatives) / len(negatives)
        tpr = sum(o["score"] >= threshold and o["correct"] for o in positives) / len(positives)
        if fpr <= 0.10:
            eligible.append((tpr, threshold, fpr))
    tpr, threshold, fpr = max(eligible)
    status = service.store.status()
    return {
        "value": threshold,
        "split": "dev",
        "labels_status": data["labels_status"],
        "queries_digest": digest(data),
        "provider_digest": digest(status["provider"]),
        "corpus_digest": status["corpus_digest"],
        "at": now(),
        "dev_positive_strong_correct_rate": tpr,
        "dev_negative_strong_rate": fpr,
        "observations": observations,
    }


def relevance_metrics(package_ids, relevance):
    ids = list(dict.fromkeys(package_ids))[:5]
    relevant = {pid for pid, grade in relevance.items() if grade > 0}
    recall = len(set(ids) & relevant) / len(relevant) if relevant else None
    dcg = sum((2 ** relevance.get(pid, 0) - 1) / math.log2(i + 2) for i, pid in enumerate(ids))
    ideal = sum(
        (2**grade - 1) / math.log2(i + 2)
        for i, grade in enumerate(sorted(relevance.values(), reverse=True)[:5])
    )
    return recall, dcg / ideal if ideal else None


def evaluate(service, path, split):
    data = read_queries(path)
    calibration = service.threshold
    index = service.store.status()
    if calibration and calibration.get("queries_digest") != digest(data):
        raise ValueError("calibration_query_set_drift")
    if calibration and (
        calibration.get("provider_digest") != digest(index.get("provider"))
        or calibration.get("corpus_digest") != index.get("corpus_digest")
        or calibration.get("split") != "dev"
        or not isinstance(calibration.get("value"), (int, float))
        or not math.isfinite(calibration["value"])
    ):
        raise ValueError("calibration_index_drift_or_invalid_threshold")
    observations = []
    for row in data["queries"]:
        if row["split"] != split:
            continue
        for mode in ("lexical", "vector", "hybrid"):
            response = service.search(
                SearchRequest(
                    query=row["query"], mode=mode, top_k=5, filters=Filters(source="candidates")
                )
            )
            if response["snapshot"] != index["snapshot"]:
                raise ValueError("evaluation_snapshot_drift")
            ids = [r["package_id"] for r in response["results"]]
            recall, ndcg = relevance_metrics(ids, row["relevance"])
            strong = any(
                r["match_strength"] in ("strong", "strong_provisional", "exact")
                for r in response["results"]
            )
            observations.append(
                {
                    "query_id": row["id"],
                    "query": row["query"],
                    "exact_lookup": row.get("kind") == "exact"
                    or row["query"] in row["relevance"]
                    or response["mode"] == "exact",
                    "language": row["language"],
                    "mode": mode,
                    "effective_mode": response["mode"],
                    "negative": row["negative"],
                    "packages": ids,
                    "recall5": recall,
                    "ndcg5": ndcg,
                    "negative_strong": strong if row["negative"] else None,
                    "latency_ms": response["latency_ms"],
                    "degraded": response["degraded"],
                }
            )
    metrics = {}
    for mode in ("lexical", "vector", "hybrid"):
        metrics[mode] = {}
        for language in ("ru", "en", "all"):
            rows = [
                o
                for o in observations
                if o["mode"] == mode
                and (language == "all" or o["language"] == language)
                and not o["exact_lookup"]
            ]
            pos, neg = [r for r in rows if not r["negative"]], [r for r in rows if r["negative"]]
            metrics[mode][language] = {
                "positive_queries": len(pos),
                "negative_queries": len(neg),
                "recall5": float(np.mean([r["recall5"] for r in pos])) if pos else None,
                "ndcg5": float(np.mean([r["ndcg5"] for r in pos])) if pos else None,
                "negative_strong_rate": float(np.mean([r["negative_strong"] for r in neg]))
                if neg and mode != "lexical" and calibration
                else None,
                "p95_ms": float(np.percentile([r["latency_ms"] for r in rows], 95))
                if rows
                else None,
            }
    hybrid = metrics["hybrid"]
    targets_met = all(
        hybrid[lang]["recall5"] is not None
        and hybrid[lang]["recall5"] >= 0.85
        and hybrid[lang]["ndcg5"] >= 0.75
        and hybrid[lang]["negative_strong_rate"] is not None
        and hybrid[lang]["negative_strong_rate"] <= 0.10
        for lang in ("ru", "en")
    )
    targets_met &= (
        hybrid["all"]["ndcg5"] is not None
        and metrics["lexical"]["all"]["ndcg5"] is not None
        and hybrid["all"]["ndcg5"] >= metrics["lexical"]["all"]["ndcg5"]
    )
    targets_met &= not any(o["degraded"] for o in observations)
    if service.store.status()["snapshot"] != index["snapshot"]:
        raise ValueError("evaluation_snapshot_drift")
    exact = {}
    for observation in observations:
        if observation["exact_lookup"]:
            exact.setdefault((observation["query"], observation["mode"]), observation)
    return {
        "at": now(),
        "split": split,
        "labels_status": data["labels_status"],
        "queries_digest": digest(data),
        "index": index,
        "calibration": calibration,
        "metrics": metrics,
        "observations": observations,
        "exact_lookup": {
            "language": "neutral",
            "unique_queries": len({query for query, mode in exact}),
            "observations": list(exact.values()),
            "included_in_language_metrics": False,
        },
        "targets_met_on_current_labels": bool(targets_met),
        "quality_accepted": bool(
            targets_met and data["labels_status"] == "confirmed" and split == "test"
        ),
        "performance_scope": "actual corpus only; not a 1000-package load claim",
    }
