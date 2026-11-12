"""Lectores de manifiestos del ecosistema MGU.

Cada repositorio publica manifiestos JSON. Estos lectores son tolerantes:
los manifiestos son datos NO confiables, asi que nunca ejecutan nada ni
confian en campos para construir comandos; solo extraen metadatos.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..core.models import Hmi


def _read_json(path: str | Path) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _as_hmi_list(value: Any) -> list[Hmi]:
    out: list[Hmi] = []
    if isinstance(value, str):
        value = [value]
    if isinstance(value, (list, tuple)):
        for v in value:
            s = str(v).strip().upper()
            if s in ("ID7", "ID8"):
                out.append(Hmi(s))
    return out


@dataclass
class AppsSpec:
    path_glob: str = "apps/*"
    manifest_name: str = "app.json"
    default_hmi: list[Hmi] = field(default_factory=list)
    requires: dict[str, str] = field(default_factory=dict)
    network_ids: list[str] = field(default_factory=list)  # build.network
    uninstallable: bool = False


@dataclass
class ToolSpec:
    id: str
    path: str = ""
    title: str = ""
    description: str = ""
    hmi: list[Hmi] = field(default_factory=list)
    requires: dict[str, str] = field(default_factory=dict)
    needs: list[str] = field(default_factory=list)
    optional: bool = False


@dataclass
class ComponentSpec:
    id: str
    kind: str = "component"
    version: str = ""
    path: str = ""
    title: str = ""
    description: str = ""
    hmi: list[Hmi] = field(default_factory=list)
    requires: dict[str, str] = field(default_factory=dict)
    optional: bool = False
    internet: bool = False
    provides: str = ""
    uninstallable: bool = False
    has_activate: bool = False
    has_units: bool = False


@dataclass
class RepoManifest:
    schema: int = 1
    apps: Optional[AppsSpec] = None
    tools: list[ToolSpec] = field(default_factory=list)
    components: list[dict] = field(default_factory=list)  # mgu-store estilo


def parse_repo_manifest(repo_dir: str | Path) -> Optional[RepoManifest]:
    data = _read_json(Path(repo_dir) / "mgu-repo.json")
    if data is None:
        return None
    rm = RepoManifest(schema=int(data.get("schema", 1)))

    apps = data.get("apps")
    if isinstance(apps, dict):
        build = apps.get("build") or {}
        rm.apps = AppsSpec(
            path_glob=str(apps.get("path", "apps/*")),
            manifest_name=str(apps.get("manifest", "app.json")),
            default_hmi=_as_hmi_list(apps.get("mguHmi")),
            requires={str(k): str(v) for k, v in (apps.get("requires") or {}).items()},
            network_ids=[str(x) for x in (build.get("network") or [])],
            uninstallable=bool(apps.get("uninstallable", False)),
        )

    for t in data.get("tools") or []:
        if not isinstance(t, dict):
            continue
        rm.tools.append(ToolSpec(
            id=str(t.get("id", "")),
            path=str(t.get("path", "")),
            title=str(t.get("title", "")),
            description=str(t.get("description", "")),
            hmi=_as_hmi_list(t.get("mguHmi")),
            requires={str(k): str(v) for k, v in (t.get("requires") or {}).items()},
            needs=[str(x) for x in (t.get("needs") or [])],
            optional=bool(t.get("optional", False)),
        ))

    comps = data.get("components")
    if isinstance(comps, list):
        rm.components = [c for c in comps if isinstance(c, dict)]

    return rm


@dataclass
class AppManifest:
    id: str
    title: str = ""
    description: str = ""
    version: str = ""
    hmi: list[Hmi] = field(default_factory=list)
    requires: dict[str, str] = field(default_factory=dict)
    needs: list[str] = field(default_factory=list)
    signals: dict = field(default_factory=dict)
    has_settings: bool = False
    source: str = ""


def parse_app_manifest(path: str | Path, default_hmi: Optional[list[Hmi]] = None) -> Optional[AppManifest]:
    data = _read_json(path)
    if data is None:
        return None
    hmi = _as_hmi_list(data.get("mguHmi") or data.get("hmi"))
    if not hmi and default_hmi:
        hmi = list(default_hmi)
    return AppManifest(
        id=str(data.get("id") or Path(path).parent.name),
        title=str(data.get("title", "")),
        description=str(data.get("description", "")),
        version=str(data.get("version", "")),
        hmi=hmi,
        requires={str(k): str(v) for k, v in (data.get("requires") or {}).items()},
        needs=[str(x) for x in (data.get("needs") or [])],
        signals=data.get("signals") or {},
        has_settings=bool(data.get("settings")),
        source=str(path),
    )


def parse_component_manifest(path: str | Path) -> Optional[ComponentSpec]:
    data = _read_json(path)
    if data is None:
        return None
    return ComponentSpec(
        id=str(data.get("id") or Path(path).parent.name),
        kind=str(data.get("kind", "component")),
        version=str(data.get("version", "")),
        path=str(Path(path).parent),
        title=str(data.get("title", "")),
        description=str(data.get("description", "")),
        hmi=_as_hmi_list(data.get("mguHmi")),
        requires={str(k): str(v) for k, v in (data.get("requires") or {}).items()},
        optional=bool(data.get("optional", False)),
        internet=bool(data.get("internet", False)),
        provides=str(data.get("mguProvides", "")),
        uninstallable=bool(data.get("uninstallable", False)),
        has_activate=bool(data.get("activate")),
        has_units=bool(data.get("units")),
    )


@dataclass
class MguAppManifest:
    id: str
    version: str = ""
    tree: str = ""
    source: str = ""


def parse_mgu_app_manifest(path: str | Path) -> Optional[MguAppManifest]:
    data = _read_json(path)
    if data is None:
        return None
    return MguAppManifest(
        id=str(data.get("id") or Path(path).parent.name),
        version=str(data.get("version", "")),
        tree=str(data.get("tree", "")),
        source=str(path),
    )


@dataclass
class ReleaseManifest:
    requires: dict[str, str] = field(default_factory=dict)
    build: str = ""
    source: str = ""


def parse_release_manifest(path: str | Path) -> Optional[ReleaseManifest]:
    data = _read_json(path)
    if data is None:
        return None
    build = data.get("build", "")
    return ReleaseManifest(
        requires={str(k): str(v) for k, v in (data.get("requires") or {}).items()},
        build=build if isinstance(build, str) else "",
        source=str(path),
    )
