"""Ejecucion de subprocesos: argv (nunca shell), salida en vivo censurada,
cancelacion solo en fases cancelables, timeouts solo donde procede.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

import re

from ..core.logbus import LogBus
from ..i18n import tr
from ..security.redaction import mask_vin, redact, redact_args

OutputCb = Callable[[str], None]
FinishedCb = Callable[["ProcessResult"], None]
# VIN tal como lo imprime el tool ("| VIN: WBS...") — se captura ANTES de censurar.
_VIN_OUT_RE = re.compile(r"\bVIN[:=\s]+([A-HJ-NPR-Z0-9]{17})\b", re.IGNORECASE)


@dataclass
class ProcessResult:
    returncode: int
    cancelled: bool = False
    timed_out: bool = False
    error: Optional[str] = None
    lines: list[str] = field(default_factory=list)
    vin_masked: str = ""   # VIN detectado en la salida, ya enmascarado
    vin: str = field(default="", repr=False)   # VIN real: solo en memoria (p. ej. para `enable --vin`); NUNCA se loguea

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.error and not self.timed_out and not self.cancelled


@dataclass
class ProcessHandle:
    cancelable: bool = True
    _popen: Optional[subprocess.Popen] = None
    _thread: Optional[threading.Thread] = None
    cancelled: bool = False

    def cancel(self) -> bool:
        if not self.cancelable:
            return False
        p = self._popen
        if p and p.poll() is None:
            self.cancelled = True
            try:
                p.terminate()
            except Exception:
                return False
            return True
        return False

    def wait(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())


def _creationflags() -> int:
    if sys.platform.startswith("win"):
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


class ProcessRunner:
    def __init__(self, bus: Optional[LogBus] = None) -> None:
        self.bus = bus

    def _log(self, level: str, msg: str) -> None:
        if self.bus:
            self.bus.log(level, msg)

    def run(self, argv: Sequence[str], *, cwd: str | None = None, env: dict | None = None,
            on_output: OutputCb | None = None, on_finished: FinishedCb | None = None,
            cancelable: bool = True, timeout: float | None = None,
            label: str = "") -> ProcessHandle:
        argv = [str(a) for a in argv]
        handle = ProcessHandle(cancelable=cancelable)
        self._log("CMD", (label + ": " if label else "") + " ".join(redact_args(argv)))

        def target() -> None:
            result = ProcessResult(returncode=-1)
            try:
                popen = subprocess.Popen(
                    argv, cwd=cwd, env=env, shell=False,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    creationflags=_creationflags(),
                )
                handle._popen = popen
                start = time.monotonic()
                watchdog: Optional[threading.Timer] = None
                if timeout is not None and cancelable:
                    # Un proceso colgado SIN imprimir nada no pasaria por el bucle de lineas: el
                    # temporizador lo mata igual (visto como riesgo en la revision del 2026-11-09).
                    def _expire() -> None:
                        if popen.poll() is None:
                            result.timed_out = True
                            try:
                                popen.terminate()
                            except Exception:
                                pass

                    watchdog = threading.Timer(timeout, _expire)
                    watchdog.daemon = True
                    watchdog.start()
                assert popen.stdout is not None
                for raw in popen.stdout:
                    raw = raw.rstrip("\r\n")
                    vm = _VIN_OUT_RE.search(raw)
                    if vm:
                        vin = vm.group(1).upper()
                        result.vin = vin
                        result.vin_masked = mask_vin(vin)
                        if self.bus:
                            self.bus.add_vin(vin)  # censura tambien formas no estandar en todo el log
                    line = redact(raw)
                    result.lines.append(line)
                    self._log("OUT", line)
                    if on_output:
                        on_output(line)
                    if timeout is not None and cancelable and (time.monotonic() - start) > timeout:
                        result.timed_out = True
                        try:
                            popen.terminate()
                        except Exception:
                            pass
                        break
                popen.wait()
                if watchdog is not None:
                    watchdog.cancel()
                result.returncode = popen.returncode
                result.cancelled = handle.cancelled
            except FileNotFoundError as e:
                result.error = tr(f"No se encontro el ejecutable: {e}", f"Executable not found: {e}")
                self._log("ERROR", result.error)
            except Exception as e:  # pragma: no cover
                result.error = str(e)
                self._log("ERROR", result.error)
            finally:
                self._log("OK" if result.ok else "WARN",
                          tr(f"codigo de salida: {result.returncode}", f"exit code: {result.returncode}")
                          + (tr(" (cancelado)", " (cancelled)") if result.cancelled else "")
                          + (" (timeout)" if result.timed_out else ""))
                if on_finished:
                    on_finished(result)

        t = threading.Thread(target=target, name="mgua2-proc", daemon=True)
        handle._thread = t
        t.start()
        return handle

    def run_blocking(self, argv: Sequence[str], *, cwd=None, env=None, timeout=None, label="") -> ProcessResult:
        box: dict[str, ProcessResult] = {}
        done = threading.Event()

        def fin(r: ProcessResult) -> None:
            box["r"] = r
            done.set()

        h = self.run(argv, cwd=cwd, env=env, on_finished=fin, cancelable=True, timeout=timeout, label=label)
        h.wait()
        done.wait(2)
        return box.get("r", ProcessResult(returncode=-1, error=tr("sin resultado", "no result")))
