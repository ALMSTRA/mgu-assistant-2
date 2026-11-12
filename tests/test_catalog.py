import pytest

from mgua2.catalog.scanner import CatalogScanner
from mgua2.core.demo import fixtures_root
from mgua2.core.models import Hmi, RiskLevel


@pytest.fixture(scope="module")
def by_id():
    return {i.id: i for i in CatalogScanner(fixtures_root() / "repos").scan()}


def test_catalog_size(by_id):
    assert len(by_id) >= 40


def test_id7_inheritance_and_filters(by_id):
    assert by_id["warmup"].hmi == [Hmi.ID7] and by_id["warmup"].id7
    # car-apps "Car Data" 1.2.0+ se declaro "iDrive 8 only" (nov-2026): debe salir gris.
    assert not by_id["iteriodev_cardash"].id7
    assert by_id["iteriodev_cardash"].effective_risk() == RiskLevel.GREY
    # Screen Share paso a ID7+ID8 en car-apps 1.0.8: el catalogo lo descubre solo.
    assert "iteriodev-screencast" in by_id
    assert any(not i.id7 for i in by_id.values()) and any(i.id7 for i in by_id.values())


def test_risk_classification(by_id):
    assert by_id["warmup"].risk == RiskLevel.GREEN
    assert by_id["dtc_scanner"].risk == RiskLevel.RED and by_id["dtc_scanner"].clears_faults
    assert by_id["live_adjustments"].risk == RiskLevel.RED
    assert by_id["doom"].parked_only
    assert by_id["dyno"].track_only and by_id["draggy"].track_only
    assert by_id["robertn_waze_cluster"].reversible_patch


def test_new_apps_discovered(by_id):
    # Apps anadidas la semana del 8-nov-2026: descubiertas por manifiesto, no por lista fija.
    for new in ("ambient_config", "oap-driverecorder-next", "iteriodev_seats"):
        assert new in by_id, new


def test_base_tools_not_grey(by_id):
    for t in ("mgu-deploy", "mgu-updater", "mgu-uplink"):
        assert by_id[t].id7
