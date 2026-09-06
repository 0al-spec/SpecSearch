import json
from pathlib import Path


def test_frozen_queries():
    data = json.loads(Path("eval/queries.json").read_text())
    assert data["labels_status"] == "provisional"
    assert data["reviewer"] is None
    assert len(data["queries"]) == 40
    assert sum(q["negative"] for q in data["queries"]) == 10
    for group in {q["group"] for q in data["queries"]}:
        rows = [q for q in data["queries"] if q["group"] == group]
        assert len({q["split"] for q in rows}) == 1
        assert {q["language"] for q in rows} == {"ru", "en"}


def test_frozen_corpus_is_portable():
    data = json.loads(Path("eval/corpus-lock.json").read_text())
    assert len(data["records"]) >= 5
    assert sum("/new/original" in row["path"] for row in data["records"]) == 5
    assert "/Users/" not in json.dumps(data)
