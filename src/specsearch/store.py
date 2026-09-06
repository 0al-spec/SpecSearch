from __future__ import annotations

import fcntl
import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from .models import Filters, Package, digest, now


def tokens(text):
    expanded = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    expanded = re.sub(r"([a-z])([A-Z])", r"\1 \2", expanded)
    return re.findall(r"[^\W_]+", expanded.casefold(), re.UNICODE)


def predicate(filters: Filters):
    clauses, args = ["1=1"], []
    if filters.source != "all":
        clauses.append("p.kind=?")
        args.append(filters.source)
    for name, column in (
        ("source_id", "source_id"),
        ("package", "pid"),
        ("version", "version"),
        ("license", "license"),
    ):
        value = getattr(filters, name)
        if value is not None:
            clauses.append(f"p.{column}=?")
            args.append(value)
    for name, field in (("capability", "capabilities"), ("intent", "intents")):
        value = getattr(filters, name)
        if value is not None:
            clauses.append(f"EXISTS(SELECT 1 FROM json_each(p.payload,'$.{field}') WHERE value=?)")
            args.append(value)
    if not filters.include_inactive:
        clauses.append("p.inactive=0")
    return " AND ".join(clauses), args


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def active(self):
        pointer = self.root / "active.json"
        if not pointer.exists():
            raise LookupError("index_not_built")
        value = json.loads(pointer.read_text())["snapshot"]
        if not re.fullmatch(r"[0-9a-f]{32}", value):
            raise ValueError("invalid_snapshot_pointer")
        return value

    @contextmanager
    def connect(self, snapshot=None):
        snapshot = self.active() if snapshot is None else snapshot
        if not isinstance(snapshot, str) or not re.fullmatch(r"[0-9a-f]{32}", snapshot):
            raise ValueError("invalid_snapshot")
        path = self.root / (snapshot + ".db")
        if not path.is_file():
            raise LookupError("snapshot_not_found")
        try:
            con = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        except sqlite3.OperationalError:
            if not path.exists():
                raise LookupError("snapshot_not_found") from None
            raise
        con.row_factory = sqlite3.Row
        try:
            yield con
        finally:
            con.close()

    def build(self, packages: list[Package], embedder=None):
        with (self.root / "writer.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return self._build(packages, embedder)

    def _build(self, packages, embedder):
        snapshot = uuid.uuid4().hex
        path = self.root / f"{snapshot}.db"
        con = sqlite3.connect(path)
        publication_started = False
        try:
            con.executescript("""
                CREATE TABLE packages(id TEXT PRIMARY KEY, source_id TEXT, kind TEXT,
                  pid TEXT, version TEXT, license TEXT, inactive INT, payload TEXT);
                CREATE TABLE docs(id INTEGER PRIMARY KEY, record TEXT, payload TEXT);
                CREATE VIRTUAL TABLE terms USING fts5(text, tokenize='unicode61');
                CREATE TABLE vectors(id INTEGER PRIMARY KEY, vector BLOB);
                CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT);
                CREATE INDEX package_filters ON packages(kind, inactive, pid);
            """)
            docs = []
            for package in packages:
                con.execute(
                    "INSERT INTO packages VALUES(?,?,?,?,?,?,?,?)",
                    (
                        package.record_id,
                        package.source_id,
                        package.source_kind,
                        package.package_id,
                        package.version,
                        package.license,
                        int(package.yanked or package.deprecated),
                        package.model_dump_json(),
                    ),
                )
                for doc in package.documents:
                    docid = len(docs) + 1
                    docs.append(doc)
                    con.execute(
                        "INSERT INTO docs VALUES(?,?,?)",
                        (docid, package.record_id, doc.model_dump_json()),
                    )
                    con.execute(
                        "INSERT INTO terms(rowid,text) VALUES(?,?)",
                        (docid, " ".join(tokens(doc.text))),
                    )
            provider = None
            if embedder:
                provider = embedder.identity()
                vectors = embedder.documents([doc.text for doc in docs])
                if embedder.identity() != provider:
                    raise ValueError("model_changed_during_build")
                if len(vectors) != len(docs):
                    raise ValueError("vector_count_mismatch")
                for i, vector in enumerate(vectors, 1):
                    con.execute("INSERT INTO vectors VALUES(?,?)", (i, vector.tobytes()))
            metadata = {
                "snapshot": snapshot,
                "created_at": now(),
                "packages": len(packages),
                "documents": len(docs),
                "provider": provider,
                "corpus_digest": digest(sorted(p.record_id for p in packages)),
                "collections": {
                    kind: sum(p.source_kind == kind for p in packages)
                    for kind in ("registry", "candidates")
                },
            }
            con.execute("INSERT INTO metadata VALUES('status',?)", (json.dumps(metadata),))
            con.commit()
            con.close()
            with path.open("rb") as file:
                os.fsync(file.fileno())
            temporary = self.root / f"{snapshot}.pointer"
            temporary.write_text(json.dumps({"snapshot": snapshot}))
            with temporary.open("rb") as file:
                os.fsync(file.fileno())
            # An interrupt can arrive after replace succeeds but before it returns.
            publication_started = True
            os.replace(temporary, self.root / "active.json")
            return metadata
        except BaseException:
            con.close()
            if not publication_started:
                path.unlink(missing_ok=True)
            raise

    def status(self):
        try:
            with self.connect() as con:
                return json.loads(
                    con.execute("SELECT value FROM metadata WHERE key='status'").fetchone()[0]
                )
        except LookupError:
            return {"snapshot": None, "packages": 0, "documents": 0, "provider": None}

    def package(self, record_id, snapshot=None):
        with self.connect(snapshot) as con:
            row = con.execute("SELECT payload FROM packages WHERE id=?", (record_id,)).fetchone()
            if row is None:
                raise LookupError("package_not_found")
            return Package.model_validate_json(row[0])

    def exact(self, query, filters, snapshot):
        where, args = predicate(filters)
        with self.connect(snapshot) as con:
            rows = con.execute(f"SELECT payload FROM packages p WHERE {where} ORDER BY p.id", args)
            result = []
            for row in rows:
                p = Package.model_validate_json(row[0])
                if query in [
                    p.package_id,
                    f"{p.package_id}@{p.version}",
                    *p.capabilities,
                    *p.intents,
                ]:
                    result.append(p)
            return result

    def lexical(self, query, filters, snapshot):
        words = list(dict.fromkeys(tokens(query)))[:100]
        if not words:
            return []
        match = " OR ".join('"' + word + '"' for word in words)
        where, args = predicate(filters)
        with self.connect(snapshot) as con:
            rows = con.execute(
                f"""SELECT d.record,d.payload,bm25(terms) AS score
                FROM terms JOIN docs d ON d.id=terms.rowid JOIN packages p ON p.id=d.record
                WHERE terms MATCH ? AND {where} ORDER BY score, d.id LIMIT 50""",
                [match, *args],
            )
            return [
                {"record_id": row[0], "document": json.loads(row[1]), "score": -row[2]}
                for row in rows
            ]


def collapse(hits):
    return list(dict.fromkeys(hit["record_id"] for hit in hits))
