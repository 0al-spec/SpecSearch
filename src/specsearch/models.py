from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FieldText(StrictModel):
    path: str
    text: str


class Document(StrictModel):
    id: str
    spec_id: str | None = None
    fields: list[FieldText]

    @property
    def text(self) -> str:
        return "\n".join(item.text for item in self.fields)


class Package(StrictModel):
    record_id: str
    source_id: str
    source_kind: Literal["registry", "candidates"]
    package_id: str
    version: str
    name: str
    summary: str = ""
    license: str | None = None
    digest: str
    capabilities: list[str] = Field(default_factory=list)
    intents: list[str] = Field(default_factory=list)
    yanked: bool = False
    deprecated: bool = False
    metadata_only: bool = False
    observed_at: str
    documents: list[Document]
    details: dict = Field(default_factory=dict)
    evidence: list[dict] = Field(default_factory=list)
    provenance: dict = Field(default_factory=dict)
    locator: dict = Field(default_factory=dict)

    def public(self):
        return self.model_dump(exclude={"locator"})


class Filters(StrictModel):
    source: Literal["registry", "candidates", "all"] = "registry"
    source_id: str | None = None
    package: str | None = None
    version: str | None = None
    license: str | None = None
    capability: str | None = None
    intent: str | None = None
    include_inactive: bool = False


class SearchRequest(StrictModel):
    query: str = Field(min_length=1, max_length=1000)
    mode: Literal["lexical", "vector", "hybrid"] = "hybrid"
    top_k: int = Field(default=10, ge=1, le=50)
    filters: Filters = Field(default_factory=Filters)
