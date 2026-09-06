import json
from pathlib import Path

import pytest

from specsearch.ingest import ImportFailure, allowed_base, import_sources, load_yaml, read_tree


@pytest.mark.parametrize("text", [b"x: &a [*a]", b"[1,2]", b"x: !!python/object:foo {}"])
def test_hostile_yaml(text):
    with pytest.raises(Exception):
        load_yaml(text)


def test_symlink_and_size(tmp_path, monkeypatch):
    (tmp_path / "escape").symlink_to("/etc/passwd")
    with pytest.raises(OSError):
        read_tree(tmp_path)
    (tmp_path / "escape").unlink()
    (tmp_path / "large").write_bytes(b"12345")
    monkeypatch.setattr("specsearch.ingest.MAX_FILE", 4)
    with pytest.raises(ImportFailure):
        read_tree(tmp_path)


def test_import_errors_are_visible(tmp_path):
    packages, report = import_sources(
        [{"id": "local", "kind": "candidates", "paths": [str(tmp_path)]}]
    )
    assert not packages and report["errors"]


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://example.com", "https://u:p@host"])
def test_forbidden_urls(url):
    with pytest.raises(ImportFailure):
        allowed_base(url)


def test_live_corpus_if_available():
    import os

    bundle = os.environ.get("SPECSEARCH_TEST_CORPUS")
    if not bundle:
        pytest.skip("Explicit local corpus not configured")
    lock = json.loads(Path("eval/corpus-lock.json").read_text())
    paths = [str(Path(bundle) / row["path"]) for row in lock["records"]]
    packages, report = import_sources([{"id": "p56", "kind": "candidates", "paths": paths}])
    assert report["errors"] == []
    assert len(packages) == 89
    assert all(p.source_kind == "candidates" for p in packages)
    assert all(p.provenance["validator"] for p in packages)
