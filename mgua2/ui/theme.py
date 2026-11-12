"""Tema visual profesional (oscuro) y colores."""
from __future__ import annotations

from ..core.models import RiskLevel
from ..i18n import tr

ACCENT = "#2f7cf6"
BG = "#0f1216"
PANEL = "#161a21"
CARD = "#1b2028"
BORDER = "#262c36"
TEXT = "#e8ebef"
MUTED = "#9aa3ad"
OK = "#2fbf71"
WARN = "#f2b134"
ERR = "#ff5c5c"

RISK_COLORS: dict[RiskLevel, tuple[str, str]] = {
    RiskLevel.GREEN: ("#1f7a3d", "#ffffff"),
    RiskLevel.YELLOW: ("#b8860b", "#ffffff"),
    RiskLevel.RED: ("#a11", "#ffffff"),
    RiskLevel.GREY: ("#4a515b", "#dddddd"),
}
RISK_LABEL_ES: dict[RiskLevel, str] = {
    RiskLevel.GREEN: tr("Verde - lectura", "Green - read-only"),
    RiskLevel.YELLOW: tr("Amarillo - modifica / red / pista / parche", "Yellow - modifies / network / track / patch"),
    RiskLevel.RED: tr("Rojo - escribe / controla el vehiculo", "Red - writes to / controls the vehicle"),
    RiskLevel.GREY: tr("Gris - no aplica a ID7", "Grey - does not apply to ID7"),
}
LEVEL_COLORS = {"DEBUG": MUTED, "INFO": TEXT, "WARN": WARN, "ERROR": ERR, "OK": OK, "CMD": ACCENT, "OUT": "#c9d1d9"}

STYLESHEET = f"""
QMainWindow, QWidget {{ background: {BG}; color: {TEXT}; font-size: 13px; }}
QLabel#Title {{ font-size: 22px; font-weight: 700; color: #ffffff; }}
QLabel#Subtitle {{ font-size: 13px; color: {MUTED}; }}
QLabel#Section {{ font-size: 14px; font-weight: 600; color: #ffffff; margin-top: 6px; }}
QLabel#Muted {{ color: {MUTED}; font-size: 12px; }}
QFrame#Card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#Header {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
QListWidget#Nav {{ background: {PANEL}; border: none; border-right: 1px solid {BORDER}; padding: 10px 8px; outline: 0; }}
QListWidget#Nav::item {{ padding: 10px 12px; border-radius: 8px; color: #c4c9d0; margin: 2px 0; }}
QListWidget#Nav::item:selected {{ background: #22304a; color: #ffffff; }}
QListWidget#Nav::item:hover {{ background: #1d2430; }}
QListWidget#Nav::item:disabled {{ color: #566070; }}
QPushButton {{ background: #232a35; color: #ffffff; border: 1px solid #2f3744; padding: 8px 14px; border-radius: 8px; }}
QPushButton:hover {{ background: #2b3340; }}
QPushButton:pressed {{ background: #1c222b; }}
QPushButton:disabled {{ background: #181c23; color: #5b6472; border-color: #22272f; }}
QPushButton#Primary {{ background: {ACCENT}; border-color: {ACCENT}; font-weight: 600; }}
QPushButton#Primary:hover {{ background: #4a8df8; }}
QPushButton#Primary:disabled {{ background: #1f3350; border-color: #1f3350; color: #7f93ad; }}
QPushButton#Danger {{ background: #5a1f1f; border-color: #8a2b2b; }}
QPushButton#Flat {{ background: transparent; border: none; color: {ACCENT}; padding: 4px 6px; }}
QPlainTextEdit, QTextEdit {{ background: #0b0e12; color: #d7dde4; border: 1px solid {BORDER}; border-radius: 8px;
    font-family: Consolas, "Cascadia Mono", monospace; font-size: 12px; }}
QLineEdit, QComboBox {{ background: #0b0e12; color: {TEXT}; border: 1px solid #2f3744; border-radius: 8px; padding: 7px; }}
QComboBox QAbstractItemView {{ background: {CARD}; color: {TEXT}; selection-background-color: #22304a; }}
QCheckBox {{ spacing: 8px; }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: 10px; margin-top: 12px; padding: 12px 8px 8px 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {MUTED}; }}
QProgressBar {{ background: #0b0e12; border: 1px solid {BORDER}; border-radius: 6px; text-align: center; height: 16px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 6px; }}
QTableWidget {{ background: #0b0e12; gridline-color: {BORDER}; border: 1px solid {BORDER}; border-radius: 8px; }}
QHeaderView::section {{ background: {PANEL}; color: {MUTED}; padding: 6px; border: none; border-bottom: 1px solid {BORDER}; }}
QTableWidget::item:selected {{ background: #22304a; }}
QDockWidget {{ titlebar-close-icon: none; }}
QDockWidget::title {{ background: {PANEL}; padding: 6px 10px; border-top: 1px solid {BORDER}; }}
QStatusBar {{ background: {PANEL}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QScrollArea {{ border: none; }}
QToolTip {{ background: {CARD}; color: {TEXT}; border: 1px solid {BORDER}; }}
"""
