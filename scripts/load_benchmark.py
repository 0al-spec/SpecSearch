"""Synthetic replication measures load only, never retrieval quality."""

import argparse
import json
import time
from pathlib import Path

import numpy as np

from specsearch.cli import atomic_json, configuration
from specsearch.embeddings import Embedder
from specsearch.models import Filters, Package, SearchRequest
from specsearch.service import SearchService
from specsearch.store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("config.local.json"))
    parser.add_argument("--out", type=Path, default=Path("SPECS/reports/load-1000.json"))
    args = parser.parse_args()
    config = configuration(args.config)
    data = Path(config["data_dir"])
    originals = [
        Package.model_validate(p) for p in json.loads((data / "packages.json").read_text())
    ]
    packages = []
    for i in range(1000):
        source = originals[i % len(originals)]
        packages.append(
            source.model_copy(
                update={"record_id": f"load-{i}", "package_id": f"load.{i}", "locator": {}}
            )
        )
    embedder = Embedder(config["provider"], data / "cache.db")
    try:
        store = Store(data / "load-index")
        start = time.perf_counter()
        status = store.build(packages, embedder)
        build_seconds = time.perf_counter() - start
        service = SearchService(store, embedder)
        queries = [
            "Compress shell output",
            "HTTP client",
            "workflow automation",
            "полностью проверяющий узел Bitcoin",
            "сократить вывод команд",
        ]
        first = service.search(
            SearchRequest(query=queries[0], filters=Filters(source="candidates"))
        )
        timings = []
        for query in queries * 4:
            response = service.search(
                SearchRequest(query=query, filters=Filters(source="candidates"))
            )
            assert not response["degraded"]
            timings.append(response["latency_ms"])
        atomic_json(
            args.out,
            {
                "scope": "synthetic replicated packages, not quality evidence",
                "index": status,
                "build_seconds": build_seconds,
                "first_request_ms": first["latency_ms"],
                "cold_model_start_measured": False,
                "warm_request_count": len(timings),
                "warm_p95_ms": float(np.percentile(timings, 95)),
                "performance_target_met": bool(np.percentile(timings, 95) <= 2000),
            },
        )
        print(args.out)
    finally:
        embedder.close()


if __name__ == "__main__":
    main()
