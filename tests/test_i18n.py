"""Idioma de la interfaz (mgua2.i18n): espanol por defecto, ingles a peticion.

Cada prueba que cambia el idioma lo devuelve a 'es' (try/finally) para no afectar a las demas,
que comprueban los textos en espanol.
"""
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

from mgua2 import i18n
from mgua2.security.redaction import hide_home, redact

ROOT = Path(__file__).resolve().parent.parent


def test_tr_spanish_by_default_english_on_request():
    # Un proceso nuevo, sin set_language(), habla espanol.
    env = {**os.environ, "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")}
    out = subprocess.run([sys.executable, "-c",
                          "from mgua2 import i18n; print(i18n.get_language(), i18n.tr('Probar', 'Test'))"],
                         cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.split() == ["es", "Probar"], out.stderr
    assert i18n.DEFAULT == "es"
    try:
        assert i18n.set_language("en") == "en" and i18n.get_language() == "en"
        assert i18n.tr("Probar SSH", "Test SSH") == "Test SSH"
        assert i18n.tr(f"Puerto {22}", f"Port {22}") == "Port 22"
        assert i18n.set_language("fr") == "es"            # idioma desconocido -> por defecto
        assert i18n.tr("Probar SSH", "Test SSH") == "Probar SSH"
        i18n.set_language("en")
        assert i18n.set_language(None) == "es"            # sin idioma -> por defecto
    finally:
        i18n.set_language("es")
    assert i18n.get_language() == "es" and i18n.tr("Probar SSH", "Test SSH") == "Probar SSH"


def test_saved_language_roundtrip_and_fallbacks(tmp_path):
    active = i18n.get_language()
    f = tmp_path / "settings.json"
    assert i18n.load_saved(tmp_path) is None                      # sin archivo
    i18n.save(tmp_path, "en")
    assert i18n.load_saved(tmp_path) == "en"
    i18n.save(tmp_path, "es")
    assert i18n.load_saved(tmp_path) == "es"
    i18n.save(tmp_path, "klingon")                                # invalido al guardar -> por defecto
    assert i18n.load_saved(tmp_path) == "es"
    f.write_text(json.dumps({"language": "xx", "otra": 1}), encoding="utf-8")
    assert i18n.load_saved(tmp_path) is None                      # invalido en el archivo -> se ignora
    i18n.save(tmp_path, "en")
    assert json.loads(f.read_text(encoding="utf-8")) == {"language": "en", "otra": 1}   # conserva otras claves
    for junk in ("{no es json", "[1, 2]", ""):
        f.write_text(junk, encoding="utf-8")
        assert i18n.load_saved(tmp_path) is None                  # corrupto / no es un objeto
        i18n.save(tmp_path, "en")                                 # y se rehace al guardar
        assert i18n.load_saved(tmp_path) == "en"
    nested = tmp_path / "nueva" / "state"
    i18n.save(nested, "en")                                       # crea la carpeta si falta
    assert i18n.load_saved(nested) == "en"
    assert i18n.get_language() == active                          # guardar no cambia el idioma activo


def test_hide_home_and_redact_hide_user_folder():
    home = os.path.expanduser("~")
    path = home + r"\AppData\x"
    assert hide_home(path) == r"~\AppData\x"
    assert redact(path) == r"~\AppData\x"
    line = redact(f"Datos en {path}")
    assert home not in line and line == r"Datos en ~\AppData\x"
    if home.upper() != home:                                      # Windows no distingue mayusculas
        assert hide_home(home.upper() + r"\AppData\x") == r"~\AppData\x"
    assert hide_home("") == "" and hide_home("sin rutas") == "sin rutas"


def test_state_reason_in_english_after_reload():
    import mgua2.core.state as state
    try:
        i18n.set_language("en")
        state = importlib.reload(state)
        d = state.StateMachine().can_install_store()
        assert not d.allowed and d.reason == "Verify SSH access first (key + connection)."
    finally:
        i18n.set_language("es")
        state = importlib.reload(state)
    d = state.StateMachine().can_install_store()
    assert not d.allowed and d.reason == "Verifique primero el acceso SSH (llave + conexion)."


def test_catalog_and_vehicle_texts_follow_language():
    from mgua2.catalog import classifier
    from mgua2.catalog.model import CatalogItem
    from mgua2.core.models import Hmi, id7_vehicles

    def snapshot():
        doom = classifier.classify(CatalogItem(id="doom", name="Doom", version="1", repo="r", hmi=[Hmi.ID7]))
        id8 = CatalogItem(id="x", name="X", version="1", repo="r", hmi=[Hmi.ID8])
        return doom.notes_es, doom.description_es, id8.compatibility_es(), id7_vehicles()[-1].display_name

    try:
        i18n.set_language("en")
        importlib.reload(classifier)          # OVERRIDES es constante de modulo: se evalua al importar
        en = snapshot()
    finally:
        i18n.set_language("es")
        importlib.reload(classifier)
    assert en == (["Parked only."], "Doom (Freedoom: Phase 1) on the iDrive screen.",
                  "Not applicable to iDrive 7 (declares ID8 only).", "Other BMW with iDrive 7")
    assert snapshot() == (["Solo estacionado."], "Doom (Freedoom: Phase 1) en la pantalla iDrive.",
                          "No aplica a iDrive 7 (declara solo ID8).", "Otro BMW con iDrive 7")
