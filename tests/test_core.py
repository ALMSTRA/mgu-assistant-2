from pathlib import Path

from mgua2.core.context import AppContext
from mgua2.core.logbus import LogBus
from mgua2.core.models import SUPPORTED_BTLD, id7_vehicles
from mgua2.core.state import SessionState, StateMachine
from mgua2.services.doctor import hints_for_output
from mgua2.services.sshtool import parse_status
from mgua2.services import upstream_cli


def _ready(sm):
    s = sm.state
    s.tools_ready = s.diagnostic_done = s.gateway_found = s.is_mgu = True
    s.btld = SUPPORTED_BTLD
    s.preflight_done = True
    sm.confirm_backup(True)


def test_gates_in_order():
    sm = StateMachine()
    assert not sm.can_run_diagnostic()
    sm.state.tools_ready = True
    assert sm.can_run_diagnostic()
    assert not sm.can_run_preflight()
    assert not sm.can_enable_ssh()
    _ready(sm)
    assert sm.can_enable_ssh()
    assert not sm.can_install_store()
    sm.state.ssh_verified = True
    sm.state.key_path = "k"
    assert sm.can_install_store()


def test_btld_gate_blocks_flash():
    sm = StateMachine()
    _ready(sm)
    sm.state.btld = "DEADBEEF"
    assert not sm.can_enable_ssh() and "BTLD" in sm.can_enable_ssh().reason


def test_nbt_blocks():
    sm = StateMachine()
    _ready(sm)
    sm.state.is_mgu = False
    assert not sm.can_enable_ssh()


def test_acceptance_requires_preflight_and_accept():
    sm = StateMachine()
    assert not sm.confirm_backup(True) and not sm.state.backup_confirmed      # sin preflight no hay que aceptar
    sm.state.preflight_done = True
    assert not sm.confirm_backup(False) and not sm.state.backup_confirmed
    assert sm.confirm_backup(True) and sm.state.backup_confirmed              # un solo 'Acepto', sin frase


def test_select_vehicle_resets():
    sm = StateMachine()
    _ready(sm)
    sm.select_vehicle(id7_vehicles()[1])
    assert not sm.state.backup_confirmed and not sm.can_enable_ssh()


def test_parse_status_real_tool_format():
    # Formato REAL de idrive7-8-ssh-root (ssh_enable.py / mgu7/diag.py).
    lines = ["[10:00:00] Found 1 ENET gateway. | VIN: WBS12345678901234",
             "[10:00:01] Connecting to ENET gateway 169.254.254.36:6801...",
             "[10:00:02] SVK: BTLD 00003F36_030.016.006 SWFL 00003F37_030.016.002 CAFD 00003F3A_030.016.001",
             "[10:00:02] MGU IP: 169.254.36.47 | netmask: 255.255.0.0",
             "[10:00:03] DTC B7F8E5 (Debugging active / SSH is active!!!): absent",
             "[10:00:04] MGU SSH port 22 is not open (12 ms).",
             "[10:00:04] Status: debug/SSH-open state is OFF"]
    r = parse_status(lines)
    assert r.gateway_found and r.is_mgu and not r.nbt_rejected
    assert r.btld == "00003F36" and r.btld_supported
    assert r.software_version == "030.016.002"       # la de SWFL, no la de BTLD
    assert r.mgu_ip == "169.254.36.47"
    assert r.ssh_port_open is False
    assert r.debug_active is False                   # 'absent' pese a la palabra 'active' en la etiqueta
    assert r.vin_masked.startswith("WBS")


def test_parse_status_btld_unsupported_mgu():
    r = parse_status(["Found 1 ENET gateway. | VIN: not reported",
                      "Refusing to flash: this unit's BTLD is not 00003F36, so it is outside the supported MGU ID7/ID8 debug catalog. (Use --force to override.)"])
    assert r.gateway_found and r.is_mgu and r.btld_unsupported and not r.btld_supported
    sm = StateMachine(); sm.state.tools_ready = True
    sm.state.diagnostic_done = sm.state.gateway_found = sm.state.is_mgu = True
    sm.state.btld = ""  # nunca se parseo un BTLD soportado
    assert not sm.can_enable_ssh()
    h = {f.id for f in hints_for_output(["Refusing to flash: this unit's BTLD is not 00003F36"])}
    assert "BTLD_UNSUPPORTED" in h


