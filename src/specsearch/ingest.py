from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urljoin, urlparse

import httpx
import yaml
from specpm.core import validate_package, validate_remote_registry_payload

from .models import Document, FieldText, Package, digest, now

MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
MAX_FILES = 512
SPEC_PM_REVISION = "8a5ce3dece3d18bf8f601a5a599520bd520c7839"


class ImportFailure(ValueError):
    pass


def safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ImportFailure("unsafe_relative_path")
    return path.as_posix()


def read_tree(root: Path) -> dict[str, bytes]:
    if root.is_symlink() or not root.is_dir():
        raise ImportFailure("invalid_root")
    root = root.resolve()
    files = {}
    total = 0
    directories = 0
    for directory, dirs, names, dir_fd in os.fwalk(root, follow_symlinks=False):
        directories += 1
        if directories > MAX_FILES:
            raise ImportFailure("directory_count_limit")
        if any(
            stat.S_ISLNK(os.stat(name, dir_fd=dir_fd, follow_symlinks=False).st_mode)
            for name in dirs
        ):
            raise ImportFailure("symlink_directory")
        for name in sorted(names):
            path = Path(directory) / name
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE:
                    raise ImportFailure("file_type_or_size_limit")
                content = stream.read(MAX_FILE + 1)
            total += len(content)
            if len(content) > MAX_FILE or total > MAX_TOTAL or len(files) >= MAX_FILES:
                raise ImportFailure("package_size_limit")
            files[path.relative_to(root).as_posix()] = content
    return files


def load_yaml(content: bytes) -> dict:
    if len(content) > MAX_FILE:
        raise ImportFailure("yaml_size_limit")
    depth = 0
    for event in yaml.parse(content):
        if isinstance(event, yaml.AliasEvent) or getattr(event, "anchor", None):
            raise ImportFailure("yaml_alias_not_allowed")
        if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
            depth += 1
            if depth > 30:
                raise ImportFailure("yaml_depth_limit")
        elif isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
            depth -= 1
    result = yaml.safe_load(content)
    if not isinstance(result, dict):
        raise ImportFailure("yaml_mapping_required")
    return result


def fields(value, prefix) -> list[FieldText]:
    if isinstance(value, dict):
        return [field for k, v in value.items() for field in fields(v, f"{prefix}.{k}")]
    if isinstance(value, list):
        return [field for i, v in enumerate(value) for field in fields(v, f"{prefix}[{i}]")]
    if isinstance(value, (str, int, float)) and str(value).strip():
        return [FieldText(path=prefix, text=str(value))]
    return []


def local_package(root: Path, source_id: str) -> Package:
    contents = read_tree(root)
    manifest = load_yaml(contents["specpm.yaml"])
    paths = [safe_relative(item["path"]) for item in manifest.get("specs", [])]
    specs = [(path, load_yaml(contents[path])) for path in paths]
    # Validate the immutable bounded copy, never the live repository tree.
    for path, spec in specs:
        for item in spec.get("evidence", []):
            if "path" in item:
                safe_relative(item["path"])
    with tempfile.TemporaryDirectory() as temp:
        snapshot = Path(temp)
        for name, content in contents.items():
            if name.endswith((".yaml", ".yml")):
                load_yaml(content)
            target = snapshot / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        validation = validate_package(snapshot)
    if validation["error_count"]:
        raise ImportFailure("specpm_invalid:" + ",".join(e["code"] for e in validation["errors"]))
    meta = manifest["metadata"]
    file_digests = {k: hashlib.sha256(v).hexdigest() for k, v in sorted(contents.items())}
    checksum = digest(file_digests)
    rid = digest([source_id, meta["id"], meta["version"], checksum])
    documents = [
        Document(
            id=f"{rid}:package",
            fields=fields(
                {k: meta[k] for k in ("id", "name", "summary") if k in meta}, "specpm.yaml.metadata"
            )
            + fields(manifest.get("keywords", []), "specpm.yaml.keywords"),
        )
    ]
    evidence = []
    details = {"compatibility": manifest.get("compatibility"), "specs": []}
    for path, spec in specs:
        sid = spec["metadata"]["id"]
        context = []
        for key in ("interfaces", "requires", "constraints", "effects", "scope"):
            context.extend(fields(spec.get(key), f"{path}.{key}"))
        documents.append(
            Document(
                id=f"{rid}:{sid}:purpose",
                spec_id=sid,
                fields=fields(spec.get("intent"), f"{path}.intent") + context,
            )
        )
        for i, cap in enumerate(spec.get("provides", {}).get("capabilities", [])):
            documents.append(
                Document(
                    id=f"{rid}:{sid}:cap:{i}",
                    spec_id=sid,
                    fields=fields(cap, f"{path}.provides.capabilities[{i}]") + context,
                )
            )
        details["specs"].append(
            {
                "spec_id": sid,
                "path": path,
                **{
                    key: spec.get(key)
                    for key in (
                        "intent",
                        "provides",
                        "interfaces",
                        "requires",
                        "constraints",
                        "effects",
                        "scope",
                    )
                },
            }
        )
        evidence.extend(
            {"spec_id": sid, "spec_path": path, **item} for item in spec.get("evidence", [])
        )
    return Package(
        record_id=rid,
        source_id=source_id,
        source_kind="candidates",
        package_id=meta["id"],
        version=meta["version"],
        name=meta["name"],
        summary=meta.get("summary", ""),
        license=meta.get("license"),
        digest=checksum,
        capabilities=validation["capabilities"],
        intents=validation["intents"],
        observed_at=now(),
        documents=documents,
        details=details,
        evidence=evidence,
        provenance={
            "file_digests": file_digests,
            "validator": SPEC_PM_REVISION,
            "warning_count": validation["warning_count"],
        },
        locator={"path": str(root.resolve())},
    )


