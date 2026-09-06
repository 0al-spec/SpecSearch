import json

import pytest

from specsearch.evaluation import read_queries, relevance_metrics


def test_calibration_and_evaluation_are_not_acceptance(tmp_path, package_factory):
    from test_service import FakeEmbedder

    from specsearch.evaluation import calibrate, evaluate
    from specsearch.service import SearchService
    from specsearch.store import Store

    path = tmp_path / "queries.json"
    rows = []
    for split in ("dev", "test"):
        for lang in ("ru", "en"):
            rows.append(
                {
                    "id": f"{split}-{lang}-exact",
                    "group": f"{split}-exact",
                    "split": split,
                    "language": lang,
                    "negative": False,
                    "query": "rtk.proxy",
                    "relevance": {"rtk.proxy": 2},
                }
            )
            for negative in (False, True):
                rows.append(
                    {
                        "id": f"{split}-{lang}-{negative}",
                        "group": f"{split}-{negative}",
                        "split": split,
                        "language": lang,
                        "negative": negative,
                        "query": "unrelated" if negative else "output",
                        "relevance": {} if negative else {"rtk.proxy": 2},
                    }
                )
    path.write_text(json.dumps({"labels_status": "provisional", "queries": rows}))
    store = Store(tmp_path / "store")
    model = FakeEmbedder()
    store.build([package_factory()], model)
    service = SearchService(store, model)
    service.threshold = calibrate(service, path)
    report = evaluate(service, path, "test")
    assert report["quality_accepted"] is False
    assert report["exact_lookup"]["unique_queries"] == 1
    assert len(report["exact_lookup"]["observations"]) == 3
    assert report["metrics"]["hybrid"]["ru"]["positive_queries"] == 1
    assert report["metrics"]["hybrid"]["en"]["positive_queries"] == 1
    threshold = service.threshold.copy()
    for key, value in (
        ("provider_digest", "different-model"),
        ("corpus_digest", "different-corpus"),
        ("split", "test"),
        ("value", float("nan")),
        ("value", True),
        ("value", False),
    ):
        service.threshold = {**threshold, key: value}
        with pytest.raises(ValueError, match="calibration_index_drift"):
            evaluate(service, path, "test")
    service.threshold = threshold
    assert all(o["query_id"].startswith("test") for o in report["observations"])
    assert all(o["query_id"].startswith("dev") for o in report["calibration"]["observations"])
    data = json.loads(path.read_text())
    data["reviewer"] = "changed"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="drift"):
        evaluate(service, path, "test")


def test_metric_math_and_duplicates():
    recall, ndcg = relevance_metrics(["wrong", "good", "good"], {"good": 2})
    assert recall == 1
    assert ndcg == pytest.approx(1 / 1.584962500721156)
    assert relevance_metrics([], {}) == (None, None)


def test_split_leakage(tmp_path):
    path = tmp_path / "queries.json"
    value = {
        "labels_status": "provisional",
        "queries": [
            {"id": str(i), "group": "same", "split": split, "negative": True, "relevance": {}}
            for i, split in enumerate(("dev", "test"))
        ],
    }
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="split_leakage"):
        read_queries(path)


def test_exact_only_cannot_pass_language_gate(tmp_path, package_factory):
    from test_service import FakeEmbedder

    from specsearch.evaluation import evaluate
    from specsearch.service import SearchService
    from specsearch.store import Store

    path = tmp_path / "queries.json"
    path.write_text(
        json.dumps(
            {
                "labels_status": "confirmed",
                "reviewer": "fixture",
                "queries": [
                    {
                        "id": "exact",
                        "group": "exact",
                        "split": "test",
                        "language": "en",
                        "negative": False,
                        "query": "rtk.proxy",
                        "relevance": {"rtk.proxy": 2},
                    }
                ],
            }
        )
    )
    store = Store(tmp_path / "store")
    store.build([package_factory()], FakeEmbedder())
    result = evaluate(SearchService(store, FakeEmbedder()), path, "test")
    assert result["exact_lookup"]["unique_queries"] == 1
    assert result["metrics"]["hybrid"]["all"]["positive_queries"] == 0
    assert not result["targets_met_on_current_labels"]
    assert not result["quality_accepted"]