def test_parse_status_debug_present_and_port_open():
    r = parse_status(["DTC B7F8E5 (Debugging active / SSH is active!!!): PRESENT", "MGU SSH port 22 is open (9 ms).",
                      "SVK: BTLD 00003F36_030.016.006"])
    assert r.debug_active is True and r.ssh_port_open is True and r.btld_supported


def test_parse_status_demo_lines():
    lines = ["[10:00:00] Gateway 169.254.254.36:6801 found", "SVK: BTLD 00003F36 030.016.006 | SWFL 030.016.002",
             "MGU unit IP: 169.254.36.47", "MGU SSH port 22 is not open", "VIN: WBS12345678901234"]
    r = parse_status(lines)
    assert r.gateway_found and r.is_mgu and r.btld == "00003F36" and r.btld_supported
    assert r.mgu_ip == "169.254.36.47" and r.ssh_port_open is False and r.vin_masked.startswith("WBS")


def test_runner_captures_vin_before_redaction(tmp_path):
    import sys
    from mgua2.core.logbus import LogBus
    from mgua2.services.runner import ProcessRunner
    bus = LogBus(tmp_path)
    r = ProcessRunner(bus).run_blocking([sys.executable, "-c", "print('Found 1 ENET gateway. | VIN: WBS12345678901234')"])
    assert r.vin_masked.startswith("WBS") and r.vin_masked.endswith("34")
    assert "WBS12345678901234" not in bus.export_text() and "WBS12345678901234" not in " ".join(r.lines)


def test_parse_status_nbt_and_no_gateway():
    assert parse_status(["This unit is an NBT/EVO head unit (BTLD 1234); this tool only speaks MGU."]).nbt_rejected
    r = parse_status(["No ENET gateway responded. A direct IP can be entered with --gateway."])
    assert not r.gateway_found and not r.is_mgu


def test_doctor_hints():
    h = hints_for_output(["No ENET gateway responded", "Permission denied (publickey)", "REMOTE HOST IDENTIFICATION HAS CHANGED"])
    ids = {f.id: f for f in h}
    assert ids["ENET_NO_GATEWAY"].fix_id == "RETRY_FIXED_GATEWAY" and ids["ENET_NO_GATEWAY"].auto
    assert ids["KEY_REFUSED"].fix_id == "OPEN_OFFICIAL_GUI"
    assert ids["KNOWN_HOSTS_STALE"].auto


def test_logbus_redacts_and_fans_out(tmp_path):
    bus = LogBus(tmp_path)
    got = []
    bus.subscribe(lambda ts, lv, m: got.append((lv, m)))
    bus.info("vin WBS12345678901234 token ghp_" + "A" * 36)
    assert got and "WBS12345678901234" not in got[0][1] and "ghp_" not in got[0][1]
    assert "[VIN-CENSURADO]" in bus.path.read_text(encoding="utf-8")


def test_upstream_argv_dev_mode():
    argv = upstream_cli.build_argv("C:/x/ssh_enable.py", ["status"])
    assert argv[-2:] == ["C:\\x\\ssh_enable.py", "status"] or argv[-1] == "status"
    assert "--force" not in argv and "--yes" not in argv


def test_demo_context_full_flow():
    ctx = AppContext(demo=True)
    assert ctx.state.tools_ready
    res = ctx.runner.run_blocking(["x", "ssh_enable.py", "status"])
    st = parse_status(res.lines)
    assert st.btld_supported and st.is_mgu
    ctx.runner.run_blocking(["x", "ssh_enable.py", "preflight"])
    assert ctx.sshtool.find_preflight_backups()
    assert ctx.sshtool.launch_official_gui()
    enr = ctx.sshtool.find_enrollments()
    assert enr and enr[0].key_path
    assert len(ctx.build_catalog()) >= 40
    assert all(f.severity == "ok" for f in ctx.doctor.check_environment())
    ctx.close()


