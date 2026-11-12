"""Entrada del catalogo (ID7)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..core.models import Hmi, RiskLevel
from ..i18n import tr


class Access(str, Enum):
    READ = "read"
    WRITE = "write"
    MIXED = "mixed"

    def __str__(self) -> str:  # pragma: no cover
        return self.value


class Kind(str, Enum):
    APP = "app"
    TOOL = "tool"
    STORE = "store"

    def __str__(self) -> str:  # pragma: no cover
        return self.value


@dataclass
class CatalogItem:
    id: str
    name: str
    version: str
    repo: str
    commit: str = ""
    kind: Kind = Kind.APP
    description: str = ""
    description_es: str = ""          # *_es: nombre historico; guarda el texto en el idioma activo
    hmi: list[Hmi] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    requires_internet: bool = False
    requires_restart: bool = False
    access: Access = Access.READ
    experimental: bool = False
    risk: RiskLevel = RiskLevel.GREEN
    notes_es: list[str] = field(default_factory=list)
    source_manifest: str = ""
    parked_only: bool = False
    track_only: bool = False
    clears_faults: bool = False
    reversible_patch: bool = False
    electric_only: bool = False

    @property
    def id7(self) -> bool:
        return Hmi.ID7 in self.hmi

    def effective_risk(self) -> RiskLevel:
        return self.risk if self.id7 else RiskLevel.GREY

    def compatibility_es(self, electric_vehicle: bool = False) -> str:
        # Nombre historico: devuelve el texto en el idioma activo.
        if not self.id7:
            return tr("No aplica a iDrive 7 (declara solo ID8).", "Not applicable to iDrive 7 (declares ID8 only).")
        if self.electric_only and not electric_vehicle:
            return tr("Compatible, pero no aplica a un coche de combustion.",
                      "Compatible, but not applicable to a combustion car.")
        if self.experimental:
            return tr("Compatible en ID7, marcado experimental / no probado en coche.",
                      "Compatible with ID7, marked experimental / not tested in a car.")
        return tr("Instalable en iDrive 7.", "Installable on iDrive 7.")
