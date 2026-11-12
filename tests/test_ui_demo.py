import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from mgua2.core.context import AppContext


@pytest.fixture
def win(qtbot):
    from mgua2.ui.main_window import MainWindow
    ctx = AppContext(demo=True)
    w = MainWindow(ctx)
    qtbot.addWidget(w)
    return w


def test_builds_and_enters_pages(win):
    assert len(win.pages) == 9
    for p in win.pages:
        p.on_enter()


def test_full_demo_flow_through_pages(win, qtbot):
    ctx = win.ctx
    dash, env, tools, enet, backup, ssh, store, apps, logs = win.pages
    enet.on_enter()
    assert not enet.btn_run.isEnabled()          # sin aceptar la lista no se puede diagnosticar
    enet.accept.btn.click()                      # un solo 'Acepto' (estilo terminos y condiciones)
    assert enet.btn_run.isEnabled()
    enet.run(None)
    assert ctx.state.id7_confirmed and ctx.state.btld_supported
    backup.on_enter()
    assert not backup.accept.btn.isEnabled()     # sin preflight no hay nada que aceptar
    backup.run_preflight()
    assert backup.accept.btn.isEnabled()
    backup.accept.btn.click()
    assert ctx.state.backup_confirmed and ctx.sm.can_enable_ssh()
    assert not backup.accept.btn.isEnabled() and backup.accept.accepted
    ssh._open_gui()
    ssh.test()
    assert ctx.state.ssh_verified
    store.on_enter()
    store.install()
    assert ctx.state.store_installed
    assert store.is_unlocked() and apps.is_unlocked()


def test_backup_accept_resyncs_after_vehicle_change(win):
    # Aceptar, cambiar de vehiculo (resetea el estado) y volver: el boton debe poder aceptarse otra vez.
    ctx = win.ctx
    dash, env, tools, enet, backup = win.pages[:5]
    enet.on_enter()
    enet.accept.btn.click()
    enet.run(None)
    backup.on_enter()
    backup.run_preflight()
    backup.accept.btn.click()
    assert ctx.state.backup_confirmed and backup.accept.accepted
    dash.vehicle.setCurrentIndex(1)            # select_vehicle -> backup_confirmed = False
    backup.on_enter()
    assert not ctx.state.backup_confirmed and not backup.accept.accepted
    backup.run_preflight()
    assert backup.accept.btn.isEnabled()
    backup.accept.btn.click()
    assert ctx.state.backup_confirmed


def test_locked_pages_block_navigation(win):
    assert not win.pages[6].is_unlocked()  # Store sin SSH
    win._nav_clicked(6)
    assert win.stack.currentIndex() == 0
