import json
import sys

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

from specsearch import cli
from specsearch.api import create_app
from specsearch.embeddings import Embedder, EmbeddingError
from specsearch.ingest import ImportFailure, import_sources, load_yaml, local_package, safe_relative
from specsearch.models import Filters, SearchRequest
from specsearch.service import SearchService
from specsearch.store import Store


def test_real_validation_and_unchanged_source(local_fixture, tmp_path):
    before = {p.name: p.read_bytes() for p in local_fixture.rglob("*.yaml")}
    package = local_package(local_fixture, "test")
    assert before == {p.name: p.read_bytes() for p in local_fixture.rglob("*.yaml")}
    assert package.details["specs"][0]["intent"]["summary"] == "Compress shell output"
    store = Store(tmp_path / "store")
    store.build([package])
    service = SearchService(store)
    assert service.verify(package.record_id)["status"] == "matched_metadata"
    path = local_fixture / "specpm.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest["metadata"]["summary"] = "Changed meaning"
    path.write_text(yaml.safe_dump(manifest))
    assert service.verify(package.record_id)["status"] == "drift"
    path.write_text("broken: [")
    assert service.verify(package.record_id)["status"] == "invalid"


@pytest.mark.parametrize("value", ["../outside", "/absolute", "a\\b", ""])
def test_reject_escape(value):
    with pytest.raises(ImportFailure):
        safe_relative(value)


def test_reject_spec_path_and_bad_package(local_fixture):
    path = local_fixture / "specpm.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest["specs"] = [{"path": "../../secret"}]
    path.write_text(yaml.safe_dump(manifest))
    with pytest.raises(ImportFailure):
        local_package(local_fixture, "test")
    manifest["specs"] = [{"path": "specs/main.spec.yaml"}]
    manifest["metadata"]["id"] = "INVALID ID"
    path.write_text(yaml.safe_dump(manifest))
    with pytest.raises(ImportFailure, match="specpm_invalid"):
        local_package(local_fixture, "test")


def test_depth_and_invalid_source():
    with pytest.raises(ImportFailure):
        load_yaml(("x: " + "[" * 40 + "0" + "]" * 40).encode())
    assert import_sources([{"id": "bad", "kind": "other"}])[1]["errors"]


def test_api_errors_and_unbuilt(tmp_path):
    client = TestClient(create_app(SearchService(Store(tmp_path))))
    assert client.post("/v1/search", json={"query": "x"}).status_code == 503
    assert client.post("/v1/search", content="x").status_code == 415
    assert client.post("/v1/verify", json={"record_id": "missing"}).status_code == 404
    assert client.get("/v1/status", headers={"host": "evil.example"}).status_code == 400


def test_cli_import_build_search_and_failure(local_fixture, tmp_path, monkeypatch, capsys):
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "data_dir": str(tmp_path / "data"),
                "sources": [{"id": "test", "kind": "candidates", "paths": [str(local_fixture)]}],
            }
        )
    )

    def run(*args):
        monkeypatch.setattr(sys, "argv", ["specsearch", "--config", str(config), *args])
        return cli.main()

    assert run("import") == 0
    assert run("index", "build", "--lexical") == 0
    assert run("search", "fixture.proxy", "--source", "candidates") == 0
    assert run("status") == 0
    assert "fixture.proxy" in capsys.readouterr().out
    (local_fixture / "specpm.yaml").unlink()
    assert run("import") == 1
    assert run("import", "--allow-rejected") == 0
    assert run("index", "build", "--lexical") == 0


def test_embedding_unavailable_and_model_missing(tmp_path):
    def unavailable(request):
        raise httpx.ConnectError("offline", request=request)

    embedder = Embedder(
        {}, tmp_path / "cache", httpx.Client(transport=httpx.MockTransport(unavailable))
    )
    with pytest.raises(EmbeddingError):
        embedder.identity()
    embedder.client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"models": []}))
    )
    with pytest.raises(EmbeddingError):
        embedder.identity()


def test_model_mismatch_and_stale_calibration(tmp_path, package_factory):
    from test_service import FakeEmbedder

    store = Store(tmp_path)
    model = FakeEmbedder()
    store.build([package_factory()], model)
    service = SearchService(store, model, {"value": -1, "provider_digest": "wrong"})
    req = SearchRequest(query="output", filters=Filters(source="all"))
    assert service.search(req)["results"][0]["match_strength"] == "uncalibrated"
    model.identity = lambda: {"model": "changed"}
    assert service.search(req)["degraded"]
