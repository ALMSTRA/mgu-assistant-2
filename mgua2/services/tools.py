"""Gestor de herramientas: descarga y verifica todo lo necesario.

- Codigo de la herramienta oficial de SSH (zip de GitHub, sin git) -> repos/
- GUI oficial prebuilt MGU-SSH.exe (release de GitHub) -> tools/MGU-SSH/
- Instalador standalone del Store `mgu-install` (verificado con SHA256SUMS) -> tools/
- Repositorios de apps (zip) para el catalogo -> repos/

Guarda versiones/commits en state/tools.json y preserva los datos del usuario
(enrollments, respaldos preflight, logs) al actualizar.
"""
from __future__ import annotations

import datetime as _dt
import json
import platform
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..core.logbus import LogBus
from ..core.paths import DataPaths
from ..i18n import tr
from . import download as dl

ProgressCb = Callable[[str, int, int], None]  # (etiqueta, recibido, total)

# Repositorios oficiales (owner, repo). URLs exactas; nada mas se descarga.
UPSTREAM: dict[str, tuple[str, str]] = {
    "idrive7-8-ssh-root": ("cauliflowermossgrape", "idrive7-8-ssh-root"),
    "mgu-store": ("robertnisipeanu", "mgu-store"),
    "idrive7-apps": ("cauliflowermossgrape", "idrive7-apps"),
    "idrive-apps": ("robertnisipeanu", "idrive-apps"),
    "car-apps": ("IterioDev", "car-apps"),
}
SSH_REPO = "idrive7-8-ssh-root"
STORE_REPO = "mgu-store"
APP_REPOS = ("idrive7-apps", "idrive-apps", "car-apps", "mgu-store")
MGU_INSTALL_BASE = "https://github.com/robertnisipeanu/mgu-store/releases/download/installer"
# Subcarpetas de datos del usuario dentro del tool que NUNCA se pierden al actualizar.
PRESERVE_SUBDIRS = ("data/enrollments", "data/preflight", "data/logs")


@dataclass
class ToolInfo:
    name: str
    ok: bool = False
    version: str = ""     # commit corto o tag
    date: str = ""
    path: str = ""
    detail: str = ""


def _ssh_source_name() -> str:
    return tr("Codigo SSH tool", "SSH tool source code")


def _ssh_prebuilt_name() -> str:
    return tr("GUI oficial MGU-SSH.exe", "Official MGU-SSH.exe GUI")


def _mgu_install_name() -> str:
    return tr("Instalador mgu-install", "mgu-install installer")


@dataclass
class ToolsStatus:
    ssh_source: ToolInfo = field(default_factory=lambda: ToolInfo(_ssh_source_name()))
    ssh_prebuilt: ToolInfo = field(default_factory=lambda: ToolInfo(_ssh_prebuilt_name()))
    mgu_install: ToolInfo = field(default_factory=lambda: ToolInfo(_mgu_install_name()))
    repos: dict[str, ToolInfo] = field(default_factory=dict)

    @property
    def all_ready(self) -> bool:
        core = self.ssh_source.ok and self.mgu_install.ok
        gui = self.ssh_prebuilt.ok or not sys.platform.startswith("win")
        return core and gui and all(i.ok for i in self.repos.values())


def _cpu() -> str:
    m = platform.machine().lower()
    if m in ("amd64", "x86_64", "x64"):
        return "x64"
    if m in ("arm64", "aarch64"):
        return "arm64"
    return "x64"


def mgu_install_asset_name() -> str:
    if sys.platform.startswith("win"):
        return f"mgu-install-windows-{_cpu()}.exe.gz"
    if sys.platform == "darwin":
        return f"mgu-install-macos-{_cpu()}.gz"
    return f"mgu-install-linux-{_cpu()}.gz"