def test_store_plan_redacts_and_uses_host(tmp_path):
    ctx = AppContext(demo=True)
    key = tmp_path / "id_rsa"
    key.write_text("x")
    plan = ctx.store.plan_first_install(str(key), host=None)
    assert "--host" in plan.argv and "172.16.222.97" in plan.argv and "--no-restart-prompt" in plan.argv
    assert str(key) not in plan.display and "first-install" in plan.argv
    usb = ctx.store.plan_usb_repo("E:\\", ["github:a/b"])
    assert usb.argv[1:] == ["usb-repo", "E:\\", "github:a/b"]
    ctx.close()


# --- Hallazgos del primer coche real (X4 M F98, 2026-11-08) -----------------------------------

def test_parse_status_cafd_wiped_by_flash_blocks_store():
    # Antes del flash: CAFD real. Despues: CAFD FFFFFFFF (valores por defecto) y SSH persistente.
    pre = parse_status(["[18:54:35] SVK: HWEL 0000786C_001.003.001, BTLD 00003F36_016.012.001, "
                        "SWFL 00005CC5_016.012.001, SWFK 00007CFC_016.012.001, CAFD 00003E52_006.036.022"])
    assert pre.cafd == "00003E52" and not pre.coding_missing and pre.btld_supported
    post = parse_status(["[19:16:55] SVK: BTLD 00003F36_016.012.001, SWFL 000056EA_030.016.002, CAFD FFFFFFFF_255.255.255",
                         "[19:16:56] DTC B7F8E5 (Debugging active / SSH is active!!!): absent",
                         "[19:16:56] MGU SSH port 22 is open (16 ms).",
                         "[19:16:56] Status: debug/SSH-open state is OFF"])
    assert post.coding_missing and post.cafd == "FFFFFFFF" and post.btld_supported
    assert post.ssh_persistent and post.debug_active is False
    sm = StateMachine()
    _ready(sm)
    sm.state.ssh_verified, sm.state.key_path = True, "k"
    assert sm.can_install_store()
    sm.state.coding_missing = True
    d = sm.can_install_store()
    assert not d and "CAFD" in d.reason and "E-Sys" in d.reason


def test_doctor_hints_from_real_car_log():
    from mgua2.services.doctor import finding_by_id
    h = {f.id: f for f in hints_for_output([
        "The head unit's coding is missing: it holds default values. This often happens after enabling SSH or flashing.",
        "ssh: connect to host 169.254.2.80 port 22: Unknown error"])}
    assert h["CODING_DEFAULT"].severity == "error" and "E-Sys" in h["CODING_DEFAULT"].detail
    assert h["CODING_DEFAULT"].fix_id == "OPEN_PREFLIGHT_FOLDER" and not h["CODING_DEFAULT"].auto
    assert "UNIT_UNREACHABLE" in h
    assert finding_by_id("CODING_DEFAULT").title == h["CODING_DEFAULT"].title
    assert finding_by_id("NO_EXISTE") is None


def test_known_hosts_path_quoted_and_stray_file_cleanup(tmp_path):
    # Sin comillas, ssh partia "...\MGU Assistant 2\state\known_hosts" en 3 archivos y escribia la huella
    # en %LOCALAPPDATA%\MGU; el Doctor "limpiaba" un archivo que ssh nunca leia (visto en el coche).
    from mgua2.core.paths import data_paths
    from mgua2.services.runner import ProcessRunner
    from mgua2.services.sshtool import SshTool
    from mgua2.services.tools import ToolsManager
    base = tmp_path / "MGU Assistant 2"
    paths = data_paths(base).ensure()
    bus = LogBus(paths.logs)
    tool = SshTool(ToolsManager(paths, bus), ProcessRunner(bus), paths, bus)
    opt = [a for a in tool.test_ssh_argv("k", "169.254.1.2") if a.startswith("UserKnownHostsFile=")][0]
    assert opt == f'UserKnownHostsFile="{base / "state" / "known_hosts"}"'
    stray = tmp_path / "MGU"   # primer token de la ruta partida por el espacio
    stray.write_text("169.254.1.2 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHk0d2VmZ2hqa2xtbm9wcXJzdHV2d3h5ejAxMjM0NTY3\n",
                     encoding="utf-8")
    kh = tool.known_hosts_file()
    kh.write_text("169.254.1.2 ssh-ed25519 AAAA\n[169.254.1.2]:2222 ssh-rsa BBBB\n10.0.0.1 ssh-rsa CCCC\n", encoding="utf-8")
    assert tool.forget_host_key("169.254.1.2")
    assert not stray.exists()
    assert kh.read_text(encoding="utf-8").strip() == "10.0.0.1 ssh-rsa CCCC"
    assert not tool.forget_host_key("169.254.1.2")   # ya no hay nada: lo dice, no finge
    # Un archivo que NO parece known_hosts nunca se borra.
    stray.write_text("hola\n", encoding="utf-8")
    assert not tool.cleanup_legacy_known_hosts() and stray.exists()
    bus.close()


