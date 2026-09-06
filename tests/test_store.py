import pytest

from specsearch import store as store_module
from specsearch.models import Filters
from specsearch.store import Store, collapse, tokens


def test_filters_exact_and_snapshot(tmp_path, package_factory):
    store = Store(tmp_path)
    assert store.status()["snapshot"] is None
    active = store.build([package_factory(), package_factory("other", yanked=True)])
    snap = active["snapshot"]
    assert store.lexical("compress", Filters(), snap) == []
    filters = Filters(source="candidates")
    assert collapse(store.lexical("compress", filters, snap)) == ["rtk.proxy"]
    assert store.exact("intent.compress", filters, snap)[0].package_id == "rtk.proxy"
    assert store.exact("rtk.proxy@1.0.0", filters, snap)
    assert not store.lexical("compress", Filters(source="all", license="MIT"), snap)
    store.build([])
    assert store.package("rtk.proxy", snap).package_id == "rtk.proxy"
    with pytest.raises(LookupError):
        store.package("rtk.proxy")


def test_atomic_failed_build(tmp_path, package_factory):
    store = Store(tmp_path)
    snap = store.build([package_factory()])["snapshot"]
    with pytest.raises(Exception):
        store.build([package_factory(), package_factory()])
    assert store.active() == snap


def test_quoted_unicode_search(tmp_path, package_factory):
    store = Store(tmp_path)
    snap = store.build([package_factory(text="сжатие вывода HTTPClient")])["snapshot"]
    assert store.lexical('сжатие " OR *', Filters(source="all"), snap)
    assert tokens("helloWorld_pkg.id") == ["hello", "world", "pkg", "id"]


def test_acronym_boundaries(tmp_path, package_factory):
    assert tokens("HTTPClient JSONParser parseHTTPResponse") == [
        "http",
        "client",
        "json",
        "parser",
        "parse",
        "http",
        "response",
    ]
    store = Store(tmp_path)
    snap = store.build([package_factory(text="HTTPClient JSONParser")])["snapshot"]
    for query in ("http", "client", "json", "parser"):
        assert store.lexical(query, Filters(source="all"), snap)


@pytest.mark.parametrize("error", [KeyboardInterrupt, SystemExit])
def test_interrupt_after_publication_preserves_active_db(
    tmp_path, package_factory, monkeypatch, error
):
    store = Store(tmp_path)
    store.build([])
    replace = store_module.os.replace

    def interrupted_replace(source, destination):
        replace(source, destination)
        raise error()

    monkeypatch.setattr(store_module.os, "replace", interrupted_replace)
    with pytest.raises(error):
        store.build([package_factory()])
    assert store.package("rtk.proxy").package_id == "rtk.proxy"
    assert store.status()["packages"] == 1


def test_interrupt_before_publication_removes_incomplete_db(tmp_path, monkeypatch):
    store = Store(tmp_path)
    snapshot = store.build([])["snapshot"]

    def interrupted_fsync(fd):
        raise KeyboardInterrupt()

    monkeypatch.setattr(store_module.os, "fsync", interrupted_fsync)
    with pytest.raises(KeyboardInterrupt):
        store.build([])
    assert store.active() == snapshot
    assert list(tmp_path.glob("*.db")) == [tmp_path / f"{snapshot}.db"]


def test_missing_snapshot_is_lookup_error(tmp_path):
    store = Store(tmp_path)
    snapshot = "a" * 32
    with pytest.raises(LookupError, match="snapshot_not_found"):
        with store.connect(snapshot):
            pytest.fail("missing snapshot connected")
    assert not (tmp_path / f"{snapshot}.db").exists()
    with pytest.raises(LookupError, match="snapshot_not_found"):
        store.package("missing", snapshot)


def test_snapshot_disappears_before_connect(tmp_path, monkeypatch):
    store = Store(tmp_path)
    snapshot = store.build([])["snapshot"]
    connect = store_module.sqlite3.connect

    def removed_connect(*args, **kwargs):
        (tmp_path / f"{snapshot}.db").unlink()
        return connect(*args, **kwargs)

    monkeypatch.setattr(store_module.sqlite3, "connect", removed_connect)
    with pytest.raises(LookupError, match="snapshot_not_found"):
        with store.connect(snapshot):
            pytest.fail("missing snapshot connected")
