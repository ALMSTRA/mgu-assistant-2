"""Escaneo de repositorios -> CatalogItem (descubre apps nuevas por manifiestos)."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from ..core.models import Hmi
from ..i18n import tr
from .classifier import classify
from .manifests import parse_app_manifest, parse_component_manifest, parse_mgu_app_manifest, parse_repo_manifest
from .model import CatalogItem, Kind

HMI_DEFAULTS: dict[str, list[Hmi]] = {
    "robertn_store": [Hmi.ID7, Hmi.ID8],
    "robertn_waze_cluster": [Hmi.ID7],
}
_EXCLUDE = frozenset({"node_modules", ".git", "test", "tests", "fixtures"})
APP_REPOS = ("idrive7-apps", "idrive-apps", "car-apps", "mgu-store")


def _excluded(path: Path, repo: Path) -> bool:
    try:
        rel = path.relative_to(repo)
    except ValueError:
        rel = path
    return bool({p.lower() for p in rel.parts} & _EXCLUDE)


def scan_repo(repo_dir: str | Path, repo_name: str, commit: str = "") -> list[CatalogItem]:
    repo = Path(repo_dir)
    if not repo.exists():
        return []
    items: dict[str, CatalogItem] = {}
    untested = repo_name == "car-apps"

    # Layout "Releases" (manifiesto derivado por ToolsManager.write_release_manifest).
    rel = repo / "_mgua2_release.json"
    if rel.exists():
        import json as _json
        try:
            data = _json.loads(rel.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        for a in data.get("apps", []) if isinstance(data, dict) else []:
            aid = str(a.get("id", ""))
            if not aid:
                continue
            it = CatalogItem(id=aid, name=str(a.get("title") or aid), version=str(a.get("version", "")),
                             repo=repo_name, commit=commit, kind=Kind.APP, description=str(a.get("description", "")),
                             hmi=[Hmi.ID7], source_manifest=str(rel))
            classify(it)
            it.experimental = True
            tag = data.get("tag", "")
            it.notes_es.append(tr(f"Publicado por Releases ({tag}): generacion no declarada, asumida ID7; "
                                  "fuente comunitaria no verificada.",
                                  f"Published via Releases ({tag}): generation not declared, assumed ID7; "
                                  "unverified community source."))
            items[aid] = it

    rm = parse_repo_manifest(repo)
    default_hmi = list(rm.apps.default_hmi) if (rm and rm.apps) else []
    network_ids = set(rm.apps.network_ids) if (rm and rm.apps) else set()

    for mf in sorted(repo.glob("apps/*/app.json")):
        if _excluded(mf, repo):
            continue
        am = parse_app_manifest(mf, default_hmi=default_hmi)
        if not am:
            continue
        it = CatalogItem(id=am.id, name=am.title or am.id, version=am.version, repo=repo_name, commit=commit,
                         kind=Kind.APP, description=am.description, hmi=list(am.hmi),
                         dependencies=sorted(set(list(am.requires.keys()) + am.needs)), source_manifest=str(mf))
        classify(it, network=(am.id in network_ids), car_apps_untested=untested)
        items[am.id] = it

    for mf in sorted(repo.glob("apps/*/mgu-app.json")):
        if _excluded(mf, repo):
            continue
        mam = parse_mgu_app_manifest(mf)
        if not mam or mam.id in items:
            continue
        hmi = HMI_DEFAULTS.get(mam.id, list(default_hmi) or [Hmi.ID7, Hmi.ID8])
        it = CatalogItem(id=mam.id, name=mam.id, version=mam.version, repo=repo_name, commit=commit,
                         kind=Kind.STORE if mam.id.endswith("store") else Kind.APP, hmi=list(hmi),
                         source_manifest=str(mf))
        classify(it, car_apps_untested=untested)
        items[mam.id] = it

    for mf in sorted(repo.rglob("component.json")):
        if _excluded(mf, repo):
            continue
        cs = parse_component_manifest(mf)
        if not cs or cs.id in items:
            continue
        hmi = list(cs.hmi) if cs.hmi else [Hmi.ID7, Hmi.ID8]
        it = CatalogItem(id=cs.id, name=cs.title or cs.id, version=cs.version, repo=repo_name, commit=commit,
                         kind=Kind.TOOL, description=cs.description, hmi=hmi,
                         dependencies=sorted(cs.requires.keys()), requires_internet=cs.internet,
                         source_manifest=str(mf))
        classify(it, network=cs.internet, has_units=cs.has_units, has_activate=cs.has_activate,
                 car_apps_untested=untested)
        items[cs.id] = it

    if rm:
        for t in rm.tools:
            if not t.id or t.id in items:
                continue
            it = CatalogItem(id=t.id, name=t.title or t.id, version="", repo=repo_name, commit=commit,
                             kind=Kind.TOOL, description=t.description, hmi=list(t.hmi) or list(default_hmi),
                             dependencies=sorted(set(list(t.requires.keys()) + t.needs)),
                             source_manifest=str(repo / "mgu-repo.json"))
            classify(it, car_apps_untested=untested)
            items[t.id] = it
    return list(items.values())


class CatalogScanner:
    def __init__(self, repos_dir: str | Path, commit_lookup: Optional[Callable[[str], str]] = None) -> None:
        self.repos_dir = Path(repos_dir)
        self.commit_lookup = commit_lookup or (lambda n: "")

    def scan(self, names: Optional[list] = None) -> list[CatalogItem]:
        """`names`: lista de nombres (carpeta == etiqueta) o de tuplas (etiqueta, carpeta)."""
        out: list[CatalogItem] = []
        entries = [(n, n) if isinstance(n, str) else tuple(n) for n in (names or APP_REPOS)]
        for label, folder in entries:
            try:
                commit = (self.commit_lookup(label) or "")[:10]
            except Exception:
                commit = ""
            out.extend(scan_repo(self.repos_dir / folder, label, commit=commit))
        out.sort(key=lambda it: (not it.id7, it.repo, it.name.lower()))
        return out
