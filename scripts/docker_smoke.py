"""Read-only service smoke against the Docker-exposed port."""

import http.client
import json
import time
import urllib.error
import urllib.request


def call(path, body=None):
    request = urllib.request.Request(
        "http://127.0.0.1:8031" + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    for attempt in range(30):
        try:
            status = call("/v1/status")
            break
        except (OSError, urllib.error.URLError, http.client.RemoteDisconnected):
            if attempt == 29:
                raise
            time.sleep(0.5)
    assert status["packages"] > 0
    for query, source in (
        ("rtk.shell_output_proxy", "candidates"),
        ("document_conversion.email_tools", "registry"),
    ):
        result = call("/v1/search", {"query": query, "filters": {"source": source}})
        assert result["mode"] == "exact" and result["results"]
        record = result["results"][0]
        assert record["source"] == source
        verified = call(
            "/v1/verify", {"record_id": record["record_id"], "snapshot": result["snapshot"]}
        )
        assert verified["status"] == "matched_metadata", verified
    result = call(
        "/v1/search", {"query": "compress shell output", "filters": {"source": "candidates"}}
    )
    assert result["results"] and not result["degraded"]
    print(
        json.dumps(
            {
                "snapshot": status["snapshot"],
                "packages": status["packages"],
                "registry_and_candidate_verification": "passed",
                "hybrid": "passed",
            }
        )
    )


if __name__ == "__main__":
    main()
