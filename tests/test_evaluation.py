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
