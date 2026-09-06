from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .embeddings import Embedder
from .ingest import import_sources
from .models import Filters, Package, SearchRequest
from .service import SearchService
from .store import Store


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    os.replace(temporary, path)


def configuration(path):
    config = json.loads(path.read_text())
    ids = [source["id"] for source in config.get("sources", [])]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate_source_ids")
    return config


def main():
    parser = argparse.ArgumentParser(prog="specsearch")
    parser.add_argument("--config", type=Path, default=Path("config.local.json"))
    commands = parser.add_subparsers(dest="command", required=True)
    imp = commands.add_parser("import")
    imp.add_argument("--allow-rejected", action="store_true")
    index = commands.add_parser("index")
    index.add_argument("action", choices=["build"])
    index.add_argument("--lexical", action="store_true")
    search = commands.add_parser("search")
    search.add_argument("query")
    search.add_argument("--source", choices=["registry", "candidates", "all"], default="registry")
    search.add_argument("--mode", choices=["lexical", "vector", "hybrid"], default="hybrid")
    search.add_argument("--top-k", type=int, default=10)
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8030)
    serve.add_argument("--host", choices=["127.0.0.1", "0.0.0.0"], default="127.0.0.1")
    commands.add_parser("status")
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--queries", type=Path, default=Path("eval/queries.json"))
    evaluate.add_argument("--split", choices=["dev", "test"], default="test")
    evaluate.add_argument("--out", type=Path, default=Path(".data/evaluation.json"))
    args = parser.parse_args()
    config = configuration(args.config)
    data = Path(config.get("data_dir", ".data/default"))
    store = Store(data / "index")
    if args.command == "import":
        packages, report = import_sources(config.get("sources", []))
        atomic_json(data / "import-report.json", report)
        print(json.dumps(report, ensure_ascii=False))
        if report["errors"] and not args.allow_rejected:
            return 1
        atomic_json(data / "packages.json", [p.model_dump() for p in packages])
        return 0
    embedder = Embedder(config.get("provider", {}), data / "cache.db")
    try:
        service = SearchService(store, embedder, config.get("semantic_threshold"))
        if args.command == "index":
            packages = [
                Package.model_validate(p) for p in json.loads((data / "packages.json").read_text())
            ]
            print(json.dumps(store.build(packages, None if args.lexical else embedder)))
        elif args.command == "search":
            result = service.search(
                SearchRequest(
                    query=args.query,
                    mode=args.mode,
                    top_k=args.top_k,
                    filters=Filters(source=args.source),
                )
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "status":
            print(json.dumps(service.status(), indent=2))
        elif args.command == "evaluate":
            from .evaluation import evaluate

            atomic_json(args.out, evaluate(service, args.queries, args.split))
            print(str(args.out))
        else:
            import uvicorn

            from .api import create_app

            uvicorn.run(create_app(service), host=args.host, port=args.port, access_log=False)
    finally:
        embedder.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
