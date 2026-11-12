"""Censura de datos sensibles en texto (consola, archivos de log, portapapeles).

Nunca en claro: VIN completo, tokens de GitHub, material de llaves privadas
(OpenSSH, PEM PKCS#1/#8, PPK). Idempotente y segura sobre texto arbitrario.
"""
from __future__ import annotations

import re

from ..i18n import tr

# Marcas visibles en consola/log (idioma fijado al arrancar). Ninguna contiene 17 caracteres
# seguidos de VIN, asi que redact() sigue siendo idempotente en ambos idiomas.
VIN_MARK = tr("[VIN-CENSURADO]", "[VIN-REDACTED]")
TOKEN_MARK = tr("[TOKEN-CENSURADO]", "[TOKEN-REDACTED]")
KEY_MARK = tr("[LLAVE-PRIVADA-CENSURADA]", "[PRIVATE-KEY-REDACTED]")
PATH_MARK = tr("[RUTA-CENSURADA]", "[PATH-REDACTED]")

_VIN_CHARS = "A-HJ-NPR-Z0-9"
_VIN_RE = re.compile(rf"(?<![{_VIN_CHARS}])[{_VIN_CHARS}]{{17}}(?![{_VIN_CHARS}])")
_VIN_ARG_RE = re.compile(r"(--vin[=\s]+)(\S+)", re.IGNORECASE)
_GH_TOKEN_RE = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})\b")
_AUTH_HEADER_RE = re.compile(r"(Authorization:\s*(?:Bearer|token)\s+)(\S+)", re.IGNORECASE)
_PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN (?:[A-Z0-9 ]*?)PRIVATE KEY-----.*?-----END (?:[A-Z0-9 ]*?)PRIVATE KEY-----",
    re.DOTALL,
)
_PPK_HEADER_RE = re.compile(r"^PuTTY-User-Key-File-\d.*$", re.MULTILINE)
_PRIVATE_KEY_BEGIN_RE = re.compile(r"-----BEGIN (?:[A-Z0-9 ]*?)PRIVATE KEY-----.*$", re.MULTILINE)


def _home_variants() -> list[str]:
    """Rutas de la carpeta del usuario (C:\\Users\\<nombre>) en sus formas habituales."""
    import os
    homes = {os.path.expanduser("~"), os.environ.get("USERPROFILE", ""), os.environ.get("HOME", "")}
    out: list[str] = []
    for h in homes:
        h = (h or "").rstrip("\\/")
        if len(h) < 4:
            continue
        for v in (h, h.replace("\\", "/"), h.replace("\\", "\\\\")):
            if v not in out:
                out.append(v)
    return sorted(out, key=len, reverse=True)


_HOMES = _home_variants()


def hide_home(text: str) -> str:
    """Sustituye la carpeta del usuario por '~' para no mostrar el nombre de usuario de Windows
    en consola, logs ni capturas (encontrado en las capturas del README el 2026-11-12)."""
    if not text:
        return text
    for h in _HOMES:
        if h in text:
            text = text.replace(h, "~")
        else:
            low = text.lower()
            i = low.find(h.lower())
            while i >= 0:
                text = text[:i] + "~" + text[i + len(h):]
                low = text.lower()
                i = low.find(h.lower(), i + 1)
    return text


def mask_vin(vin: str) -> str:
    """Primeros 3 + ... + ultimos 2; nunca el bloque de serie."""
    vin = (vin or "").strip()
    if len(vin) < 6:
        return VIN_MARK
    return f"{vin[:3]}{'*' * (len(vin) - 5)}{vin[-2:]}"


def redact(text: str, extra_vins: list[str] | None = None) -> str:
    if not text:
        return text
    text = _PRIVATE_KEY_BLOCK_RE.sub(KEY_MARK, text)
    text = _PPK_HEADER_RE.sub(KEY_MARK, text)
    text = _PRIVATE_KEY_BEGIN_RE.sub(KEY_MARK, text)
    text = _GH_TOKEN_RE.sub(TOKEN_MARK, text)
    text = _AUTH_HEADER_RE.sub(rf"\1{TOKEN_MARK}", text)
    for vin in extra_vins or []:
        if vin:
            text = text.replace(vin, VIN_MARK)
    text = _VIN_ARG_RE.sub(rf"\1{VIN_MARK}", text)
    text = _VIN_RE.sub(VIN_MARK, text)
    return hide_home(text)


def redact_args(args: list[str], extra_vins: list[str] | None = None) -> list[str]:
    """Censura una lista de argumentos para MOSTRARLA (nunca para ejecutar)."""
    out: list[str] = []
    mask_as: str | None = None
    for a in args:
        if mask_as is not None:
            out.append(mask_as if (a and not a.startswith("-")) else a)
            mask_as = None
            continue
        low = a.lower()
        if low == "--vin":
            out.append(a); mask_as = VIN_MARK; continue
        if low in ("--identity", "-i"):
            out.append(a); mask_as = PATH_MARK; continue
        if low.startswith("--vin="):
            out.append("--vin=" + VIN_MARK); continue
        if low.startswith("--identity="):
            out.append("--identity=" + PATH_MARK); continue
        out.append(redact(a, extra_vins=extra_vins))
    return out