def test_demo_switch_never_touches_real_data(tmp_path):
    # El boton 'Modo demo' sobrescribio el ssh_enable.py real con '# demo' (2026-11-08).
    import pytest
    from mgua2.core.demo import DemoTools
    from mgua2.core.paths import data_paths
    real = tmp_path / "real"
    ctx = AppContext(data_base=real)
    script = ctx.tools.ssh_script
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("#!/usr/bin/env python3\n" + "x = 1\n" * 100, encoding="utf-8")   # 'herramienta real'
    size = script.stat().st_size
    ctx.switch_to_demo()
    assert ctx.demo and ctx.state.demo and ctx.paths.base != real and ctx.paths.base.name.startswith("mgua2-demo-")
    assert script.stat().st_size == size and script.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3")
    assert ctx.tools.ssh_script.read_text(encoding="utf-8") == "# demo\n" and ctx.tools.ssh_script != script
    assert ctx.sshtool.launch_official_gui()
    assert all(real not in Path(e.folder).parents for e in ctx.sshtool.find_enrollments())
    # Y si alguien apunta la demo a datos reales, falla en vez de destruir.
    with pytest.raises(RuntimeError):
        DemoTools(data_paths(real).ensure(), ctx.bus, real)
    assert script.stat().st_size == size
    ctx.close()


# --- Segunda sesion en el coche (2026-11-09 00:05): sin pasarela, IP vieja, carpeta "backup" -------

def _tool(tmp_path):
    from mgua2.core.paths import data_paths
    from mgua2.services.runner import ProcessRunner
    from mgua2.services.sshtool import SshTool
    from mgua2.services.tools import ToolsManager
    paths = data_paths(tmp_path / "data").ensure()
    bus = LogBus(paths.logs)
    return SshTool(ToolsManager(paths, bus), ProcessRunner(bus), paths, bus), bus


def test_parse_status_gateway_ip_and_timeout_is_not_found():
    ok = parse_status(["[18:54:35] Found 1 ENET gateway. | VIN: not reported",
                       "[18:54:35] Connecting to ENET gateway 169.254.1.21",
                       "[18:54:35] SVK: BTLD 00003F36_016.012.001, SWFL 000056EA_016.012.001, CAFD 00003E52_006.036.022",
                       "[18:54:35] MGU IP: 169.254.2.80 | netmask: 255.255.0.0"])
    assert ok.gateway_found and ok.gateway_ip == "169.254.1.21" and ok.mgu_ip == "169.254.2.80"
    # Reintento con una pasarela equivocada: "Connecting..." + TimeoutError NO es una pasarela encontrada.
    bad = parse_status(["[00:09:32] Connecting to ENET gateway 169.254.254.36",
                        "ERROR del tool upstream: TimeoutError: [WinError 10060] A connection attempt failed"])
    assert not bad.gateway_found and bad.gateway_ip == "" and not bad.is_mgu
    assert "GATEWAY_TIMEOUT" in {f.id for f in hints_for_output(bad.raw)}


