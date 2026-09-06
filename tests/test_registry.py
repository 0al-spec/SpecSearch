import json
from pathlib import Path

import httpx
import pytest

from specsearch.ingest import ImportFailure, import_sources, registry_json, registry_package


def test_registry_capabilities_have_independent_documents():
    payload = json.loads(Path("tests/fixtures/registry/version.json").read_text())
    item = payload["package"]
    item["provided_capabilities"].append("document_conversion.markdown_to_email")
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as client:
        package = registry_package(
            client, "http://localhost:8081", "test", item["package_id"], item["version"], {}
        )
    metadata, *capabilities = package.documents
    assert len(capabilities) == 2
    assert len({doc.id for doc in package.documents}) == 3
    assert not any(f.path.startswith("package.provided_capabilities") for f in metadata.fields)
    for i, doc in enumerate(capabilities):
        assert doc.fields[0].path == f"package.provided_capabilities[{i}]"
        assert doc.fields[0].text == item["provided_capabilities"][i]
        assert item["provided_capabilities"][1 - i] not in doc.text
        assert any(f.path == "package.compatibility.platforms[0]" for f in doc.fields)
    assert package.capabilities == item["provided_capabilities"]
    assert package.details["metadata"] == item


@pytest.mark.parametrize("failure", ["http", "json", "contract", "identity", "lifecycle"])
def test_exact_version_failure_is_isolated(failure):
    status = json.loads(Path("tests/fixtures/registry/status.json").read_text())
    payload = json.loads(Path("tests/fixtures/registry/version.json").read_text())
    pid = payload["package"]["package_id"]
    versions = ["0.1.0", "0.2.0", "0.3.0"]
    catalog = {
        **{k: payload[k] for k in ("apiVersion", "schemaVersion", "status")},
        "kind": "RemotePackageIndex",
        "package_count": 1,
        "version_count": 3,
        "packages": [
            {
                "package_id": pid,
                "name": payload["package"]["name"],
                "capabilities": payload["package"]["provided_capabilities"],
                "versions": [
                    {"version": v, "yanked": False, "deprecated": False} for v in versions
                ],
            }
        ],
    }
    requested = []

    def handler(request):
        if request.url.path == "/v0/status":
            return httpx.Response(200, json=status)
        if request.url.path == "/v0/packages":
            return httpx.Response(200, json=catalog)
        version = request.url.path.rsplit("/", 1)[-1]
        requested.append(version)
        exact = {**payload, "package": {**payload["package"], "version": version}}
        if version == "0.2.0":
            if failure == "http":
                return httpx.Response(503)
            if failure == "json":
                return httpx.Response(200, content=b"not json")
            if failure == "contract":
                exact["apiVersion"] = "wrong"
            if failure == "identity":
                exact["package"]["version"] = "9.9.9"
            if failure == "lifecycle":
                exact["package"]["state"] = {"yanked": "false", "deprecated": False}
        return httpx.Response(200, json=exact)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        packages, report = import_sources(
            [{"kind": "registry", "id": "test", "url": "http://localhost:8081"}], client
        )
    assert requested == versions
    assert [p.version for p in packages] == ["0.1.0", "0.3.0"]
    assert report["imported"] == 2
    assert len(report["errors"]) == 1
    error = report["errors"][0]
    assert error["source_id"] == "test"
    assert error["package_id"] == pid
    assert error["version"] == "0.2.0"
    assert error["detail"]


def test_real_specpm_static_payloads_and_slash_redirect():
    from specsearch.ingest import registry_package

    status = json.loads(Path("tests/fixtures/registry/status.json").read_text())
    version = json.loads(Path("tests/fixtures/registry/version.json").read_text())

    def handler(request):
        if not request.url.path.endswith("/"):
            return httpx.Response(301, headers={"Location": request.url.path + "/"})
        return httpx.Response(
            200, json=status if request.url.path.endswith("/status/") else version
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    observed = registry_json(client, "http://localhost:8081", "/v0/status")
    package = registry_package(
        client,
        "http://localhost:8081",
        "test",
        "document_conversion.email_tools",
        "0.1.0",
        observed,
    )
    assert package.metadata_only and package.source_kind == "registry"
    assert package.capabilities == ["document_conversion.email_to_markdown"]


def test_registry_projection_after_specpm_validation(monkeypatch):
    validated = []

    def validate(payload):
        validated.append(payload["kind"])
        return []

    monkeypatch.setattr("specsearch.ingest.validate_remote_registry_payload", validate)
    envelope = {"apiVersion": "specpm.registry/v0", "schemaVersion": 1, "status": "ok"}

    def handler(request):
        if request.url.path.endswith("/status"):
            return httpx.Response(
                200, json={**envelope, "kind": "RemoteRegistryStatus", "registry": {}}
            )
        if request.url.path == "/v0/packages":
            return httpx.Response(
                200,
                json={
                    **envelope,
                    "kind": "RemotePackageIndex",
                    "packages": [{"package_id": "fixture.pkg", "versions": [{"version": "1.0.0"}]}],
                },
            )
        return httpx.Response(
            200,
            json={
                **envelope,
                "kind": "RemotePackageVersion",
                "package": {
                    "package_id": "fixture.pkg",
                    "version": "1.0.0",
                    "name": "Fixture",
                    "provided_capabilities": ["fixture.run"],
                    "state": {"yanked": False, "deprecated": False},
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    packages, report = import_sources(
        [{"kind": "registry", "id": "test", "url": "http://localhost:8081"}], client
    )
    assert report["errors"] == [] and len(packages) == 1
    assert validated == ["RemoteRegistryStatus", "RemotePackageIndex", "RemotePackageVersion"]
    p = packages[0]
    assert p.source_kind == "registry" and p.metadata_only
    assert p.details["metadata"]["provided_capabilities"] == ["fixture.run"]
    assert p.provenance["endpoint"].endswith("/versions/1.0.0")


def test_registry_rejects_non_contract_and_redirect():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"apiVersion": "wrong", "status": "ok"})
        )
    )
    with pytest.raises(ImportFailure):
        registry_json(client, "http://localhost:8081", "/v0/status")
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(302, headers={"Location": "http://evil.example"})
        )
    )
    packages, report = import_sources(
        [{"kind": "registry", "id": "test", "url": "http://localhost:8081"}], client
    )
    assert not packages and report["errors"]
