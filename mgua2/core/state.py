"""Maquina de estados de seguridad (flujo ID7).

Orden obligatorio: herramientas listas -> diagnostico de solo lectura que
confirma MGU ID7 y BTLD soportado -> respaldo de codificacion (preflight) y
confirmacion escrita -> habilitar SSH en la GUI oficial -> SSH verificado ->
Store -> apps. Nada de escritura se habilita fuera de orden.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..i18n import tr
from .models import SUPPORTED_BTLD, Vehicle, default_vehicle


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""

    def __bool__(self) -> bool:  # pragma: no cover
        return self.allowed


@dataclass
class SessionState:
    vehicle: Vehicle = field(default_factory=default_vehicle)
    demo: bool = False

    # Entorno / herramientas
    admin: bool = False
    openssh_ok: bool = False
    tools_ready: bool = False        # SSH tool (fuente + prebuilt) y mgu-install descargados

    # Diagnostico (status, solo lectura)
    diagnostic_done: bool = False
    diagnostic_rc: Optional[int] = None
    gateway_found: bool = False
    is_mgu: bool = False              # la herramienta no lo rechazo como NBT/EVO
    btld: str = ""
    software_version: str = ""
    cafd: str = ""                    # CAFD del SVK; "FFFFFFFF" = codificacion borrada por el flash
    coding_missing: bool = False      # la unidad esta con valores por defecto: el Store no se instala
    mgu_ip: str = ""
    mgu_ip_source: str = ""           # de donde salio la IP: diagnostico / enrollment / memoria / sondeo
    gateway_ip: str = ""              # pasarela ENET que respondio (para reintentos)
    ssh_port_open: Optional[bool] = None
    vin_masked: str = ""
    vin: str = field(default="", repr=False)   # VIN real, solo en memoria (para `enable --vin`); nunca al log

    # Respaldo
    preflight_done: bool = False
    preflight_folder: str = ""
    preflight_complete: bool = True   # False si upstream avisa lectura incompleta
    backup_confirmed: bool = False

    # SSH
    ssh_enabled: bool = False
    enrollment_dir: str = ""
    key_path: str = ""
    ssh_verified: bool = False

    # Store
    store_installed: bool = False

    @property
    def id7_confirmed(self) -> bool:
        return self.diagnostic_done and self.gateway_found and self.is_mgu

    @property
    def btld_supported(self) -> bool:
        return bool(self.btld) and self.btld.upper() == SUPPORTED_BTLD


class StateMachine:
    def __init__(self, state: Optional[SessionState] = None) -> None:
        self.state = state or SessionState()

    def select_vehicle(self, v: Vehicle) -> None:
        s = self.state
        s.vehicle = v
        for k in ("diagnostic_done", "gateway_found", "is_mgu", "preflight_done", "coding_missing",
                  "backup_confirmed", "ssh_enabled", "ssh_verified", "store_installed"):
            setattr(s, k, False)
        s.btld = s.software_version = s.cafd = s.mgu_ip = s.mgu_ip_source = s.gateway_ip = s.vin_masked = s.vin = ""
        s.preflight_folder = s.enrollment_dir = s.key_path = ""

    # -- gates --------------------------------------------------------------
    def can_run_diagnostic(self) -> Decision:
        if not self.state.tools_ready:
            return Decision(False, tr("Descargue primero las herramientas (pestana Herramientas).",
                                      "Download the tools first (Tools tab)."))
        return Decision(True)

    def can_run_preflight(self) -> Decision:
        d = self.can_run_diagnostic()
        if not d:
            return d
        if not self.state.id7_confirmed:
            return Decision(False, tr("Ejecute el diagnostico: debe confirmar una unidad MGU.",
                                      "Run the diagnostic: it must confirm an MGU unit."))
        return Decision(True)

    def can_enable_ssh(self) -> Decision:
        s = self.state
        if not s.tools_ready:
            return Decision(False, tr("Herramientas no descargadas.", "Tools not downloaded."))
        if not s.diagnostic_done:
            return Decision(False, tr("Ejecute primero el diagnostico de solo lectura.",
                                      "Run the read-only diagnostic first."))
        if not s.gateway_found:
            return Decision(False, tr("El diagnostico no encontro la unidad por ENET.",
                                      "The diagnostic did not find the unit over ENET."))
        if not s.is_mgu:
            return Decision(False, tr("La unidad no es MGU (NBT/EVO): fuera de alcance.",
                                      "The unit is not an MGU (NBT/EVO): out of scope."))
        if not s.btld_supported:
            return Decision(False, tr(
                f"BTLD {s.btld or 'desconocido'} fuera del catalogo soportado ({SUPPORTED_BTLD}). No se fuerza la proteccion.",
                f"BTLD {s.btld or 'unknown'} is outside the supported catalog ({SUPPORTED_BTLD}). "
                "The safeguard will not be bypassed."))
        if not s.preflight_done:
            return Decision(False, tr("Haga el respaldo de codificacion (preflight) antes de flashear.",
                                      "Back up the coding (preflight) before flashing."))
        if not s.backup_confirmed:
            return Decision(False, tr("Lea y acepte las confirmaciones de seguridad (boton 'Acepto') en Respaldo.",
                                      "Read and accept the safety confirmations ('I accept' button) on the Backup page."))
        return Decision(True)

    def can_install_store(self) -> Decision:
        s = self.state
        if not s.ssh_verified:
            return Decision(False, tr("Verifique primero el acceso SSH (llave + conexion).",
                                      "Verify SSH access first (key + connection)."))
        if not s.key_path:
            return Decision(False, tr("No hay llave SSH seleccionada.", "No SSH key selected."))
        if not s.tools_ready:
            return Decision(False, tr("Herramientas no descargadas.", "Tools not downloaded."))
        if s.coding_missing:
            return Decision(False, tr("La codificacion del HU esta borrada (CAFD FFFFFFFF, tipico tras el flasheo): el "
                                      "instalador oficial se negara. Recodifique HU_MGU por orden de vehiculo (E-Sys), "
                                      "reinicie la unidad y repita el diagnostico para comprobar que el CAFD volvio.",
                                      "The HU coding is wiped (CAFD FFFFFFFF, typical after flashing): the official "
                                      "installer will refuse. Recode HU_MGU from the vehicle order (E-Sys), restart "
                                      "the unit and run the diagnostic again to check that the CAFD is back."))
        return Decision(True)

    def can_prepare_usb(self) -> Decision:
        if not self.state.tools_ready:
            return Decision(False, tr("Herramientas no descargadas (mgu-install).",
                                      "Tools not downloaded (mgu-install)."))
        return Decision(True)

    def confirm_backup(self, accepted: bool) -> Decision:
        """Un solo 'Acepto' (estilo terminos y condiciones) tras leer la lista; exige el preflight hecho.
        (Antes: casillas una por una + frase escrita; cambiado a peticion del usuario el 2026-11-09.)"""
        if not self.state.preflight_done:
            return Decision(False, tr("Haga primero el respaldo de codificacion (preflight).",
                                      "Back up the coding first (preflight)."))
        if not accepted:
            return Decision(False, tr("Debe leer y aceptar las confirmaciones de seguridad.",
                                      "You must read and accept the safety confirmations."))
        self.state.backup_confirmed = True
        return Decision(True)