def test_enrollments_ignore_non_vin_folders_and_prefer_keys(tmp_path):
    import json
    import os
    import time
    tool, bus = _tool(tmp_path)
    root = tool.tools.ssh_script.parent / "data" / "enrollments"
    good = root / "WBS12345678901234"
    good.mkdir(parents=True)
    (good / "id_rsa").write_text("k", encoding="utf-8")
    (good / "metadata.json").write_text(json.dumps({"mgu_ip": "169.254.2.80"}), encoding="utf-8")
    copy = root / "WBS12345678901234 backup"          # copia del usuario: sin id_rsa y con IP vieja
    copy.mkdir()
    (copy / "metadata.json").write_text(json.dumps({"mgu_ip": "169.254.3.173"}), encoding="utf-8")
    nokey = root / "WBS99999999999999"                # enrollment real pero sin llave
    nokey.mkdir()
    now = time.time()
    os.utime(good, (now - 100, now - 100))
    os.utime(copy, (now, now))
    os.utime(nokey, (now - 10, now - 10))
    enrs = tool.find_enrollments()
    assert [Path(e.folder).name for e in enrs] == ["WBS12345678901234", "WBS99999999999999"]
    assert enrs[0].key_path and enrs[0].mgu_ip == "169.254.2.80"
    text = bus.export_text()
    assert "backup" in text and "WBS12345678901234" not in text    # avisa de la carpeta ignorada, VIN censurado
    bus.close()


def test_last_car_memory_and_retry_gateway(tmp_path):
    from mgua2.services.sshtool import FALLBACK_GATEWAY
    tool, bus = _tool(tmp_path)
    assert tool.retry_gateway("") == FALLBACK_GATEWAY
    tool.remember_car("169.254.1.21", "169.254.2.80")
    tool.remember_car("", "169.254.3.173")
    assert tool.retry_gateway("") == "169.254.1.21" and tool.retry_gateway("169.254.1.1") == "169.254.1.1"
    assert tool.last_car()["mgu_ips"] == ["169.254.3.173", "169.254.2.80"]
    bus.close()


def test_candidate_ips_exclude_self_and_gateway(tmp_path, monkeypatch):
    from mgua2.services import netinfo
    tool, bus = _tool(tmp_path)
    tool.remember_car("169.254.1.21", "169.254.2.80")
    monkeypatch.setattr(netinfo, "own_ipv4", lambda: {"169.254.10.20"})
    monkeypatch.setattr(netinfo, "arp_neighbors",
                        lambda prefix="169.254.", exclude=None: ["169.254.1.21", "169.254.10.20", "169.254.3.173"])
    assert tool.candidate_unit_ips(["169.254.2.80"]) == ["169.254.2.80", "169.254.3.173"]
    bus.close()


def test_netinfo_parse_arp_and_probe_refused():
    import socket
    from mgua2.services import netinfo
    sample = ("\nInterfaz: 169.254.10.20 --- 0x8\n"
              "  Dirección de Internet          Dirección física      Tipo\n"
              "  169.254.1.21         00-1a-2b-3c-4d-5e     dinámico\n"
              "  169.254.2.80        0a-0b-0c-0d-0e-0f     dinámico\n"
              "  169.254.255.255       ff-ff-ff-ff-ff-ff     estático\n"
              "  224.0.0.22            01-00-5e-00-00-16     estático\n"
              "  192.168.1.1           11-22-33-44-55-66     dinámico\n")
    assert netinfo.parse_arp(sample, exclude={"169.254.1.21"}) == ["169.254.2.80"]
    # Puerto abierto real (determinista). El caso 'cerrado' se simula: en Windows un puerto cerrado de
    # loopback puede responder con timeout en vez de RST, asi que no sirve como prueba fiable.
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    try:
        assert netinfo.probe_tcp("127.0.0.1", srv.getsockname()[1], timeout=2) == "open"
    finally:
        srv.close()

    class _Refusing:
        def __init__(self, *a, **k): pass
        def settimeout(self, t): pass
        def connect(self, addr): raise ConnectionRefusedError(10061, "refused")
        def close(self): pass

    class _WinTimeout(_Refusing):
        def connect(self, addr):
            e = OSError(10060, "timed out"); e.winerror = 10060; raise e

    real = netinfo.socket.socket
    try:
        netinfo.socket.socket = _Refusing
        assert netinfo.probe_tcp("169.254.3.173", 22) == "refused"
        netinfo.socket.socket = _WinTimeout
        assert netinfo.probe_tcp("169.254.3.173", 22) == "timeout"
    finally:
        netinfo.socket.socket = real


