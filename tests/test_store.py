import pytest

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
