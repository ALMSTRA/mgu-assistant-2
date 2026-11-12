"""Modelos de dominio (ID7).

MGU Assistant 2 esta acotado a iDrive 7 / MGU ID7. Los manifiestos del
catalogo siguen declarando ID7/ID8; la app filtra ID7 y marca lo demas como
no aplicable.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..i18n import tr


class Hmi(str, Enum):
    ID7 = "ID7"
    ID8 = "ID8"

    def __str__(self) -> str:  # pragma: no cover
        return self.value


class RiskLevel(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    GREY = "grey"

    def __str__(self) -> str:  # pragma: no cover
        return self.value


# La herramienta oficial gatea las unidades MGU soportadas por este BTLD.
SUPPORTED_BTLD = "00003F36"
SSH_ARCH = "id7"
HOTSPOT_HOST = "172.16.222.97"   # SSH de la unidad por el hotspot Wi-Fi del coche


@dataclass(frozen=True)
class Vehicle:
    key: str
    display_name: str
    model_code: str
    years: str
    note: str
    preset: bool = False   # el coche del propietario


def id7_vehicles() -> list[Vehicle]:
    """Coches con iDrive 7 (MGU ID7). La compatibilidad real la confirma el
    diagnostico (SVK/BTLD); esta lista solo orienta."""
    lcp = tr("ID7 con Live Cockpit Professional.", "ID7 with Live Cockpit Professional.")
    return [
        Vehicle("x4m_f98", "BMW X4 M (F98)", "F98", "2019-2021",
                tr("Seleccion por defecto. Cualquier BMW con iDrive 7 sigue el mismo flujo: el diagnostico decide.",
                   "Default selection. Any BMW with iDrive 7 follows the same flow: the diagnostic decides."),
                preset=True),
        Vehicle("x3m_f97", "BMW X3 M (F97)", "F97", "2019-2021",
                tr("Mismo MGU ID7 que el X4 M.", "Same MGU ID7 as the X4 M.")),
        Vehicle("g20", tr("BMW Serie 3 (G20/G21)", "BMW 3 Series (G20/G21)"), "G20", "2019-2022", lcp),
        Vehicle("g22", tr("BMW Serie 4 / M4 (G22/G82)", "BMW 4 Series / M4 (G22/G82)"), "G22", "2020-2022",
                tr("ID7 hasta el cambio a ID8/8.5.", "ID7 until the switch to ID8/8.5.")),
        Vehicle("g05", "BMW X5 / X6 / X7 (G05/G06/G07)", "G05", "2019-2022", "ID7."),
        Vehicle("g01", "BMW X3 / X4 (G01/G02)", "G01", "2019-2021", lcp),
        Vehicle("g30", tr("BMW Serie 5 (G30/G31 LCI)", "BMW 5 Series (G30/G31 LCI)"), "G30", "2020-2023", "ID7."),
        Vehicle("g29", "BMW Z4 / Toyota Supra MGU", "G29", "2019-2022", "ID7."),
        Vehicle("f90", "BMW M5 (F90 LCI)", "F90", "2021-2023", "ID7."),
        Vehicle("g14", tr("BMW Serie 8 (G14/G15/G16)", "BMW 8 Series (G14/G15/G16)"), "G14", "2019-2022", "ID7."),
        Vehicle("other_id7", tr("Otro BMW con iDrive 7", "Other BMW with iDrive 7"), "?", "2018-2023",
                tr("Sin promesa: el diagnostico decide.", "No promises: the diagnostic decides.")),
    ]


def default_vehicle() -> Vehicle:
    return id7_vehicles()[0]
