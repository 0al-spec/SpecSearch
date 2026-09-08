import json
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from specsearch.api import create_app
from specsearch.ingest import ImportFailure, import_sources, local_package, registry_package
from specsearch.models import Filters, Package, SearchRequest, Upstream
from specsearch.service import SearchService
from specsearch.store import Store
from specsearch.upstream import manifest_upstream, normalize_upstream

URL = "https://example.org/software/repository"
UPSTREAM = {"url": URL, "revision": "a" * 40}
ARTIFACT = {
    "id": "upstream_repository",
    "role": "primary_intent_source",
    "uri": URL,
    "revision": UPSTREAM["revision"],
}
INVALID = [
    None,
    "https://example.org/repository",
    [],
    {},
    {"url": None},
    {"url": 12},
    {"url": ""},
    {"url": "javascript:alert(1)"},
    {"url": "file:///repository"},
    {"url": "https:///repository"},
    {"url": "https://user@example.org/repository"},
    {"url": "https://user:password@example.org/repository"},
    {"url": "https://@example.org/repository"},
    {"url": URL + "?download=1"},
    {"url": URL + "#readme"},
    {"url": URL + " "},
    {"url": URL + "\t"},
    {"url": URL + "\n"},
    {"url": URL + "\x00"},
    {"url": URL + "\x7f"},
    {"url": URL + "\u00a0"},
    {"url": "https://example.org\\repository"},
    {"url": "https://example.org:invalid/repository"},
    {"url": "https://example.org:65536/repository"},
    {"url": "https://[invalid/repository"},
    {"url": URL + "/" + "a" * 2048},
    *[{"url": URL, "revision": value} for value in (None, 12, "", " ", "a b", "a\n")],
    *[{"url": URL, "revision": value} for value in ("a\x00", "a\x7f", "a\u00a0", "a" * 257)],
]


@pytest.mark.parametrize("value", INVALID)
def test_normalizer_and_typed_model_reject_invalid(value):
    assert normalize_upstream(value) is None
    with pytest.raises(ValidationError, match="invalid_upstream"):
        Upstream.model_validate(value)


@pytest.mark.parametrize(
    "value",
    [
        {"url": URL},
        UPSTREAM,
        {"url": "http://example.org:8080/repository", "revision": "refs/tags/v1.0"},
        {"url": "https://[::1]:443/repository", "revision": "v1"},
        {
            "url": "https://example.org/" + "a" * (2048 - len("https://example.org/")),
            "revision": "a" * 256,
        },
    ],
)
def test_normalization_preserves_valid_values_and_roundtrips(value):
    assert normalize_upstream(value) == value
    upstream = Upstream.model_validate(value)
    assert upstream.model_dump() == value
    assert Upstream.model_validate_json(upstream.model_dump_json()) == upstream


def test_normalizer_matches_producer_projection_of_extra_fields():
    value = {**UPSTREAM, "unrelated": "ignored"}
    assert normalize_upstream(value) == UPSTREAM
    assert Upstream.model_validate(value).model_dump() == UPSTREAM


@pytest.mark.parametrize("artifacts", [None, {}, [], [None], [ARTIFACT, ARTIFACT]])
def test_manifest_helper_omits_missing_and_ambiguous(artifacts):
    assert manifest_upstream({"foreignArtifacts": artifacts}) is None


def write_artifacts(root, artifacts):
    path = root / "specpm.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest["foreignArtifacts"] = artifacts
    path.write_text(yaml.safe_dump(manifest))


def test_local_import_selects_explicit_artifact_only(local_fixture):
    baseline = local_package(local_fixture, "test")
    write_artifacts(
        local_fixture,
        [
            {"id": "documentation", "role": "primary_intent_source", "uri": "https://other.org"},
            ARTIFACT,
        ],
    )
    before = (local_fixture / "specpm.yaml").read_bytes()
    package = local_package(local_fixture, "test")
    assert package.upstream.model_dump() == UPSTREAM
    assert (local_fixture / "specpm.yaml").read_bytes() == before
    assert package.digest != baseline.digest
    assert package.record_id != baseline.record_id
    assert [doc.fields for doc in package.documents] == [doc.fields for doc in baseline.documents]
    assert URL not in json.dumps(package.details)


@pytest.mark.parametrize(
    "artifacts",
    [
        [],
        [{**ARTIFACT, "id": "repository"}],
        [{**ARTIFACT, "role": "implementation_hint"}],
        [ARTIFACT, dict(ARTIFACT)],
        [ARTIFACT, {**ARTIFACT, "role": "implementation_hint"}],
        [{**ARTIFACT, "uri": "javascript:alert(1)"}],
        [{**ARTIFACT, "revision": "bad revision"}],
    ],
)
def test_local_import_omits_absent_invalid_or_ambiguous(local_fixture, artifacts):
    write_artifacts(local_fixture, artifacts)
    package = local_package(local_fixture, "test")
    assert package.upstream is None
    assert package.public()["upstream"] is None


def registry_fixture():
    return json.loads(Path("tests/fixtures/registry/version.json").read_text())


def import_version(payload):
    item = payload["package"]
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as client:
        return registry_package(
            client, "http://localhost:8081", "test", item["package_id"], item["version"], {}
        )


