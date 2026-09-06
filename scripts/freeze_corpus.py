"""Freeze local P56 originals/retained sets without changing their contents."""

import argparse
import hashlib
import json
from pathlib import Path


def digest_files(root):
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlink in corpus: {path.name}")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(), files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--out", type=Path, default=Path("eval/corpus-lock.json"))
    args = parser.parse_args()
    records = []
    for path in sorted(args.bundle.glob("*/new/original/specpm.yaml")) + sorted(
        args.bundle.glob("*/retained-files/*/specpm.yaml")
    ):
        digest, files = digest_files(path.parent)
        records.append(
            {
                "path": path.parent.relative_to(args.bundle).as_posix(),
                "digest": digest,
                "files": files,
            }
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"version": 1, "records": records}, indent=2) + "\n")
    print(f"Frozen {len(records)} package directories")


if __name__ == "__main__":
    main()
