import pytest

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
