"""Bus central de registro ("console log").

Todo lo que ocurre (descargas, comandos, salida de procesos, decisiones) pasa
por aqui. Cada linea se CENSURA antes de llegar a la consola de la UI y al
archivo de log. Python puro: la UI se suscribe con un callback.
"""
from __future__ import annotations

import datetime as _dt
import logging
import threading
from pathlib import Path
from typing import Callable, Optional

from ..security.redaction import redact

Subscriber = Callable[[str, str, str], None]  # (timestamp, level, message)

LEVELS = ("DEBUG", "INFO", "WARN", "ERROR", "OK", "CMD", "OUT")


class LogBus:
    """Fan-out de lineas de log censuradas a la consola y al archivo."""

    def __init__(self, log_dir: Optional[Path] = None, extra_vins: Optional[list[str]] = None) -> None:
        self._subs: list[Subscriber] = []
        self._lock = threading.Lock()
        self._extra_vins = list(extra_vins or [])
        self._fh = None
        self.path: Optional[Path] = None
        if log_dir is not None:
            log_dir.mkdir(parents=True, exist_ok=True)
            stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            self.path = log_dir / f"mgua2-{stamp}.log"
            self._fh = open(self.path, "a", encoding="utf-8")
        self.history: list[tuple[str, str, str]] = []

    # -- suscripcion ------------------------------------------------------
    def subscribe(self, fn: Subscriber) -> None:
        with self._lock:
            self._subs.append(fn)

    def unsubscribe(self, fn: Subscriber) -> None:
        with self._lock:
            if fn in self._subs:
                self._subs.remove(fn)

    def add_vin(self, vin: str) -> None:
        """Registra un VIN de sesion para censurarlo aunque no sea estandar."""
        if vin and vin not in self._extra_vins:
            self._extra_vins.append(vin)

    # -- emision ----------------------------------------------------------
    def log(self, level: str, message: str) -> None:
        level = level.upper()
        if level not in LEVELS:
            level = "INFO"
        msg = redact(str(message), extra_vins=self._extra_vins)
        ts = _dt.datetime.now().strftime("%H:%M:%S")
        with self._lock:
            self.history.append((ts, level, msg))
            if len(self.history) > 20000:
                del self.history[:5000]
            if self._fh:
                try:
                    self._fh.write(f"{ts} [{level}] {msg}\n")
                    self._fh.flush()
                except Exception:
                    pass
            subs = list(self._subs)
        for fn in subs:
            try:
                fn(ts, level, msg)
            except Exception:
                pass

    def info(self, m: str) -> None: self.log("INFO", m)
    def ok(self, m: str) -> None: self.log("OK", m)
    def warn(self, m: str) -> None: self.log("WARN", m)
    def error(self, m: str) -> None: self.log("ERROR", m)
    def cmd(self, m: str) -> None: self.log("CMD", m)
    def out(self, m: str) -> None: self.log("OUT", m)
    def debug(self, m: str) -> None: self.log("DEBUG", m)

    def export_text(self) -> str:
        with self._lock:
            return "\n".join(f"{ts} [{lv}] {m}" for ts, lv, m in self.history)

    def close(self) -> None:
        if self._fh:
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None


class LogBusHandler(logging.Handler):
    """Puente desde el modulo `logging` estandar al bus."""

    def __init__(self, bus: LogBus) -> None:
        super().__init__()
        self.bus = bus

    def emit(self, record: logging.LogRecord) -> None:
        lvl = {"WARNING": "WARN", "CRITICAL": "ERROR"}.get(record.levelname, record.levelname)
        self.bus.log(lvl, self.format(record))
