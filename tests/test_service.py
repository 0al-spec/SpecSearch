import numpy as np
from fastapi.testclient import TestClient

from specsearch.api import create_app
from specsearch.models import Filters, SearchRequest
from specsearch.service import SearchService
from specsearch.store import Store


class FakeEmbedder:
    def identity(self):
        return {"model": "fake", "dimension": 2}

    def documents(self, texts):
        return np.array([[1, 0] for _ in texts], dtype=np.float32)

    def query(self, text):
        return np.array([1, 0], dtype=np.float32)


def test_hybrid_and_api(tmp_path, package_factory):
    store = Store(tmp_path)
    store.build([package_factory()], FakeEmbedder())
    service = SearchService(store, FakeEmbedder())
    result = service.search(SearchRequest(query="compress", filters=Filters(source="all")))
    assert result["results"][0]["ranking_score"] == 2 / 61
    assert result["results"][0]["match_strength"] == "uncalibrated"
    client = TestClient(create_app(service))
    assert client.get("/v1/status").json()["packages"] == 1
    payload = {"query": "rtk.proxy", "filters": {"source": "all"}}
    response = client.post("/v1/search", json=payload)
    assert response.json()["mode"] == "exact"
    assert "Content-Security-Policy" in response.headers
    assert "locator" not in client.get("/v1/packages/rtk.proxy").json()
    assert (
        client.post(
            "/v1/search", json=payload, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert client.post("/v1/search", json={"query": "x" * 20000}).status_code == 413
    assert client.get("/v1/packages/missing").status_code == 404


def test_fallback_and_vector_failure(tmp_path, package_factory):
    store = Store(tmp_path)
    store.build([package_factory()])
    client = TestClient(create_app(SearchService(store)))
    payload = {"query": "compress", "filters": {"source": "all"}}
    result = client.post("/v1/search", json=payload).json()
    assert result["degraded"] and result["mode"] == "lexical"
    assert client.post("/v1/search", json={**payload, "mode": "vector"}).status_code == 503


def test_missing_snapshot_returns_not_found(tmp_path, package_factory):
    store = Store(tmp_path)
    store.build([package_factory()])
    client = TestClient(create_app(SearchService(store)))
    missing = "f" * 32
    assert client.get(f"/v1/packages/rtk.proxy?snapshot={missing}").status_code == 404
    assert (
        client.post("/v1/verify", json={"record_id": "rtk.proxy", "snapshot": missing}).status_code
        == 404
    )


def test_missing_candidate_root_is_unavailable(tmp_path, package_factory):
    store = Store(tmp_path / "store")
    store.build([package_factory(locator={"path": str(tmp_path / "deleted")})])
    assert SearchService(store).verify("rtk.proxy")["status"] == "unavailable"
