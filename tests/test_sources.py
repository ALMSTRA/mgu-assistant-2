import pytest

from mgua2.core.context import AppContext
from mgua2.core.paths import data_paths
from mgua2.services.sources import COMMUNITY_SNAPSHOT, OFFICIAL_REPOS, SourcesManager


def test_snapshot_has_no_official_and_is_sorted():
    assert not any(s.repo in OFFICIAL_REPOS for s in COMMUNITY_SNAPSHOT)
    assert all("/" in s.repo for s in COMMUNITY_SNAPSHOT)


def test_snapshot_unique_and_blocked_rejected(tmp_path):
    import pytest
    from mgua2.services.sources import BLOCKED_SOURCES, SourcesManager
    repos = [s.repo.lower() for s in COMMUNITY_SNAPSHOT]
    assert len(repos) == len(set(repos)) and len(repos) >= 78
    assert not set(repos) & {r.lower() for r in BLOCKED_SOURCES}
    m = SourcesManager(data_paths(tmp_path).ensure())
    with pytest.raises(ValueError):
        m.add_custom("https://github.com/mlurker/bmw-idrive7-releases")
    with pytest.raises(ValueError):
        m.add_custom("hexlay/mgu-store")


def test_enable_persist_and_custom(tmp_path):
    sm = SourcesManager(data_paths(tmp_path).ensure())
    assert sm.enabled() == []  # comunitarias: opcionales, ninguna por defecto
    sm.set_enabled("bimmer-lab/apps", True)
    assert sm.is_enabled("bimmer-lab/apps") and "bimmer-lab/apps" in sm.enabled()
    s = sm.add_custom("https://github.com/alguien/mi-apps.git")
    assert s.repo == "alguien/mi-apps" and s.custom
    with pytest.raises(ValueError):
        sm.add_custom("no-es-un-repo")
    # persiste
    sm2 = SourcesManager(data_paths(tmp_path))
    assert sm2.is_enabled("bimmer-lab/apps") and any(x.repo == "alguien/mi-apps" for x in sm2.all_known())


def test_official_never_counted_as_extra(tmp_path):
    sm = SourcesManager(data_paths(tmp_path).ensure())
    sm.set_enabled("robertnisipeanu/mgu-store", True)
    assert "robertnisipeanu/mgu-store" not in sm.enabled()


def test_all_known_sorted_by_stars(tmp_path):
    sm = SourcesManager(data_paths(tmp_path).ensure())
    known = sm.all_known()
    stars = [s.stars for s in known]
    assert stars == sorted(stars, reverse=True)
    assert known[0].repo == "PenguinDukeYDAuto/idrive7-EVAHUD"


def test_demo_catalog_ignores_extras():
    ctx = AppContext(demo=True)
    ctx.sources.set_enabled("bimmer-lab/apps", True)
    assert len(ctx.build_catalog()) >= 40  # demo: solo fixtures oficiales
    ctx.close()


def test_release_layout_manifest_scanned(tmp_path):
    import json
    from mgua2.catalog.scanner import scan_repo
    d = tmp_path / "evan__apps"
    d.mkdir()
    (d / "_mgua2_release.json").write_text(json.dumps({"tag": "v1.5.0", "apps": [
        {"id": "exhaust_flap", "title": "Exhaust & Start/Stop", "description": "Open or close the exhaust flap", "version": "1.4.0"},
        {"id": "gentleman", "title": "Gentleman Function", "description": "Move the passenger seat", "version": "2.1.0"},
    ]}), encoding="utf-8")
    items = {i.id: i for i in scan_repo(d, "evan/apps")}
    assert items["exhaust_flap"].version == "1.4.0" and items["exhaust_flap"].id7 and items["exhaust_flap"].experimental
    assert str(items["exhaust_flap"].risk) == "red"  # 'exhaust' en el nombre -> control
    assert items["gentleman"].repo == "evan/apps"


@pytest.mark.net
def test_fetch_real_sources_tree_and_releases(tmp_path):
    from mgua2.core.logbus import LogBus
    from mgua2.services.tools import ToolsManager
    from mgua2.catalog.scanner import CatalogScanner
    paths = data_paths(tmp_path).ensure()
    tm = ToolsManager(paths, LogBus(None))
    a = tm.fetch_source("bimmer-lab/apps")
    b = tm.fetch_source("evangoyuk/mgu-store-apps")
    assert a.ok and b.ok
    items = CatalogScanner(paths.repos).scan([("bimmer-lab/apps", "bimmer-lab__apps"),
                                              ("evangoyuk/mgu-store-apps", "evangoyuk__mgu-store-apps")])
    by_repo = {}
    for i in items:
        by_repo.setdefault(i.repo, []).append(i.id)
    assert len(by_repo.get("bimmer-lab/apps", [])) >= 1
    assert "exhaust_flap" in by_repo.get("evangoyuk/mgu-store-apps", [])


@pytest.mark.net
def test_discover_live(tmp_path):
    sm = SourcesManager(data_paths(tmp_path).ensure())
    known = sm.discover()
    assert any(s.repo == "bimmer-lab/apps" for s in known)
