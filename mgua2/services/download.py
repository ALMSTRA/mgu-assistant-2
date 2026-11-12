"""Descargas verificadas: HTTP con progreso, SHA256, SHA256SUMS, zip/gz
seguros y consultas minimas a la API de GitHub. Sin dependencias externas
(urllib). Todo lo descargado es DATO no confiable: se extrae en su propia
carpeta con proteccion contra path traversal y nunca se ejecuta desde aqui.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ..i18n import tr

ProgressCb = Callable[[int, int], None]  # (bytes_recibidos, total o -1)

USER_AGENT = "MGU-Assistant-2 (+https://github.com)"
GITHUB_API = "https://api.github.com"


class DownloadError(RuntimeError):
    pass


def _open(url: str, timeout: float = 30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_json(url: str, timeout: float = 30) -> dict | list:
    try:
        with _open(url, timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # "HTTP <codigo>" al principio en ambos idiomas: github_latest_release() busca "HTTP 404".
        raise DownloadError(tr(f"HTTP {e.code} al consultar {url}", f"HTTP {e.code} when querying {url}")) from e
    except Exception as e:
        raise DownloadError(tr(f"No se pudo consultar {url}: {e}", f"Could not query {url}: {e}")) from e


def fetch_text(url: str, timeout: float = 30) -> str:
    try:
        with _open(url, timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        raise DownloadError(tr(f"No se pudo descargar {url}: {e}", f"Could not download {url}: {e}")) from e


def download_file(url: str, dest: Path, *, progress: Optional[ProgressCb] = None,
                  timeout: float = 60, retries: int = 2) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            with _open(url, timeout) as r, open(tmp, "wb") as f:
                total = int(r.headers.get("Content-Length") or -1)
                got = 0
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if progress:
                        progress(got, total)
            tmp.replace(dest)
            return dest
        except Exception as e:
            last_err = e
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
    raise DownloadError(tr(f"No se pudo descargar {url}: {last_err}", f"Could not download {url}: {last_err}"))


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_sha256sums(text: str) -> dict[str, str]:
    """Formato `<sha256>  <nombre>` (acepta '*nombre')."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and len(parts[0]) == 64:
            name = parts[1].lstrip("*")
            out[name] = parts[0].lower()
    return out


def verify_sha256(path: Path, expected: str) -> None:
    got = sha256_of(path)
    if got.lower() != expected.lower():
        # El Doctor reconoce ambos textos ("sha256 no coincide" / "sha256 does not match").
        raise DownloadError(tr(f"SHA256 no coincide para {path.name}: {got} != {expected}",
                               f"SHA256 does not match for {path.name}: {got} != {expected}"))


def gunzip_to(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(src, "rb") as g, open(dest, "wb") as f:
        shutil.copyfileobj(g, f)
    return dest


def safe_extract_zip(zip_path: Path, dest_dir: Path, *, strip_top: bool = False) -> Path:
    """Extrae un zip evitando path traversal. `strip_top` quita la carpeta
    raiz unica (p. ej. `repo-main/`)."""
    dest_dir = Path(dest_dir).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        top = ""
        if strip_top and names:
            first = names[0].split("/")[0]
            if all(n.split("/")[0] == first for n in names):
                top = first + "/"
        for info in z.infolist():
            name = info.filename
            if top and name.startswith(top):
                name = name[len(top):]
            if not name or name.endswith("/"):
                continue
            target = (dest_dir / name).resolve()
            if dest_dir not in target.parents and target != dest_dir:
                raise DownloadError(tr(f"Entrada peligrosa en zip: {info.filename}", f"Dangerous zip entry: {info.filename}"))
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as f:
                shutil.copyfileobj(src, f)
    return dest_dir


# --- GitHub ------------------------------------------------------------------
@dataclass(frozen=True)
class ReleaseAsset:
    tag: str
    name: str
    url: str
    size: int


def github_latest_release_asset(owner: str, repo: str, name_contains: str) -> ReleaseAsset:
    data = fetch_json(f"{GITHUB_API}/repos/{owner}/{repo}/releases/latest")
    tag = str(data.get("tag_name", ""))
    for a in data.get("assets", []):
        if name_contains.lower() in str(a.get("name", "")).lower():
            return ReleaseAsset(tag, a["name"], a["browser_download_url"], int(a.get("size", 0)))
    raise DownloadError(tr(f"El release {tag} de {owner}/{repo} no tiene un activo '{name_contains}'.",
                           f"Release {tag} of {owner}/{repo} has no '{name_contains}' asset."))


@dataclass(frozen=True)
class RepoInfo:
    full_name: str
    default_branch: str
    stars: int
    pushed_at: str
    description: str
    fork_of: str = ""


def github_repo_info(owner: str, repo: str) -> RepoInfo:
    data = fetch_json(f"{GITHUB_API}/repos/{owner}/{repo}")
    parent = data.get("parent") or {}
    return RepoInfo(
        full_name=str(data.get("full_name", f"{owner}/{repo}")),
        default_branch=str(data.get("default_branch") or "main"),
        stars=int(data.get("stargazers_count") or 0),
        pushed_at=str(data.get("pushed_at") or ""),
        description=str(data.get("description") or ""),
        fork_of=str(parent.get("full_name") or ""),
    )


def github_search_repos(query: str, per_page: int = 20) -> list[RepoInfo]:
    """Busqueda de repositorios (sin autenticacion: ~10 consultas/minuto)."""
    q = urllib.request.quote(query)
    data = fetch_json(f"{GITHUB_API}/search/repositories?q={q}&sort=updated&per_page={per_page}")
    out: list[RepoInfo] = []
    for it in data.get("items", []) if isinstance(data, dict) else []:
        out.append(RepoInfo(
            full_name=str(it.get("full_name", "")), default_branch=str(it.get("default_branch") or "main"),
            stars=int(it.get("stargazers_count") or 0), pushed_at=str(it.get("pushed_at") or ""),
            description=str(it.get("description") or ""), fork_of="(fork)" if it.get("fork") else "",
        ))
    return out


@dataclass(frozen=True)
class Release:
    tag: str
    assets: list[tuple[str, str]]  # (nombre, url)


def github_latest_release(owner: str, repo: str) -> Optional[Release]:
    """Ultimo release (None si el repo no publica releases)."""
    try:
        data = fetch_json(f"{GITHUB_API}/repos/{owner}/{repo}/releases/latest")
    except DownloadError as e:
        if "HTTP 404" in str(e):
            return None
        raise
    assets = [(str(a.get("name", "")), str(a.get("browser_download_url", ""))) for a in data.get("assets", [])]
    return Release(tag=str(data.get("tag_name", "")), assets=assets)


def github_branch_head(owner: str, repo: str, branch: str = "main") -> tuple[str, str]:
    """(sha, fecha ISO) del ultimo commit de la rama."""
    data = fetch_json(f"{GITHUB_API}/repos/{owner}/{repo}/commits/{branch}")
    sha = str(data.get("sha", ""))
    date = str(((data.get("commit") or {}).get("committer") or {}).get("date", ""))
    return sha, date


def github_zip_url(owner: str, repo: str, ref: str = "main") -> str:
    return f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{ref}"
