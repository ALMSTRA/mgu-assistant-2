"""Clasificacion de riesgo, acceso y compatibilidad del catalogo.

Combina:
- heuristicas sobre id/titulo/descripcion/senales (para descubrir apps
  nuevas sin depender de una lista fija);
- una tabla de casos conocidos (OVERRIDES) usada como fixtures, que aporta
  descripciones en espanol y las advertencias especificas del proyecto.

Los OVERRIDES solo ajustan lo que declaran; el resto se infiere.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..core.models import RiskLevel
from ..i18n import tr
from .model import Access, CatalogItem, Kind

# --- Palabras clave ---------------------------------------------------------
_KW_CONTROL = (
    "exhaust", "flap", "escape", " map", "maps", "mapa", "cooling", "refriger",
    "xdrive", "transmission", "gearbox", " zf", "clutch", "shift map",
    "engine config", "live adjust", "adjustment", "tune", "dme", "reset",
    "resetea", "coding", "cafd",
)
_KW_FAULT = ("fault", "dtc", "falla", "fault code", "fault memory", "fault scanner")
_KW_CLEAR = ("clear", "borra", "borrar", "clears")
_KW_TRACK = ("dyno", "drag", "brake test", "g-force", "gforce", "g force",
             "launch", "quarter mile", "1/4 mile", "0-100", "100-200")
_KW_GAME = ("doom", "freedoom", " game", "juego")
_KW_PATCH = ("patch", "carplay", "waze")
_KW_NET = ("internet", "tailnet", "tailscale", "uplink", "online", "qr code",
           "network", "remote access")
_KW_RESTART = ("restart", "reboot", "reiniciar", "next start", "next head-unit",
               "al reiniciar", "takes effect")
_KW_ELECTRIC = ("edrive", "electric vehicle", "hv battery", "state of charge")


def _category_text(item: CatalogItem) -> str:
    """Texto para decidir CATEGORIA: solo id + nombre.

    La descripcion se excluye a proposito: muchos manifiestos mencionan otras
    apps ('... beside Doom', '... drags become touches', '... fault memory')
    y eso provocaba falsos positivos de categoria.
    """
    return f"{item.id} {item.name}".lower()


def _full_text(item: CatalogItem) -> str:
    """Texto para rasgos transversales (internet/reinicio/electrico)."""
    return f"{item.id} {item.name} {item.description}".lower()


def _any(text: str, kws) -> bool:
    return any(k in text for k in kws)


@dataclass
class Override:
    description_es: str = ""
    risk: Optional[RiskLevel] = None
    access: Optional[Access] = None
    notes_es: list[str] = field(default_factory=list)
    parked_only: Optional[bool] = None
    track_only: Optional[bool] = None
    clears_faults: Optional[bool] = None
    reversible_patch: Optional[bool] = None
    electric_only: Optional[bool] = None
    experimental: Optional[bool] = None
    requires_restart: Optional[bool] = None
    requires_internet: Optional[bool] = None


_TRACK_NOTE = tr("Solo pista cerrada y condiciones controladas.",
                 "Closed track and controlled conditions only.")

# Casos conocidos (fixtures). No se asume que permanezcan iguales: si un
# manifiesto cambia, las heuristicas siguen aplicando a lo no cubierto aqui.
# Los campos *_es conservan el nombre historico pero guardan el idioma activo
# (se evalua al importar: el idioma ya esta fijado antes de cargar la UI).
OVERRIDES: dict[str, Override] = {
    # --- idrive7-apps (ID7) ---
    "warmup": Override(
        description_es=tr(
            "Calculadora de calentamiento de aceite y refrigerante "
            "(tiempo hasta temperatura), limite de revoluciones seguro en frio y "
            "enfriamiento del turbo. Solo lectura.",
            "Oil and coolant warm-up calculator (time to temperature), safe "
            "cold rev limit and turbo cool-down. Read-only."),
        risk=RiskLevel.GREEN, access=Access.READ,
    ),
    "live_data": Override(
        description_es=tr(
            "Valores en vivo del coche y sus modulos, computadora de "
            "viaje y pantallas de instrumentos. Solo lectura.",
            "Live values from the car and its modules, trip computer and "
            "gauge screens. Read-only."),
        risk=RiskLevel.GREEN, access=Access.READ,
    ),
    "car_vitals": Override(
        description_es=tr(
            "M Vitals: indicadores en vivo de motor, termica, admision, "
            "combustible, encendido, neumaticos y chasis. Solo lectura.",
            "M Vitals: live engine, thermal, intake, fuel, ignition, tire "
            "and chassis gauges. Read-only."),
        risk=RiskLevel.GREEN, access=Access.READ,
    ),
    "redline": Override(
        description_es=tr(
            "Tacometro a pantalla completa con luces de cambio, marcha "
            "y aviso de motor frio. Solo lectura / visualizacion.",
            "Full-screen tachometer with shift lights, gear and cold-engine "
            "warning. Read-only / display."),
        risk=RiskLevel.GREEN, access=Access.READ,
    ),
    "service": Override(
        description_es=tr(
            "Requisitos de servicio desde el cuadro de instrumentos "
            "(aceite, frenos, liquido de frenos, inspeccion).",
            "Service requirements from the instrument cluster (oil, brakes, "
            "brake fluid, inspection)."),
        risk=RiskLevel.YELLOW, access=Access.MIXED,
        notes_es=[tr("Verifique si la version vigente permite ademas resetear "
                     "intervalos de servicio (accion de escritura).",
                     "Check whether the current version can also reset service "
                     "intervals (a write action).")],
    ),
    "gforce": Override(
        description_es=tr(
            "Circulo de friccion con envolvente de agarre y picos de g "
            "por direccion. Lee sensores; su uso incita conduccion deportiva.",
            "Friction circle with grip envelope and peak g per direction. "
            "Reads sensors; using it encourages spirited driving."),
        risk=RiskLevel.YELLOW, access=Access.READ, track_only=True,
        notes_es=[_TRACK_NOTE],
    ),
    "dyno": Override(
        description_es=tr(
            "Virtual Dyno: curvas de potencia y par de una aceleracion "
            "a fondo, guardadas y comparadas.",
            "Virtual Dyno: power and torque curves from a full-throttle pull, "
            "saved and compared."),
        risk=RiskLevel.YELLOW, access=Access.READ, track_only=True,
        notes_es=[_TRACK_NOTE],
    ),
    "draggy": Override(
        description_es=tr(
            "Drag Timer: 0-100, 100-200 y 1/4 de milla con mejores "
            "tiempos.",
            "Drag Timer: 0-100, 100-200 and 1/4 mile with best times."),
        risk=RiskLevel.YELLOW, access=Access.READ, track_only=True,
        notes_es=[_TRACK_NOTE],
    ),
    "brake_test": Override(
        description_es=tr(
            "Brake Test: distancias de frenado 100-0 y 200-0, pico de "
            "desaceleracion y seguimiento de fatiga de frenos.",
            "Brake Test: 100-0 and 200-0 braking distances, peak "
            "deceleration and brake fade tracking."),
        risk=RiskLevel.YELLOW, access=Access.READ, track_only=True,
        notes_es=[_TRACK_NOTE],
    ),
    "doom": Override(
        description_es=tr("Doom (Freedoom: Phase 1) en la pantalla iDrive.",
                          "Doom (Freedoom: Phase 1) on the iDrive screen."),
        risk=RiskLevel.YELLOW, access=Access.READ, parked_only=True,
        notes_es=[tr("Solo estacionado.", "Parked only.")],
    ),
    "edrive": Override(
        description_es=tr(
            "eDrive: autonomia real, potencia de bateria en vivo y "
            "salud (SOH) de la bateria de alta tension.",
            "eDrive: real range, live battery power and health (SOH) of the "
            "high-voltage battery."),
        risk=RiskLevel.GREEN, access=Access.READ, electric_only=True,
        notes_es=[tr("Solo tiene sentido en electricos/hibridos; no aplica a un coche de combustion.",
                     "Only makes sense on electric/hybrid cars; not applicable to a combustion car.")],
    ),
    "live_adjustments": Override(
        description_es=tr(
            "Engine Config: controla la valvula de escape (OEM/OPEN/"
            "CLOSE) y ajustes de motor por el enlace de diagnostico. Escribe en el "
            "vehiculo.",
            "Engine Config: controls the exhaust valve (OEM/OPEN/CLOSE) and "
            "engine settings over the diagnostic link. Writes to the vehicle."),
        risk=RiskLevel.RED, access=Access.WRITE,
        notes_es=[tr("Accion de control del vehiculo; usar con conocimiento pleno.",
                     "Vehicle control action; use only if you fully understand it.")],
    ),
    "zf8hp": Override(
        description_es=tr(
            "Transmission Config (experimental): monitor de la ZF 8HP, "
            "adaptaciones de llenado de embrague y mapas de cambio.",
            "Transmission Config (experimental): ZF 8HP monitor, clutch fill "
            "adaptations and shift maps."),
        risk=RiskLevel.RED, access=Access.WRITE, experimental=True,
        notes_es=[tr("Experimental; afecta la transmision.", "Experimental; affects the transmission.")],
    ),
    "dtc_scanner": Override(
        description_es=tr(
            "Fault Scanner: lee la memoria de fallas de cada modulo y "
            "mensajes Check Control; puede BORRAR fallas.",
            "Fault Scanner: reads the fault memory of every module and "
            "Check Control messages; it can CLEAR faults."),
        risk=RiskLevel.RED, access=Access.MIXED, clears_faults=True,
        notes_es=[tr("Diferencie leer (seguro) de borrar fallas (accion de "
                     "escritura que puede ocultar problemas reales).",
                     "Tell reading (safe) apart from clearing faults (a write "
                     "action that can hide real problems).")],
    ),
    # --- idrive-apps ---
    "robertn_waze_cluster": Override(
        description_es=tr(
            "Waze on cluster: muestra el mapa de CarPlay (Waze/Apple/"
            "Google) en el cuadro mediante un parche reversible de CarPlay.",
            "Waze on cluster: shows the CarPlay map (Waze/Apple/Google) on "
            "the instrument cluster through a reversible CarPlay patch."),
        risk=RiskLevel.YELLOW, access=Access.WRITE, reversible_patch=True,
        requires_restart=True,
        notes_es=[tr("Aplica un parche reversible a CarPlay; instalar despues de "
                     "validar estabilidad basica.",
                     "Applies a reversible patch to CarPlay; install it after "
                     "confirming basic stability.")],
    ),
    "cluster-render": Override(
        description_es=tr(
            "Cluster renderer: dibuja las capas de las apps en el cuadro "
            "y el HUD. Componente de infraestructura.",
            "Cluster renderer: draws the app layers on the instrument "
            "cluster and the HUD. Infrastructure component."),
        risk=RiskLevel.YELLOW, access=Access.WRITE,
    ),
    # --- mgu-store (base) ---
    "robertn_store": Override(
        description_es=tr(
            "MGU Store: tienda e infraestructura base para instalar, "
            "actualizar y revertir apps y herramientas en la unidad.",
            "MGU Store: store and base infrastructure to install, update "
            "and roll back apps and tools on the unit."),
        risk=RiskLevel.YELLOW, access=Access.WRITE,
    ),
    "mgu-deploy": Override(
        description_es=tr(
            "Deploy: instala, actualiza, revierte y elimina apps y "
            "herramientas, con una instantanea antes de cada cambio.",
            "Deploy: installs, updates, rolls back and removes apps and "
            "tools, with a snapshot before every change."),
        risk=RiskLevel.YELLOW, access=Access.WRITE,
    ),
    "mgu-updater": Override(
        description_es=tr(
            "Updater: descarga e instala lo que la tienda solicita "
            "desde sus fuentes. Requiere internet.",
            "Updater: downloads and installs what the store requests from "
            "its sources. Requires internet."),
        risk=RiskLevel.YELLOW, access=Access.WRITE, requires_internet=True,
    ),
    "mgu-python": Override(
        description_es=tr(
            "Python 3.12 en la unidad para apps que compilan con "
            "Python.",
            "Python 3.12 on the unit for apps built with Python."),
        risk=RiskLevel.YELLOW, access=Access.WRITE,
    ),
    "mgu-render": Override(
        description_es=tr("Renderer: dibuja las pantallas de las apps por GPU.",
                          "Renderer: draws the app screens on the GPU."),
        risk=RiskLevel.YELLOW, access=Access.WRITE,
    ),
    "mgu-uplink": Override(
        description_es=tr(
            "Internet uplink: da internet a apps seleccionadas por un "
            "adaptador USB, LTE, telefono o Wi-Fi.",
            "Internet uplink: gives selected apps internet through a USB "
            "adapter, LTE, a phone or Wi-Fi."),
        risk=RiskLevel.YELLOW, access=Access.WRITE, requires_internet=True,
    ),
    "app-privacy": Override(
        description_es=tr(
            "App privacy: mantiene las apps fuera del reporte de apps "
            "de la unidad y las reinicia tras un fallo.",
            "App privacy: keeps the apps out of the unit's app report and "
            "restarts them after a crash."),
        risk=RiskLevel.YELLOW, access=Access.WRITE,
    ),
    # --- car-apps (ID7/ID8, no probadas en coche en ID7) ---
    "iteriodev_cardash": Override(
        description_es=tr(
            "Car Data: datos de motor en vivo (rpm, boost, potencia y "
            "par, aceite, refrigerante) en la pantalla. Solo lectura.",
            "Car Data: live engine data (rpm, boost, power and torque, oil, "
            "coolant) on screen. Read-only."),
        risk=RiskLevel.GREEN, access=Access.READ,
    ),
    "iteriodev_draggy": Override(
        description_es=tr(
            "Drag Timer: cronometra la aceleracion con parciales y "
            "grafica velocidad-tiempo.",
            "Drag Timer: times acceleration with splits and a speed-time "
            "graph."),
        risk=RiskLevel.YELLOW, access=Access.READ, track_only=True,
        notes_es=[_TRACK_NOTE],
    ),
    "iteriodev_dtcscan": Override(
        description_es=tr(
            "Fault Codes: lee la memoria de fallas de cada modulo y la "
            "borra cuando se lo indica.",
            "Fault Codes: reads the fault memory of every module and clears "
            "it when told to."),
        risk=RiskLevel.RED, access=Access.MIXED, clears_faults=True,
        notes_es=[tr("Diferencie leer de borrar fallas.", "Tell reading apart from clearing faults.")],
    ),
    "iteriodev_liveadjust": Override(
        description_es=tr(
            "Live Adjustments para DME con MHD: cambia mapas 1-4, Max "
            "Cooling y la valvula de escape. Escribe en el vehiculo.",
            "Live Adjustments for a DME with MHD: switches maps 1-4, Max "
            "Cooling and the exhaust valve. Writes to the vehicle."),
        risk=RiskLevel.RED, access=Access.WRITE,
        notes_es=[tr("Max Cooling y valvula de escape aun no probados en coche "
                     "segun upstream.",
                     "Max Cooling and the exhaust valve are not tested in a car "
                     "yet, according to upstream.")],
    ),
    "iteriodev_tailscale": Override(
        description_es=tr(
            "Tailscale: acceso remoto a la unidad por tu tailnet a "
            "traves del uplink de internet.",
            "Tailscale: remote access to the unit over your tailnet through "
            "the internet uplink."),
        risk=RiskLevel.YELLOW, access=Access.WRITE, requires_internet=True,
    ),
    # --- herramientas car-apps ---
    "iteriodev-screencast": Override(
        description_es=tr(
            "Screen share: ve la pantalla central en un navegador por "
            "tu tailnet; clics y arrastres se vuelven toques.",
            "Screen share: view the central display in a browser over your "
            "tailnet; clicks and drags become touches."),
        risk=RiskLevel.YELLOW, access=Access.WRITE, requires_internet=True,
    ),
    "iteriodev-tailscale": Override(
        description_es=tr(
            "Tailscale (herramienta): red privada para acceso remoto a "
            "la unidad.",
            "Tailscale (tool): private network for remote access to the "
            "unit."),
        risk=RiskLevel.YELLOW, access=Access.WRITE, requires_internet=True,
    ),
    # --- herramientas idrive7-apps / render ---
    "idrive7-renderd": Override(
        description_es=tr("GPU renderer de las apps iDrive 7: las dibuja a 60 fps.",
                          "GPU renderer for the iDrive 7 apps: draws them at 60 fps."),
        risk=RiskLevel.YELLOW, access=Access.WRITE,
    ),
    "mgu-inputgate": Override(
        description_es=tr(
            "Controller gate: da el controlador iDrive a las apps "
            "(pestanas, botones, ajustes).",
            "Controller gate: hands the iDrive controller to the apps "
            "(tabs, buttons, settings)."),
        risk=RiskLevel.YELLOW, access=Access.WRITE,
    ),
    "waze-on-cluster": Override(
        description_es=tr(
            "Waze on cluster (componente nativo): parche reversible de "
            "CarPlay + captura del mapa para el cuadro.",
            "Waze on cluster (native component): reversible CarPlay patch "
            "+ map capture for the instrument cluster."),
        risk=RiskLevel.YELLOW, access=Access.WRITE, reversible_patch=True,
        requires_restart=True,
    ),
}


def classify(item: CatalogItem, *, network: bool = False,
             has_units: bool = False, has_activate: bool = False,
             car_apps_untested: bool = False) -> CatalogItem:
    """Rellena riesgo, acceso, banderas y descripcion en espanol de `item`."""
    cat_text = _category_text(item)
    full_text = _full_text(item)

    # --- Heuristicas base (categoria: solo id + nombre) ---
    is_fault = _any(cat_text, _KW_FAULT)
    is_control = _any(cat_text, _KW_CONTROL)
    is_track = _any(cat_text, _KW_TRACK)
    is_game = _any(cat_text, _KW_GAME)
    is_patch = _any(cat_text, _KW_PATCH)

    # Riesgo
    risk = RiskLevel.GREEN
    access = Access.READ
    if is_fault:
        risk = RiskLevel.RED
        access = Access.MIXED
        item.clears_faults = True
    elif is_control:
        risk = RiskLevel.RED
        access = Access.WRITE
    elif is_patch:
        risk = RiskLevel.YELLOW
        access = Access.WRITE
        item.reversible_patch = True
    elif is_track:
        risk = RiskLevel.YELLOW
        access = Access.READ
        item.track_only = True
    elif is_game:
        risk = RiskLevel.YELLOW
        access = Access.READ
        item.parked_only = True
    elif item.kind in (Kind.TOOL, Kind.STORE):
        risk = RiskLevel.YELLOW
        access = Access.WRITE

    item.risk = risk
    item.access = access

    # Internet
    if network or item.requires_internet or _any(full_text, _KW_NET):
        item.requires_internet = True

    # Reinicio
    if _any(full_text, _KW_RESTART) or item.reversible_patch or \
            (item.kind in (Kind.TOOL, Kind.STORE) and has_units) or has_activate:
        item.requires_restart = True

    # Electrico
    if item.id == "edrive" or _any(cat_text, _KW_ELECTRIC):
        item.electric_only = True

    # Experimental
    if car_apps_untested or _any(full_text, ("experimental", "not tested", "untested", "emulator")):
        item.experimental = True
        if car_apps_untested:
            item.notes_es.append(tr(
                "car-apps: no probado en coche en ID7 (solo compila contra el "
                "SDK de ID7). Verifique la advertencia vigente antes de usarlo.",
                "car-apps: not tested in a car on ID7 (it only compiles against "
                "the ID7 SDK). Check the current warning before using it."
            ))

    # Descripcion en espanol por defecto: original si no hay override.
    if not item.description_es:
        item.description_es = item.description

    # --- Override de casos conocidos ---
    ov = OVERRIDES.get(item.id)
    if ov:
        if ov.description_es:
            item.description_es = ov.description_es
        if ov.risk is not None:
            item.risk = ov.risk
        if ov.access is not None:
            item.access = ov.access
        for flag in ("parked_only", "track_only", "clears_faults",
                     "reversible_patch", "electric_only", "experimental",
                     "requires_restart", "requires_internet"):
            val = getattr(ov, flag)
            if val is not None:
                setattr(item, flag, val)
        for n in ov.notes_es:
            if n not in item.notes_es:
                item.notes_es.append(n)

    return item
