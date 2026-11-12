"""Puentes entre hilos de trabajo / bus de log y las senales de Qt."""
from __future__ import annotations

import threading
import traceback
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from ..core.logbus import LogBus
from ..services.runner import ProcessHandle, ProcessResult


class LogBridge(QObject):
    """Reenvia las lineas del LogBus (desde cualquier hilo) como senal Qt."""

    line = Signal(str, str, str)  # ts, level, msg

    def __init__(self, bus: LogBus) -> None:
        super().__init__()
        self._bus = bus
        bus.subscribe(self._on_line)

    def _on_line(self, ts: str, level: str, msg: str) -> None:
        self.line.emit(ts, level, msg)


class ProcessController(QObject):
    """Lanza una operacion de servicio (on_output/on_finished) y expone senales."""

    output = Signal(str)
    finished = Signal(object)  # ProcessResult

    def __init__(self) -> None:
        super().__init__()
        self._handle: Optional[ProcessHandle] = None
        self._done = True

    def start(self, service_call: Callable, **kwargs) -> Optional[ProcessHandle]:
        self._done = False

        def fin(result: ProcessResult) -> None:
            # `running` debe ser False ya al procesar `finished`: el hilo del proceso puede seguir
            # vivo un instante mas y los `_reeval` de las paginas dejaban el boton deshabilitado.
            self._done = True
            self.finished.emit(result)

        try:
            self._handle = service_call(on_output=self.output.emit, on_finished=fin, **kwargs)
        except Exception as e:
            self._handle = None
            fin(ProcessResult(returncode=-1, error=str(e)))
        return self._handle

    def cancel(self) -> bool:
        return bool(self._handle and self._handle.cancel())

    @property
    def running(self) -> bool:
        return (not self._done) and bool(self._handle and self._handle.running)


class Worker(QObject):
    """Ejecuta una funcion bloqueante en un hilo y emite su resultado."""

    done = Signal(object)   # resultado
    failed = Signal(str)    # traceback/mensaje

    def run(self, fn: Callable, *args, **kwargs) -> None:
        def target() -> None:
            try:
                self.done.emit(fn(*args, **kwargs))
            except SystemExit:
                self.done.emit(None)
            except Exception:
                self.failed.emit(traceback.format_exc())

        threading.Thread(target=target, daemon=True).start()
