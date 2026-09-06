import json
import os

import httpx
import numpy as np
import pytest

from specsearch import embeddings as embeddings_module
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


def test_lmstudio_requires_loaded_context_and_binds_artifact(tmp_path):
    artifact = tmp_path / "model.gguf"
    artifact.write_bytes(b"fixture artifact, not a real model")
    context = [512]

    def handler(request):
        if request.url.path == "/api/v0/models":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "nomic",
                            "type": "embeddings",
                            "loaded_context_length": context[0],
                            "max_context_length": 2048,
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1, 2]}]})

    embedder = Embedder(
        {
            "kind": "lmstudio",
            "url": "http://localhost:1234",
            "model": "nomic",
            "dimension": 2,
            "artifact_path": str(artifact),
        },
        tmp_path / "cache.db",
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(EmbeddingError, match="context"):
        embedder.identity()
    context[0] = 2048
    before = embedder.identity()
    assert embedder.documents(["hello"]).shape == (1, 2)
    artifact.write_bytes(b"different fixture artifact")
    assert embedder.identity() != before


@pytest.mark.parametrize("url", ["http://[::1]:11434", "http://localhost", "http://127.0.0.1"])
def test_local_provider_parsed_host(tmp_path, url):
    calls = []

    def handler(request):
        calls.append(request.url.host)
        return httpx.Response(200, json={"embeddings": [[1, 2]]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        embedder = Embedder({"url": url, "dimension": 2}, tmp_path / "cache.db", client)
        assert embedder.raw(["hello"]).shape == (1, 2)
    assert calls == [httpx.URL(url).host]


@pytest.mark.parametrize("url", ["https://localhost.evil.test:11434", "https://example.com"])
def test_nonlocal_provider_rejected(tmp_path, url):
    with pytest.raises(EmbeddingError, match="local_embedding_provider_required"):
        Embedder({"url": url}, tmp_path / "cache.db")


@pytest.mark.parametrize("kind,key", [("ollama", "models"), ("lmstudio", "data")])
@pytest.mark.parametrize("value", [None, {}, "models", [None], [{}], [{"name": None}]])
def test_invalid_model_list_is_value_error(tmp_path, kind, key, value):
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={key: value}))
    ) as client:
        embedder = Embedder({"kind": kind}, tmp_path / "cache.db", client)
        with pytest.raises(ValueError):
            embedder.identity()


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"models": [{"name": "nomic", "capabilities": None}]},
        {"models": [{"name": "nomic", "digest": None}]},
        {"models": [{"name": "nomic"}]},
    ],
)
def test_invalid_model_metadata_is_value_error(tmp_path, payload):
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as client:
        embedder = Embedder({"model": "nomic"}, tmp_path / "cache.db", client)
        with pytest.raises(ValueError):
            embedder.identity()


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("ollama", None),
        ("ollama", []),
        ("ollama", {}),
        ("ollama", {"embeddings": None}),
        ("ollama", {"embeddings": [None]}),
        ("ollama", {"embeddings": [[{}, 1]]}),
        ("lmstudio", None),
        ("lmstudio", {}),
        ("lmstudio", {"data": None}),
        ("lmstudio", {"data": [None]}),
        ("lmstudio", {"data": [{}]}),
        ("lmstudio", {"data": [{"index": None, "embedding": [1, 2]}]}),
        ("lmstudio", {"data": [{"index": 0, "embedding": None}]}),
        ("lmstudio", {"data": [{"index": 0, "embedding": [{}, 1]}]}),
    ],
)
def test_invalid_embeddings_are_value_errors(tmp_path, kind, payload):
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as client:
        embedder = Embedder({"kind": kind, "dimension": 2}, tmp_path / "cache.db", client)
        with pytest.raises(ValueError):
            embedder.raw(["hello"])


def test_gguf_digest_cache_detects_stat_changes(tmp_path, monkeypatch):
    path = tmp_path / "model.gguf"
    path.write_bytes(b"first model")
    real_digest = embeddings_module.hashlib.file_digest
    hashes = []

    def counted_digest(file, algorithm):
        hashes.append(file.name)
        return real_digest(file, algorithm)

    monkeypatch.setattr(embeddings_module.hashlib, "file_digest", counted_digest)

    def handler(request):
        if request.url.path == "/api/v0/models":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "nomic",
                            "type": "embeddings",
                            "loaded_context_length": 2048,
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1, 2]}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        embedder = Embedder(
            {"kind": "lmstudio", "model": "nomic", "dimension": 2, "artifact_path": path},
            tmp_path / "cache.db",
            client,
        )
        before = embedder.identity()
        embedder.query("hello")
        embedder.query("hello again")
        assert len(hashes) == 1
        info = path.stat()
        path.write_bytes(b"other model")
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
        changed = embedder.identity()
        assert changed != before
        assert len(hashes) == 2
        replacement = tmp_path / "replacement.gguf"
        replacement.write_bytes(b"third model")
        os.utime(replacement, ns=(info.st_atime_ns, info.st_mtime_ns))
        replacement.replace(path)
        assert embedder.identity() != changed
        assert len(hashes) == 3


def test_gguf_change_during_hash_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "model.gguf"
    path.write_bytes(b"first model")
    real_digest = embeddings_module.hashlib.file_digest

    def changing_digest(file, algorithm):
        result = real_digest(file, algorithm)
        path.write_bytes(b"changed model")
        return result

    monkeypatch.setattr(embeddings_module.hashlib, "file_digest", changing_digest)
    with httpx.Client() as client:
        embedder = Embedder({"artifact_path": path}, tmp_path / "cache.db", client)
        with pytest.raises(EmbeddingError, match="model_changed_during_hash"):
            embedder.artifact_digest()
        assert embedder._artifact_cache is None