def allowed_base(url: str):
    parsed = urlparse(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ImportFailure("invalid_source_url")
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ImportFailure("invalid_source_url")
    if parsed.scheme == "http" and parsed.hostname not in (
        "localhost",
        "127.0.0.1",
        "::1",
        "host.docker.internal",
    ):
        raise ImportFailure("http_requires_localhost")
    return url.rstrip("/")


def registry_json(client, base, endpoint):
    with client.stream("GET", allowed_base(base) + endpoint) as response:
        current = allowed_base(base) + endpoint
        if (
            response.status_code in (301, 302, 307, 308)
            and not endpoint.endswith("/")
            and urljoin(current, response.headers.get("location", "")) == current + "/"
        ):
            return registry_json(client, base, endpoint + "/")
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_bytes():
            data.extend(chunk)
            if len(data) > MAX_FILE:
                raise ImportFailure("registry_size_limit")
    payload = json.loads(data)
    if validate_remote_registry_payload(payload) or payload.get("status") != "ok":
        raise ImportFailure("unsupported_registry_payload")
    return payload


def registry_package(client, base, source_id, pid, version, status):
    endpoint = f"/v0/packages/{quote(pid, safe='')}/versions/{quote(version, safe='')}"
    payload = registry_json(client, base, endpoint)
    if payload.get("kind") != "RemotePackageVersion":
        raise ImportFailure("wrong_registry_kind")
    item = payload["package"]
    if item["package_id"] != pid or item["version"] != version:
        raise ImportFailure("registry_identity_mismatch")
    checksum = digest(item)
    rid = digest([source_id, pid, version, checksum])
    doc_fields = fields(
        {
            k: item[k]
            for k in (
                "package_id",
                "name",
                "summary",
                "provided_capabilities",
                "provided_intents",
                "required_capabilities",
                "compatibility",
            )
            if k in item
        },
        "package",
    )
    state = item["state"]
    if not isinstance(state, dict):
        raise ImportFailure("invalid_lifecycle")
    for key in ("yanked", "deprecated"):
        if type(state.get(key)) is not bool:
            raise ImportFailure("invalid_lifecycle")
    return Package(
        record_id=rid,
        source_id=source_id,
        source_kind="registry",
        package_id=pid,
        version=version,
        name=item["name"],
        summary=item.get("summary", ""),
        license=item.get("license"),
        digest=checksum,
        metadata_only=True,
        capabilities=item.get("provided_capabilities", []),
        intents=item.get("provided_intents", []),
        yanked=state["yanked"],
        deprecated=state["deprecated"],
        observed_at=now(),
        documents=[Document(id=rid + ":metadata", fields=doc_fields)],
        details={"metadata": item},
        provenance={
            "status_digest": digest(status),
            "payload_digest": digest(payload),
            "registry_status": status,
            "endpoint": endpoint,
            "registry": base,
        },
        locator={"registry": base},
    )


def import_sources(sources: list[dict], client=None):
    packages, errors = [], []
    owned = client is None
    client = client or httpx.Client(timeout=15, follow_redirects=False, trust_env=False)
    try:
        for source in sources:
            try:
                if source["kind"] == "candidates":
                    for path in source["paths"]:
                        try:
                            packages.append(local_package(Path(path), source["id"]))
                        except (ValueError, OSError, KeyError, TypeError, yaml.YAMLError) as exc:
                            errors.append(
                                {
                                    "source_id": source["id"],
                                    "input": path,
                                    "error": type(exc).__name__,
                                    "detail": str(exc)[:300],
                                }
                            )
                elif source["kind"] == "registry":
                    base = allowed_base(source["url"])
                    status = registry_json(client, base, "/v0/status")
                    catalog = registry_json(client, base, "/v0/packages")
                    for item in catalog["packages"]:
                        for version in item["versions"]:
                            packages.append(
                                registry_package(
                                    client,
                                    base,
                                    source["id"],
                                    item["package_id"],
                                    version["version"],
                                    status,
                                )
                            )
                else:
                    raise ImportFailure("unknown_source_kind")
            except (ValueError, OSError, KeyError, TypeError, httpx.HTTPError) as exc:
                errors.append(
                    {
                        "source_id": source["id"],
                        "error": type(exc).__name__,
                        "detail": str(exc)[:300],
                    }
                )
    finally:
        if owned:
            client.close()
    unique = {p.record_id: p for p in packages}
    return list(unique.values()), {"imported": len(unique), "errors": errors, "at": now()}
