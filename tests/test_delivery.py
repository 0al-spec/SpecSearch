import io
import json
import urllib.request
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from specsearch.api import create_app
from specsearch.service import SearchService
from specsearch.store import Store


@pytest.mark.parametrize("snapshot,code", [(None, 1), ("a" * 32, 0)])
def test_healthcheck_requires_active_snapshot(monkeypatch, snapshot, code):
    command = yaml.safe_load(Path("compose.yaml").read_text())["services"]["specsearch"][
        "healthcheck"
    ]["test"][-1]
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *a, **kw: io.BytesIO(json.dumps({"snapshot": snapshot}).encode()),
    )
    with pytest.raises(SystemExit) as result:
        exec(command, {})
    assert result.value.code == code


def test_static_bundle_is_shipped(tmp_path):
    from specsearch.cli import main

    assert callable(main)
    client = TestClient(create_app(SearchService(Store(tmp_path))))
    assert client.get("/app.js").status_code == 200
    assert client.get("/fonts/InstrumentSerif.ttf").status_code == 200
