import json
from pathlib import Path

import pytest
import yaml

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


@pytest.mark.parametrize("content", ["inert evidence\n", "- inert\n- evidence\n"])
@pytest.mark.parametrize("suffix", ["yaml", "yml"])
@pytest.mark.parametrize("referenced", [False, True])
def test_non_metadata_yaml_is_inert(local_fixture, content, suffix, referenced):
    name = f"evidence.{suffix}"
    (local_fixture / name).write_text(content)
    if referenced:
        path = local_fixture / "specs/main.spec.yaml"
        spec = yaml.safe_load(path.read_text())
        spec["evidence"][0]["path"] = name
        path.write_text(yaml.safe_dump(spec))
    packages, report = import_sources(
        [{"id": "local", "kind": "candidates", "paths": [str(local_fixture)]}]
    )
    assert report["errors"] == []
    assert len(packages) == 1
    assert name in packages[0].provenance["file_digests"]
    assert all("inert evidence" not in doc.text for doc in packages[0].documents)


@pytest.mark.parametrize("path", ["specpm.yaml", "specs/main.spec.yaml"])
@pytest.mark.parametrize("content", ["scalar", "- list", "x: &a [*a]", "x: " + "[" * 31 + "]" * 31])
def test_declared_metadata_remains_restricted(local_fixture, path, content):
    (local_fixture / path).write_text(content)
    packages, report = import_sources(
        [{"id": "local", "kind": "candidates", "paths": [str(local_fixture)]}]
    )
    assert packages == []
    assert report["errors"][0]["error"] == "ImportFailure"


def test_local_package_still_requires_specpm_validation(local_fixture):
    path = local_fixture / "specpm.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest["kind"] = "NotSpecPackage"
    path.write_text(yaml.safe_dump(manifest))
    packages, report = import_sources(
        [{"id": "local", "kind": "candidates", "paths": [str(local_fixture)]}]
    )
    assert packages == []
    assert report["errors"][0]["detail"].startswith("specpm_invalid:")


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
