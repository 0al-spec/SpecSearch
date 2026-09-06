import json

import httpx
import numpy as np
import pytest

from specsearch.embeddings import Embedder, EmbeddingError, chunks, normalized


def test_chunks_and_norms():
    text = "Привет мир " * 200
    split = chunks(text)
    assert "".join(split) == text
    assert all(len(part.encode()) <= 1024 for part in split)
    for values in ([[0, 0]], [[float("nan"), 1]], [[1]], [[float("inf"), 1]]):
        with pytest.raises(EmbeddingError):
            normalized(values, 2)


def test_provider_cache_fingerprint_and_prefix(tmp_path):
    calls = []
    artifact = ["abc"]

    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "nomic", "digest": artifact[0]}]})
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(200, json={"embeddings": [[1, 2] for _ in body["input"]]})

    embedder = Embedder(
        {"model": "nomic", "dimension": 2},
        tmp_path / "cache.db",
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    a = embedder.documents(["hello"])
    embedder.documents(["hello"])
    assert len(calls) == 1 and calls[0]["truncate"] is False
    assert calls[0]["input"] == ["search_document: hello"]
    artifact[0] = "changed"
    embedder.documents(["hello"])
    assert len(calls) == 2
    b = embedder.query("hello")
    assert calls[-1]["input"] == ["search_query: hello"]
    np.testing.assert_allclose(a[0], b)


def test_lmstudio_index_validation(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"data": [{"index": 2, "embedding": [1, 2]}]})

    embedder = Embedder(
        {"kind": "lmstudio", "url": "http://localhost:1234", "dimension": 2},
        tmp_path / "cache.db",
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(EmbeddingError):
        embedder.raw(["hello"])