@pytest.mark.parametrize("value", INVALID)
def test_registry_rejects_explicit_invalid_upstream(value):
    payload = registry_fixture()
    payload["package"]["upstream"] = value
    # Updated SpecPM rejects first; the pinned validator reaches consumer validation.
    with pytest.raises(ImportFailure, match="^(invalid_upstream|unsupported_registry_payload)$"):
        import_version(payload)


def test_registry_preserves_archive_separation_and_document_content():
    payload = registry_fixture()
    baseline = import_version(payload)
    assert baseline.upstream is None
    archive = deepcopy(payload["package"]["source"])
    payload["package"]["upstream"] = UPSTREAM
    package = import_version(payload)
    assert package.upstream.model_dump() == UPSTREAM
    assert package.details["metadata"]["source"] == archive
    assert package.details["metadata"]["upstream"] == UPSTREAM
    assert package.digest != baseline.digest
    assert package.record_id != baseline.record_id
    assert [doc.fields for doc in package.documents] == [doc.fields for doc in baseline.documents]


def test_registry_uses_exact_version_never_catalog_upstream():
    payload = registry_fixture()
    pid = payload["package"]["package_id"]
    status = json.loads(Path("tests/fixtures/registry/status.json").read_text())
    versions = ["0.1.0", "0.2.0", "0.3.0", "0.4.0"]
    catalog = {
        **{key: payload[key] for key in ("apiVersion", "schemaVersion", "status")},
        "kind": "RemotePackageIndex",
        "package_count": 1,
        "version_count": len(versions),
        "packages": [
            {
                "package_id": pid,
                "name": payload["package"]["name"],
                "capabilities": payload["package"]["provided_capabilities"],
                "upstream": {"url": "https://catalog.example.org/wrong"},
                "versions": [
                    {"version": version, "yanked": False, "deprecated": False}
                    for version in versions
                ],
            }
        ],
    }
    requests = []

    def handler(request):
        requests.append(str(request.url))
        if request.url.path == "/v0/status":
            return httpx.Response(200, json=status)
        if request.url.path == "/v0/packages":
            return httpx.Response(200, json=catalog)
        version = request.url.path.rsplit("/", 1)[-1]
        exact = deepcopy(payload)
        exact["package"]["version"] = version
        if version in versions[:2]:
            exact["package"]["upstream"] = {"url": URL, "revision": version}
        elif version == "0.4.0":
            exact["package"]["upstream"] = {"url": "javascript:alert(1)"}
        return httpx.Response(200, json=exact)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        packages, report = import_sources(
            [{"kind": "registry", "id": "test", "url": "http://localhost:8081"}], client
        )
    assert [p.version for p in packages] == versions[:3]
    assert [p.upstream.revision if p.upstream else None for p in packages] == [
        "0.1.0",
        "0.2.0",
        None,
    ]
    assert len(report["errors"]) == 1
    assert report["errors"][0]["version"] == "0.4.0"
    assert report["errors"][0]["detail"] in {
        "invalid_upstream",
        "unsupported_registry_payload",
    }
    assert len(requests) == 6
    assert all(url.startswith("http://localhost:8081/v0/") for url in requests)


@pytest.mark.parametrize("upstream", [None, {"url": URL}, UPSTREAM])
def test_package_snapshot_search_detail_roundtrip(tmp_path, package_factory, upstream):
    package = package_factory(upstream=upstream, locator={"path": "/private/local/package"})
    assert Package.model_validate_json(package.model_dump_json()) == package
    legacy = package.model_dump()
    legacy.pop("upstream")
    assert Package.model_validate(legacy).upstream is None
    store = Store(tmp_path)
    first = store.build([package])["snapshot"]
    service = SearchService(store)
    initial = service.search(SearchRequest(query=package.package_id, filters=Filters(source="all")))
    assert initial["results"][0]["upstream"] == upstream
    store.build([package_factory(upstream={"url": URL, "revision": "new"})])
    assert store.package(package.record_id, first).public()["upstream"] == upstream
    client = TestClient(create_app(service))
    detail = client.get(f"/v1/packages/{package.record_id}?snapshot={first}").json()
    assert detail["upstream"] == upstream
    assert "locator" not in detail
    for query in (package.package_id, "compress"):
        response = client.post(
            "/v1/search", json={"query": query, "mode": "lexical", "filters": {"source": "all"}}
        )
        assert response.status_code == 200
        result = response.json()
        current = client.get(
            f"/v1/packages/{package.record_id}?snapshot={result['snapshot']}"
        ).json()
        assert result["results"][0]["upstream"] == current["upstream"]
        assert current["upstream"] == {"url": URL, "revision": "new"}


def test_local_upstream_revision_drift_is_metadata_only(local_fixture, tmp_path):
    write_artifacts(local_fixture, [ARTIFACT])
    package = local_package(local_fixture, "test")
    store = Store(tmp_path)
    snapshot = store.build([package])["snapshot"]
    service = SearchService(store)
    verified = service.verify(package.record_id, snapshot)
    assert verified["status"] == "matched_metadata"
    assert verified["runtime_verified"] is False
    assert verified["publication_authorized"] is False
    write_artifacts(local_fixture, [{**ARTIFACT, "revision": "another-revision"}])
    assert service.verify(package.record_id, snapshot)["status"] == "drift"
    result = service.search(
        SearchRequest(query=package.package_id, filters=Filters(source="candidates"))
    )
    assert result["results"][0]["upstream"] == UPSTREAM
