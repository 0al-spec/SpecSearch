"""Create ignored operator config from an explicitly supplied frozen corpus."""

import argparse
import json
from pathlib import Path

from freeze_corpus import digest_files

from specsearch.cli import atomic_json
from specsearch.models import digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--provider", choices=["ollama", "lmstudio"], default="ollama")
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--out", type=Path, default=Path("config.local.json"))
    parser.add_argument("--data", default=".data/ollama")
    parser.add_argument("--path-prefix", type=Path)
    parser.add_argument("--provider-url")
    parser.add_argument("--registry")
    args = parser.parse_args()
    lock = json.loads(Path("eval/corpus-lock.json").read_text())
    paths = []
    for row in lock["records"]:
        path = (args.bundle / row["path"]).resolve()
        checksum, _ = digest_files(path)
        if checksum != row["digest"]:
            raise ValueError("frozen_corpus_drift:" + row["path"])
        paths.append(str(args.path_prefix / row["path"]) if args.path_prefix else str(path))
    config = {
        "data_dir": args.data,
        "corpus_digest": digest(lock),
        "sources": [{"id": "p56", "kind": "candidates", "paths": paths}],
        "provider": {"kind": args.provider, "dimension": 768},
    }
    if args.provider == "ollama":
        config["provider"].update(url="http://127.0.0.1:11434", model="nomic-embed-text:latest")
    else:
        if not args.artifact:
            parser.error("--artifact required for LM Studio")
        config["provider"].update(
            url="http://127.0.0.1:1234",
            model="text-embedding-nomic-embed-text-v1.5",
            artifact_path=str(args.artifact.resolve()),
        )
    if args.provider_url:
        config["provider"]["url"] = args.provider_url
    if args.registry:
        config["sources"].append({"id": "specpm-local", "kind": "registry", "url": args.registry})
    atomic_json(args.out, config)
    print(f"Configured {len(paths)} frozen package paths")


if __name__ == "__main__":
    main()
