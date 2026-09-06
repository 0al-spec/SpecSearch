import json
from pathlib import Path

import httpx
import pytest

from specsearch.ingest import ImportFailure, import_sources, registry_json


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
