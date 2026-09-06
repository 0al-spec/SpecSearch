from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
import numpy as np

from .ingest import allowed_base
from .models import digest

PREPROCESSING = "nomic-prefix-utf8-1024-mean/v1"


class EmbeddingError(ValueError):
    pass


def chunks(text, limit=1024):
    if len(text.encode()) > 256 * 1024:
        raise EmbeddingError("document_too_large")
    result, current, size = [], [], 0
    for char in text:
        length = len(char.encode())
        if size + length > limit:
            result.append("".join(current))
            current, size = [], 0
        current.append(char)
        size += length
    if current:
        result.append("".join(current))
    return result or [" "]


def normalized(values, dimension):
    try:
        array = np.asarray(values, dtype=np.float32)
    except (TypeError, ValueError, OverflowError) as error:
        raise EmbeddingError("invalid_vector_shape_or_values") from error
    if array.ndim != 2 or array.shape[1] != dimension or not np.isfinite(array).all():
        raise EmbeddingError("invalid_vector_shape_or_values")
    norms = np.linalg.norm(array, axis=1, keepdims=True)
    if not np.isfinite(norms).all() or (norms <= 0).any():
        raise EmbeddingError("invalid_vector_norm")
    return array / norms


class Embedder:
    def __init__(self, config: dict, cache: Path, client=None):
        self.config = config
        self.kind = config.get("kind", "ollama")
        if self.kind not in ("ollama", "lmstudio"):
            raise EmbeddingError("unknown_provider")
        self.base = allowed_base(config.get("url", "http://127.0.0.1:11434"))
        if urlparse(self.base).hostname not in (
            "127.0.0.1",
            "localhost",
            "::1",
            "host.docker.internal",
        ):
            raise EmbeddingError("local_embedding_provider_required")
        self.model = config.get("model", "nomic-embed-text:latest")
        self.dimension = config.get("dimension", 768)
        self.cache = cache
        cache.parent.mkdir(parents=True, exist_ok=True)
        self.client = client or httpx.Client(timeout=30, follow_redirects=False, trust_env=False)
        self.owned = client is None
        self._artifact_cache = None
        with sqlite3.connect(cache) as con:
            con.execute("CREATE TABLE IF NOT EXISTS embeddings(key TEXT PRIMARY KEY, data BLOB)")

    def close(self):
        if self.owned:
            self.client.close()

    def request(self, method, path, **kwargs):
        for attempt in range(2):
            try:
                response = self.client.request(method, self.base + path, **kwargs)
                if response.status_code in (429, 502, 503, 504) and attempt == 0:
                    time.sleep(0.1)
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.TransportError:
                if attempt:
                    raise EmbeddingError("provider_unavailable") from None
                time.sleep(0.1)
        raise EmbeddingError("provider_unavailable")

    def identity(self):
        if self.kind == "ollama":
            models = self.model_list("/api/tags", "models", "name")
            match = next((m for m in models if m["name"] == self.model), None)
            capabilities = match.get("capabilities", ["embedding"]) if match else []
            if not isinstance(capabilities, list):
                raise EmbeddingError("invalid_provider_response")
            if not match or "embedding" not in capabilities:
                raise EmbeddingError("embedding_model_missing")
            artifact = match.get("digest")
            if not isinstance(artifact, str) or not artifact:
                raise EmbeddingError("invalid_provider_response")
        else:
            models = self.model_list("/api/v0/models", "data", "id")
            match = next((m for m in models if m["id"] == self.model), None)
            if not match or match.get("type") != "embeddings":
                raise EmbeddingError("embedding_model_missing")
            context = match.get("loaded_context_length")
            if type(context) is not int or context < 1100:
                raise EmbeddingError("embedding_context_not_confirmed")
            # LM Studio's model ID alone does not bind the served GGUF variant.
            artifact = self.artifact_digest()
            artifact = digest(
                [
                    artifact,
                    {k: match.get(k) for k in ("id", "arch", "quantization", "max_context_length")},
                ]
            )
        return {
            "kind": self.kind,
            "model": self.model,
            "artifact": artifact,
            "dimension": self.dimension,
            "preprocessing": PREPROCESSING,
        }

    def model_list(self, endpoint, key, identifier):
        payload = self.request("GET", endpoint)
        models = payload.get(key) if isinstance(payload, dict) else None
        if not isinstance(models, list) or any(
            not isinstance(model, dict) or not isinstance(model.get(identifier), str)
            for model in models
        ):
            raise EmbeddingError("invalid_provider_response")
        return models

    def artifact_digest(self):
        path = Path(self.config["artifact_path"])

        def identity(info):
            return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

        with path.open("rb") as file:
            before = identity(os.fstat(file.fileno()))
            if self._artifact_cache is not None and self._artifact_cache[0] == before:
                artifact = self._artifact_cache[1]
            else:
                artifact = hashlib.file_digest(file, "sha256").hexdigest()
            if identity(os.fstat(file.fileno())) != before or identity(path.stat()) != before:
                raise EmbeddingError("model_changed_during_hash")
        self._artifact_cache = (before, artifact)
        return artifact

    def raw(self, texts):
        if self.kind == "ollama":
            payload = self.request(
                "POST",
                "/api/embed",
                json={
                    "model": self.model,
                    "input": texts,
                    "truncate": False,
                    "options": {"num_ctx": 2048},
                },
            )
            values = payload.get("embeddings") if isinstance(payload, dict) else None
        else:
            payload = self.request(
                "POST", "/v1/embeddings", json={"model": self.model, "input": texts}
            )
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list) or any(
                not isinstance(row, dict)
                or type(row.get("index")) is not int
                or "embedding" not in row
                for row in data
            ):
                raise EmbeddingError("invalid_provider_response")
            data = sorted(data, key=lambda row: row["index"])
            if [row["index"] for row in data] != list(range(len(texts))):
                raise EmbeddingError("invalid_embedding_indices")
            values = [row["embedding"] for row in data]
        if not isinstance(values, list) or any(not isinstance(row, list) for row in values):
            raise EmbeddingError("invalid_provider_response")
        if len(values) != len(texts):
            raise EmbeddingError("invalid_embedding_count")
        return normalized(values, self.dimension)

    def encode(self, texts, role, cached):
        identity = self.identity()
        prefix = "search_query: " if role == "query" else "search_document: "
        split = [[prefix + part for part in chunks(text)] for text in texts]
        unique = list(dict.fromkeys(part for parts in split for part in parts))
        keys = {text: digest([identity, text]) for text in unique}
        vectors = {}
        with sqlite3.connect(self.cache) as con:
            if cached:
                for text, key in keys.items():
                    row = con.execute("SELECT data FROM embeddings WHERE key=?", (key,)).fetchone()
                    if row:
                        vectors[text] = normalized(
                            [np.frombuffer(row[0], dtype=np.float32)], self.dimension
                        )[0]
            missing = [text for text in unique if text not in vectors]
            for start in range(0, len(missing), 16):
                batch = missing[start : start + 16]
                for text, vector in zip(batch, self.raw(batch), strict=True):
                    vectors[text] = vector
                    if cached:
                        con.execute(
                            "INSERT OR REPLACE INTO embeddings VALUES(?,?)",
                            (keys[text], vector.tobytes()),
                        )
            if self.identity() != identity:
                raise EmbeddingError("model_changed_during_embedding")
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        return normalized(
            [np.mean([vectors[p] for p in parts], axis=0) for parts in split], self.dimension
        )

    def documents(self, texts):
        return self.encode(texts, "document", True)

    def query(self, text):
        return self.encode([text], "query", False)[0]
