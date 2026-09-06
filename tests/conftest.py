import pytest
import yaml

from specsearch.models import Document, FieldText, Package


@pytest.fixture
def package_factory():
    def make(pid="rtk.proxy", text="Compress shell output for coding agents", **kwargs):
        return Package(
            record_id=pid,
            source_id="fixture",
            source_kind="candidates",
            package_id=pid,
            version="1.0.0",
            name=pid,
            digest="a" * 64,
            capabilities=[pid + ".run"],
            intents=["intent.compress"],
            observed_at="2026-09-06T00:00:00+00:00",
            documents=[Document(id=pid, fields=[FieldText(path="intent.summary", text=text)])],
            **kwargs,
        )

    return make


@pytest.fixture
def local_fixture(tmp_path):
    root = tmp_path / "package"
    (root / "specs").mkdir(parents=True)
    manifest = {
        "apiVersion": "specpm.dev/v0.1",
        "kind": "SpecPackage",
        "metadata": {
            "id": "fixture.proxy",
            "name": "Fixture Proxy",
            "version": "0.1.0",
            "summary": "Compress shell output",
            "license": "MIT",
        },
        "specs": [{"path": "specs/main.spec.yaml"}],
        "index": {
            "provides": {"capabilities": ["fixture.proxy"]},
            "requires": {"capabilities": []},
        },
        "compatibility": {"platforms": ["any"], "languages": []},
        "foreignArtifacts": [],
    }
    spec = {
        "apiVersion": "specpm.dev/v0.1",
        "kind": "BoundarySpec",
        "metadata": {
            "id": "fixture.proxy",
            "title": "Fixture",
            "version": "0.1.0",
            "status": "draft",
        },
        "intent": {"summary": "Compress shell output"},
        "scope": {"boundedContext": "fixture", "includes": ["Output filtering"], "excludes": []},
        "provides": {
            "capabilities": [
                {"id": "fixture.proxy", "role": "primary", "summary": "Compress command output"}
            ]
        },
        "requires": {"capabilities": []},
        "interfaces": {
            "inbound": [{"id": "cli", "kind": "cli", "summary": "Read command"}],
            "outbound": [],
        },
        "effects": {"sideEffects": []},
        "constraints": [{"id": "inert", "level": "MUST", "statement": "Do not execute fixture"}],
        "evidence": [{"id": "manual", "kind": "manual_assertion", "supports": ["intent.summary"]}],
        "provenance": {"sourceConfidence": {"intent": "low", "boundary": "low", "behavior": "low"}},
    }
    (root / "specpm.yaml").write_text(yaml.safe_dump(manifest))
    (root / "specs/main.spec.yaml").write_text(yaml.safe_dump(spec))
    return root