class ToolsManager:
    def __init__(self, paths: DataPaths, bus: Optional[LogBus] = None) -> None:
        self.paths = paths
        self.bus = bus
        self._state_file = paths.state / "tools.json"

    # -- estado persistente ------------------------------------------------
    def _load(self) -> dict:
        try:
            return json.loads(self._state_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, data: dict) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _log(self, lvl: str, msg: str) -> None:
        if self.bus:
            self.bus.log(lvl, msg)

    # -- rutas ---------------------------------------------------------------
    def repo_dir(self, name: str) -> Path:
        return self.paths.repos / name

    @property
    def ssh_script(self) -> Path:
        return self.repo_dir(SSH_REPO) / "ssh_enable.py"

    @property
    def ssh_prebuilt_dir(self) -> Path:
        return self.paths.tools / "MGU-SSH"

    @property
    def ssh_prebuilt_exe(self) -> Path:
        return self.ssh_prebuilt_dir / "MGU-SSH.exe"

    @property
    def mgu_install_exe(self) -> Path:
        return self.paths.tools / ("mgu-install.exe" if sys.platform.startswith("win") else "mgu-install")

    # -- estado --------------------------------------------------------------
    MIN_SCRIPT_BYTES = 1024          # ssh_enable.py real pesa ~49 KB
    MIN_EXE_BYTES = 1_000_000        # MGU-SSH.exe y mgu-install.exe pesan decenas de MB

    @staticmethod
    def healthy(path: Path, min_size: int) -> bool:
        """Existe y no es un stub: tamano minimo y, para .exe, cabecera MZ. (El 2026-11-08 la demo
        dejo exes de 4 bytes y un script de 8 bytes, y la app los daba por 'listos' porque existian.)"""
        try:
            if not path.is_file() or path.stat().st_size < min_size:
                return False
            if path.suffix.lower() == ".exe":
                with path.open("rb") as f:
                    return f.read(2) == b"MZ"
            return True
        except OSError:
            return False

    def ssh_script_ok(self) -> bool:
        return self.healthy(self.ssh_script, self.MIN_SCRIPT_BYTES)

    def ssh_prebuilt_ok(self) -> bool:
        return self.healthy(self.ssh_prebuilt_exe, self.MIN_EXE_BYTES)

    def mgu_install_ok(self) -> bool:
        return self.healthy(self.mgu_install_exe, self.MIN_EXE_BYTES)

    def status(self) -> ToolsStatus:
        st = self._load()
        s = ToolsStatus()
        e = st.get(SSH_REPO, {})
        s.ssh_source = ToolInfo(_ssh_source_name(), self.ssh_script_ok(), e.get("commit", "")[:10],
                                e.get("date", ""), str(self.repo_dir(SSH_REPO)))
        e = st.get("ssh_prebuilt", {})
        s.ssh_prebuilt = ToolInfo(_ssh_prebuilt_name(), self.ssh_prebuilt_ok(), e.get("tag", ""),
                                  e.get("when", ""), str(self.ssh_prebuilt_exe))
        e = st.get("mgu_install", {})
        s.mgu_install = ToolInfo(_mgu_install_name(), self.mgu_install_ok(),
                                 (e.get("sha", "")[:10] + "…") if e.get("sha") else "", e.get("when", ""),
                                 str(self.mgu_install_exe))
        for name in APP_REPOS:
            e = st.get(name, {})
            s.repos[name] = ToolInfo(name, (self.repo_dir(name) / "mgu-repo.json").exists()
                                     or any(self.repo_dir(name).glob("apps/*/*.json")),
                                     e.get("commit", "")[:10], e.get("date", ""), str(self.repo_dir(name)))
        return s

    def all_ready(self) -> bool:
        return self.status().all_ready

    def commit_of(self, name: str) -> str:
        return str(self._load().get(name, {}).get("commit", ""))

    # -- descargas -----------------------------------------------------------
    def _replace_dir(self, new_dir: Path, final_dir: Path) -> None:
        """Sustituye final_dir por new_dir preservando datos del usuario."""
        kept: list[tuple[Path, Path]] = []
        if final_dir.exists():
            for sub in PRESERVE_SUBDIRS:
                src = final_dir / sub
                if src.exists():
                    tmp = final_dir.parent / f".keep-{final_dir.name}-{sub.replace('/', '_')}"
                    if tmp.exists():
                        shutil.rmtree(tmp, ignore_errors=True)
                    shutil.move(str(src), str(tmp))
                    kept.append((tmp, new_dir / sub))
            shutil.rmtree(final_dir, ignore_errors=True)
        shutil.move(str(new_dir), str(final_dir))
        for tmp, dest in kept:
            dest = final_dir / dest.relative_to(new_dir)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            shutil.move(str(tmp), str(dest))

    def fetch_repo(self, name: str, progress: Optional[ProgressCb] = None, force: bool = False) -> ToolInfo:
        owner, repo = UPSTREAM[name]
        info = ToolInfo(name)
        try:
            sha, date = dl.github_branch_head(owner, repo, "main")
        except dl.DownloadError as e:
            self._log("WARN", tr(f"{name}: no se pudo consultar GitHub ({e}); se usa la copia local si existe.",
                                 f"{name}: could not query GitHub ({e}); the local copy is used if there is one."))
            info.ok = self.repo_dir(name).exists()
            info.version = self.commit_of(name)[:10]
            return info
        st = self._load()
        intact = self.repo_dir(name).exists() and (name != SSH_REPO or self.ssh_script_ok())
        if not force and st.get(name, {}).get("commit") == sha and intact:
            self._log("OK", tr(f"{name}: ya al dia ({sha[:10]}).", f"{name}: already up to date ({sha[:10]})."))
            info.ok, info.version, info.date = True, sha[:10], date
            return info
        zip_path = self.paths.downloads / f"{name}-{sha[:10]}.zip"
        self._log("INFO", tr(f"{name}: descargando {sha[:10]} ({date[:10]})…", f"{name}: downloading {sha[:10]} ({date[:10]})…"))
        dl.download_file(dl.github_zip_url(owner, repo, "main"), zip_path,
                         progress=(lambda g, t: progress(name, g, t)) if progress else None)
        new_dir = self.paths.repos / f".{name}.new"
        if new_dir.exists():
            shutil.rmtree(new_dir, ignore_errors=True)
        dl.safe_extract_zip(zip_path, new_dir, strip_top=True)
        self._replace_dir(new_dir, self.repo_dir(name))
        st[name] = {"commit": sha, "date": date, "when": _dt.datetime.now().isoformat(timespec="seconds")}
        self._save(st)
        self._log("OK", tr(f"{name}: listo en {self.repo_dir(name)} @ {sha[:10]}",
                           f"{name}: ready at {self.repo_dir(name)} @ {sha[:10]}"))
        info.ok, info.version, info.date, info.path = True, sha[:10], date, str(self.repo_dir(name))
        return info

    def fetch_ssh_prebuilt(self, progress: Optional[ProgressCb] = None, force: bool = False) -> ToolInfo:
        info = ToolInfo(_ssh_prebuilt_name())
        if not sys.platform.startswith("win"):
            info.detail = tr("Solo hay prebuilt para Windows; en macOS se usa el codigo con nuestro interprete.",
                             "There is only a prebuilt for Windows; on macOS the source code runs with our interpreter.")
            info.ok = True
            return info
        owner, repo = UPSTREAM[SSH_REPO]
        try:
            asset = dl.github_latest_release_asset(owner, repo, "MGU-SSH-windows")
        except dl.DownloadError as e:
            self._log("WARN", tr(f"GUI oficial: {e}", f"Official GUI: {e}"))
            info.ok = self.ssh_prebuilt_exe.exists()
            return info
        st = self._load()
        if not force and st.get("ssh_prebuilt", {}).get("tag") == asset.tag and self.ssh_prebuilt_ok():
            self._log("OK", tr(f"GUI oficial MGU-SSH {asset.tag}: ya instalada.",
                               f"Official MGU-SSH GUI {asset.tag}: already installed."))
            info.ok, info.version, info.path = True, asset.tag, str(self.ssh_prebuilt_exe)
            return info
        zip_path = self.paths.downloads / f"MGU-SSH-windows-{asset.tag}.zip"
        mb = asset.size // (1024*1024)
        self._log("INFO", tr(f"GUI oficial MGU-SSH {asset.tag}: descargando ({mb} MB)…",
                             f"Official MGU-SSH GUI {asset.tag}: downloading ({mb} MB)…"))
        dl.download_file(asset.url, zip_path,
                         progress=(lambda g, t: progress("MGU-SSH.exe", g, t)) if progress else None)
        new_dir = self.paths.tools / ".MGU-SSH.new"
        if new_dir.exists():
            shutil.rmtree(new_dir, ignore_errors=True)
        dl.safe_extract_zip(zip_path, new_dir, strip_top=True)
        if not (new_dir / "MGU-SSH.exe").exists():
            raise dl.DownloadError(tr("El zip de MGU-SSH no contiene MGU-SSH.exe.",
                                      "The MGU-SSH zip does not contain MGU-SSH.exe."))
        self._replace_dir(new_dir, self.ssh_prebuilt_dir)
        st["ssh_prebuilt"] = {"tag": asset.tag, "when": _dt.datetime.now().isoformat(timespec="seconds")}
        self._save(st)
        self._log("OK", tr(f"GUI oficial lista: {self.ssh_prebuilt_exe} ({asset.tag})",
                           f"Official GUI ready: {self.ssh_prebuilt_exe} ({asset.tag})"))
        info.ok, info.version, info.path = True, asset.tag, str(self.ssh_prebuilt_exe)
        return info

    def fetch_mgu_install(self, progress: Optional[ProgressCb] = None, force: bool = False) -> ToolInfo:
        info = ToolInfo(_mgu_install_name())
        name = mgu_install_asset_name()
        sums = dl.parse_sha256sums(dl.fetch_text(f"{MGU_INSTALL_BASE}/SHA256SUMS"))
        expected = sums.get(name)
        if not expected:
            raise dl.DownloadError(tr(f"SHA256SUMS no lista {name}.", f"SHA256SUMS does not list {name}."))
        st = self._load()
        if not force and st.get("mgu_install", {}).get("sha") == expected and self.mgu_install_ok():
            self._log("OK", tr("mgu-install: ya al dia (SHA256 coincide).", "mgu-install: already up to date (SHA256 matches)."))
            info.ok, info.version, info.path = True, expected[:10], str(self.mgu_install_exe)
            return info
        gz = self.paths.downloads / name
        self._log("INFO", tr(f"mgu-install: descargando {name}…", f"mgu-install: downloading {name}…"))
        dl.download_file(f"{MGU_INSTALL_BASE}/{name}", gz,
                         progress=(lambda g, t: progress("mgu-install", g, t)) if progress else None)
        dl.verify_sha256(gz, expected)
        self._log("OK", tr("mgu-install: SHA256 verificado.", "mgu-install: SHA256 verified."))
        dl.gunzip_to(gz, self.mgu_install_exe)
        if not sys.platform.startswith("win"):
            self.mgu_install_exe.chmod(0o755)
        st["mgu_install"] = {"sha": expected, "name": name, "when": _dt.datetime.now().isoformat(timespec="seconds")}
        self._save(st)
        info.ok, info.version, info.path = True, expected[:10], str(self.mgu_install_exe)
        return info

    # -- fuentes comunitarias (owner/repo arbitrario) ------------------------------
    def source_dir(self, repo_full: str) -> Path:
        return self.paths.repos / repo_full.replace("/", "__")

    def fetch_source(self, repo_full: str, progress: Optional[ProgressCb] = None, force: bool = False) -> ToolInfo:
        """Descarga (zip) una fuente comunitaria `owner/repo` a repos/owner__repo."""
        owner, name = repo_full.split("/", 1)
        info = ToolInfo(repo_full)
        dest = self.source_dir(repo_full)
        try:
            ri = dl.github_repo_info(owner, name)
            sha, date = dl.github_branch_head(owner, name, ri.default_branch)
        except dl.DownloadError as e:
            self._log("WARN", f"{repo_full}: {e}")
            info.ok = dest.exists()
            return info
        st = self._load()
        key = "src:" + repo_full
        if not force and st.get(key, {}).get("commit") == sha and dest.exists():
            info.ok, info.version, info.date, info.path = True, sha[:10], date, str(dest)
            return info
        zip_path = self.paths.downloads / f"{dest.name}-{sha[:10]}.zip"
        self._log("INFO", tr(f"{repo_full}: descargando {sha[:10]} ({ri.default_branch})…",
                             f"{repo_full}: downloading {sha[:10]} ({ri.default_branch})…"))
        dl.download_file(dl.github_zip_url(owner, name, ri.default_branch), zip_path,
                         progress=(lambda g, t: progress(repo_full, g, t)) if progress else None)
        new_dir = self.paths.repos / f".{dest.name}.new"
        if new_dir.exists():
            shutil.rmtree(new_dir, ignore_errors=True)
        dl.safe_extract_zip(zip_path, new_dir, strip_top=True)
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        shutil.move(str(new_dir), str(dest))
        if not self._has_tree_manifests(dest):
            try:
                self.write_release_manifest(owner, name, dest)
            except Exception as e:  # el repo puede no tener releases: no es error
                self._log("WARN", tr(f"{repo_full}: sin manifiestos en el arbol ni release legible ({e}).",
                                     f"{repo_full}: no manifests in the tree and no readable release ({e})."))
        st[key] = {"commit": sha, "date": date, "branch": ri.default_branch, "stars": ri.stars,
                   "when": _dt.datetime.now().isoformat(timespec="seconds")}
        self._save(st)
        self._log("OK", tr(f"{repo_full}: listo @ {sha[:10]}", f"{repo_full}: ready @ {sha[:10]}"))
        info.ok, info.version, info.date, info.path = True, sha[:10], date, str(dest)
        return info

    def source_commit(self, repo_full: str) -> str:
        return str(self._load().get("src:" + repo_full, {}).get("commit", ""))

    # -- layout "Releases": <id>@<version>.tgz + mgu-store.json / catalog.json ----
    @staticmethod
    def _has_tree_manifests(d: Path) -> bool:
        if (d / "mgu-repo.json").exists():
            return True
        if any(d.glob("apps/*/app.json")) or any(d.glob("apps/*/mgu-app.json")):
            return True
        return any(True for _ in d.glob("native/*/component.json")) or any(True for _ in d.glob("tools/*/component.json"))

    def write_release_manifest(self, owner: str, name: str, dest: Path) -> int:
        """Sin manifiestos en el arbol: deriva las apps del ultimo release y
        escribe `_mgua2_release.json` (formato propio) para el catalogo."""
        import re as _re
        rel = dl.github_latest_release(owner, name)
        if rel is None:
            return 0
        versions: dict[str, str] = {}
        meta: dict[str, dict] = {}
        for aname, url in rel.assets:
            m = _re.match(r"^(.+?)@([0-9][^/]*?)\.tgz$", aname)
            if m:
                versions[m.group(1)] = m.group(2)
            if aname in ("mgu-store.json", "catalog.json") and url:
                try:
                    data = dl.fetch_json(url)
                except dl.DownloadError:
                    data = {}
                apps = data.get("apps") if isinstance(data, dict) else data
                if isinstance(apps, dict):
                    for aid, md in apps.items():
                        if isinstance(md, dict):
                            meta[str(aid)] = md
                elif isinstance(apps, list):
                    for md in apps:
                        if isinstance(md, dict) and md.get("id"):
                            meta[str(md["id"])] = md
        ids = sorted(set(versions) | set(meta))
        out = {"tag": rel.tag, "apps": [
            {"id": i, "title": str(meta.get(i, {}).get("title", i)), "description": str(meta.get(i, {}).get("description", "")),
             "version": versions.get(i, str(meta.get(i, {}).get("version", ""))), "author": str(meta.get(i, {}).get("author", ""))}
            for i in ids]}
        (dest / "_mgua2_release.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        self._log("OK", tr(f"{owner}/{name}: layout Releases ({rel.tag}): {len(ids)} app(s) derivadas.",
                           f"{owner}/{name}: Releases layout ({rel.tag}): {len(ids)} app(s) derived."))
        return len(ids)

    def install_all(self, progress: Optional[ProgressCb] = None, force: bool = False,
                    extra_sources: Optional[list[str]] = None) -> ToolsStatus:
        """Descarga/actualiza todo. Cada paso falla de forma aislada y se registra."""
        steps = [
            (_ssh_source_name(), lambda: self.fetch_repo(SSH_REPO, progress, force)),
            (tr("GUI oficial MGU-SSH", "Official MGU-SSH GUI"), lambda: self.fetch_ssh_prebuilt(progress, force)),
            (_mgu_install_name(), lambda: self.fetch_mgu_install(progress, force)),
        ] + [(name, (lambda n=name: self.fetch_repo(n, progress, force))) for name in APP_REPOS]
        steps += [(src, (lambda s=src: self.fetch_source(s, progress, force))) for src in (extra_sources or [])]
        for label, fn in steps:
            try:
                fn()
            except Exception as e:
                self._log("ERROR", f"{label}: {e}")
        return self.status()
