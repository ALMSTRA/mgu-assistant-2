"""Idioma de la interfaz: espanol (por defecto) o ingles.

Cada texto visible se escribe con sus dos versiones en el sitio donde se usa:

    tr("Probar SSH", "Test SSH")

asi no hay catalogos que se desincronicen. El idioma se fija UNA vez al arrancar (`set_language`)
antes de importar la UI, porque varios textos son constantes de modulo; cambiarlo desde la app
guarda la preferencia y reinicia la ventana.

Nunca se traduce la salida de las herramientas upstream: la consola la muestra tal cual.
"""
from __future__ import annotations

import json
import locale
import os
from pathlib import Path
from typing import Optional

LANGUAGES = {"es": "Español", "en": "English"}
DEFAULT = "es"
_current = DEFAULT


def tr(es: str, en: str) -> str:
    """Texto en el idioma activo."""
    return en if _current == "en" else es


def get_language() -> str:
    return _current


def set_language(lang: Optional[str]) -> str:
    global _current
    _current = lang if lang in LANGUAGES else DEFAULT
    return _current


def system_language() -> str:
    """'es' si el sistema esta en espanol; si no, 'en'."""
    candidates = [os.environ.get(k, "") for k in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")]
    try:
        candidates.append(locale.getlocale()[0] or "")
    except Exception:
        pass
    if os.name == "nt":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, len(buf)):
                candidates.append(buf.value)
        except Exception:
            pass
    for c in candidates:
        if c:
            return "es" if c.lower().replace("-", "_").startswith(("es", "spanish")) else "en"
    return DEFAULT


def _settings_file(state_dir: Path) -> Path:
    return Path(state_dir) / "settings.json"


def load_saved(state_dir: Path) -> Optional[str]:
    try:
        lang = json.loads(_settings_file(state_dir).read_text(encoding="utf-8")).get("language")
        return lang if lang in LANGUAGES else None
    except Exception:
        return None


def save(state_dir: Path, lang: str) -> None:
    f = _settings_file(state_dir)
    try:
        data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    data["language"] = lang if lang in LANGUAGES else DEFAULT
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, indent=2), encoding="utf-8")