def test_bridge_reports_upstream_exception_cleanly(tmp_path, capsys):
    import os
    import sys
    script = tmp_path / "boom.py"
    script.write_text("raise TimeoutError('[WinError 10060] simulado')\n", encoding="utf-8")
    cwd, argv = os.getcwd(), list(sys.argv)
    try:
        rc = upstream_cli.run_upstream_entry(str(script), ["status"])
    finally:
        os.chdir(cwd)
        sys.argv = argv
    err = capsys.readouterr().err
    assert rc == 1 and "ERROR del tool upstream: TimeoutError" in err and "Traceback" not in err


# --- Revision independiente 2026-11-09 -----------------------------------------------------------

def test_parse_status_not_reported_debug_state_is_unknown():
    r = parse_status(["MGU SSH port 22 is open (16 ms).", "Status: debug/SSH-open state is OFF (or not reported)"])
    assert r.ssh_port_open is True and r.debug_active is None and not r.ssh_persistent
    r2 = parse_status(["DTC B7F8E5 (Debugging active / SSH is active!!!): absent", "MGU SSH port 22 is open (16 ms).",
                       "Status: debug/SSH-open state is OFF"])
    assert r2.debug_active is False and r2.ssh_persistent


def test_tools_status_rejects_stub_files(tmp_path):
    from mgua2.core.paths import data_paths
    from mgua2.services.tools import ToolsManager
    paths = data_paths(tmp_path / "data").ensure()
    bus = LogBus(paths.logs)
    tm = ToolsManager(paths, bus)
    tm.ssh_script.parent.mkdir(parents=True, exist_ok=True)
    tm.ssh_script.write_text("# demo\n", encoding="utf-8")            # stub que dejo la demo
    tm.ssh_prebuilt_dir.mkdir(parents=True, exist_ok=True)
    tm.ssh_prebuilt_exe.write_bytes(b"demo")
    tm.mgu_install_exe.write_bytes(b"demo")
    st = tm.status()
    assert not st.ssh_source.ok and not st.ssh_prebuilt.ok and not st.mgu_install.ok
    tm.ssh_script.write_text("#!/usr/bin/env python3\n" + "x = 1\n" * 300, encoding="utf-8")
    tm.ssh_prebuilt_exe.write_bytes(b"MZ" + b"\0" * ToolsManager.MIN_EXE_BYTES)
    tm.mgu_install_exe.write_bytes(b"XX" + b"\0" * ToolsManager.MIN_EXE_BYTES)   # grande pero sin cabecera MZ
    st = tm.status()
    assert st.ssh_source.ok and st.ssh_prebuilt.ok and not st.mgu_install.ok
    bus.close()


def test_runner_watchdog_kills_silent_process(tmp_path):
    import sys
    import time
    from mgua2.services.runner import ProcessRunner
    bus = LogBus(tmp_path)
    t0 = time.monotonic()
    r = ProcessRunner(bus).run_blocking([sys.executable, "-c", "import time; time.sleep(20)"], timeout=1)
    assert r.timed_out and not r.ok and time.monotonic() - t0 < 10
    bus.close()


def test_store_plan_rejects_empty_host(tmp_path):
    import pytest
    ctx = AppContext(demo=True)
    key = tmp_path / "id_rsa"
    key.write_text("x")
    with pytest.raises(ValueError):
        ctx.store.plan_first_install(str(key), host="")
    with pytest.raises(ValueError):
        ctx.store.plan_uninstall(str(key), host="   ")
    assert "172.16.222.97" in ctx.store.plan_first_install(str(key), host=None).argv   # None = hotspot, explicito
    ctx.close()


def test_runner_keeps_raw_vin_in_memory_only(tmp_path):
    import sys
    from mgua2.services.runner import ProcessRunner
    bus = LogBus(tmp_path)
    r = ProcessRunner(bus).run_blocking([sys.executable, "-c", "print('Found 1 ENET gateway. | VIN: WBS12345678901234')"])
    assert r.vin == "WBS12345678901234" and "WBS12345678901234" not in repr(r)
    assert "WBS12345678901234" not in bus.export_text()
    s = SessionState()
    s.vin = r.vin
    assert "WBS12345678901234" not in repr(s)
