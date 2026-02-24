"""QSS stylesheets, theming, and state colors for FocusQuest."""

from __future__ import annotations

from ..timer.engine import TimerState

# ── state colors (ring gradient pairs) — GLOBAL DEFAULTS ────────────────
#    Each state maps to (primary, secondary) for the conical gradient.
#    Themes may override individual states via their ``ring_colors`` dict.

STATE_COLORS: dict[TimerState, tuple[str, str]] = {
    TimerState.WORKING:     ("#FF6B6B", "#FFA07A"),   # warm coral
    TimerState.SHORT_BREAK: ("#4ECDC4", "#44B09E"),   # cool teal
    TimerState.LONG_BREAK:  ("#A18CD1", "#7B68EE"),   # calm purple
    TimerState.PAUSED:      ("#6C7086", "#585B70"),   # desaturated gray
    TimerState.IDLE:        ("#4A4A5E", "#3A3A4E"),   # neutral dim
}

# ── default palette (matches Midnight theme) ─────────────────────────────

_DEFAULT_PALETTE: dict[str, str] = {
    "bg":           "#1A1A2E",
    "bg_secondary": "#232340",
    "surface":      "#2A2A4A",
    "accent":       "#CBA6F7",
    "accent2":      "#89B4FA",
    "text":         "#E2E2F0",
    "text_muted":   "#7A7A9A",
    "success":      "#A6E3A1",
    "warning":      "#F9E2AF",
    "danger":       "#F38BA8",
    "border":       "#313154",
}


# ── palette + ring‑colour look‑ups (driven by unlock registry) ──────────


def get_palette(theme_key: str) -> dict[str, str]:
    """Return the colour palette dict for *theme_key*.

    Pulls colours from the ``ThemeDef`` in the unlock registry so that
    ``unlockables.py`` is the single source of truth.  Falls back to the
    default (Midnight) palette for unknown keys.
    """
    from ..gamification.unlockables import get_theme_def, MINIMAL_LIGHT_PALETTE

    theme = get_theme_def(theme_key)
    if theme is None:
        return dict(_DEFAULT_PALETTE)

    # Minimal adapts to macOS light/dark appearance
    if theme_key == "minimal":
        return _resolve_minimal_palette(theme, MINIMAL_LIGHT_PALETTE)

    return dict(theme.palette)


def _resolve_minimal_palette(
    theme: object, light_palette: dict[str, str],
) -> dict[str, str]:
    """Return the light or dark Minimal palette based on macOS appearance."""
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        app = QApplication.instance()
        if app is not None:
            hints = app.styleHints()
            if hints is not None:
                scheme = hints.colorScheme()
                if scheme == Qt.ColorScheme.Light:
                    return dict(light_palette)
    except Exception:
        pass
    # Default to the dark variant (stored in ThemeDef.palette)
    from ..gamification.unlockables import ThemeDef
    return dict(theme.palette) if isinstance(theme, ThemeDef) else dict(_DEFAULT_PALETTE)


def get_ring_colors(theme_key: str) -> dict[TimerState, tuple[str, str]]:
    """Return per‑theme ring gradient colours merged onto STATE_COLORS defaults.

    Any states not overridden by the theme fall back to the global defaults.
    """
    from ..gamification.unlockables import (
        get_theme_def, MINIMAL_LIGHT_RING_COLORS,
    )

    result = dict(STATE_COLORS)

    theme = get_theme_def(theme_key)
    if theme is None:
        return result

    # Minimal in light mode uses its own idle colours
    ring_src = theme.ring_colors
    if theme_key == "minimal":
        try:
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtCore import Qt
            app = QApplication.instance()
            if app and app.styleHints():
                if app.styleHints().colorScheme() == Qt.ColorScheme.Light:
                    ring_src = MINIMAL_LIGHT_RING_COLORS
        except Exception:
            pass

    _STATE_NAME_MAP = {
        "working":     TimerState.WORKING,
        "short_break": TimerState.SHORT_BREAK,
        "long_break":  TimerState.LONG_BREAK,
        "paused":      TimerState.PAUSED,
        "idle":        TimerState.IDLE,
    }

    for state_name, colour_pair in ring_src.items():
        state = _STATE_NAME_MAP.get(state_name)
        if state is not None:
            result[state] = colour_pair

    return result


# ── font resolution ───────────────────────────────────────────────────

_resolved_font: str | None = None


def resolve_font_family() -> str:
    """Detect the best available system font.  Must be called after
    QApplication is created (font database needs the app context)."""
    global _resolved_font
    if _resolved_font is None:
        try:
            from PyQt6.QtGui import QFontDatabase
            families = set(QFontDatabase.families())
            for candidate in ("SF Pro", ".AppleSystemUIFont"):
                if candidate in families:
                    _resolved_font = candidate
                    break
            else:
                _resolved_font = "Helvetica Neue"
        except Exception:
            _resolved_font = "Helvetica Neue"
    return _resolved_font


# ── QSS builder ───────────────────────────────────────────────────────


def build_stylesheet(palette: dict[str, str]) -> str:
    p = palette
    font = resolve_font_family()
    return f"""
    /* ── global ─────────────────────────────────── */
    QWidget {{
        background-color: {p['bg']};
        color: {p['text']};
        font-family: "{font}", "Helvetica Neue", Arial;
        font-size: 14px;
    }}

    QMainWindow {{
        background-color: {p['bg']};
    }}

    /* ── buttons — macOS native feel ─────────────── */
    QPushButton {{
        background-color: {p['bg_secondary']};
        color: {p['text']};
        border: 1px solid {p['border']};
        border-radius: 10px;
        padding: 10px 24px;
        font-size: 14px;
        font-weight: 600;
    }}

    QPushButton:hover {{
        background-color: {p.get('surface', p['bg_secondary'])};
        border-color: {p['accent']};
    }}

    QPushButton:pressed {{
        background-color: {p['accent']};
        color: {p['bg']};
    }}

    QPushButton#primaryButton {{
        background-color: {p['accent']};
        color: {p['bg']};
        border: none;
        font-size: 17px;
        padding: 14px 40px;
        border-radius: 12px;
        font-weight: 700;
    }}

    QPushButton#primaryButton:hover {{
        background-color: {p['accent2']};
    }}

    QPushButton#primaryButton:pressed {{
        background-color: {p['accent']};
    }}

    QPushButton#secondaryButton {{
        background-color: transparent;
        color: {p['text_muted']};
        border: 1px solid {p['border']};
        font-size: 13px;
        padding: 8px 16px;
        border-radius: 8px;
    }}

    QPushButton#secondaryButton:hover {{
        color: {p['text']};
        border-color: {p['text_muted']};
    }}

    QPushButton#dangerButton {{
        background-color: transparent;
        color: {p['danger']};
        border: 1px solid {p['border']};
        font-size: 13px;
        padding: 8px 16px;
        border-radius: 8px;
    }}

    QPushButton#dangerButton:hover {{
        background-color: {p['danger']};
        color: {p['bg']};
        border-color: {p['danger']};
    }}

    QPushButton#microButton {{
        background-color: {p['bg_secondary']};
        color: {p['text_muted']};
        border: 1px solid {p['border']};
        font-size: 13px;
        padding: 8px 20px;
        border-radius: 8px;
    }}

    QPushButton#microButton:hover {{
        color: {p['text']};
        background-color: {p.get('surface', p['bg_secondary'])};
        border-color: {p['text_muted']};
    }}

    QPushButton#extendButton {{
        background-color: transparent;
        color: {p['warning']};
        border: 1px solid {p['warning']};
        font-size: 13px;
        padding: 8px 20px;
        border-radius: 8px;
        font-weight: 600;
    }}

    QPushButton#extendButton:hover {{
        background-color: {p['warning']};
        color: {p['bg']};
    }}

    /* ── line edit ───────────────────────────────── */
    QLineEdit {{
        background-color: {p['bg_secondary']};
        color: {p['text']};
        border: 1px solid {p['border']};
        border-radius: 8px;
        padding: 8px 14px;
        font-size: 13px;
    }}

    QLineEdit:focus {{
        border-color: {p['accent']};
    }}

    /* ── tab widget ──────────────────────────────── */
    QTabWidget::pane {{
        border: none;
        background-color: transparent;
    }}

    QTabBar {{
        background-color: transparent;
    }}

    QTabBar::tab {{
        background-color: transparent;
        color: {p['text_muted']};
        padding: 10px 24px;
        border: none;
        border-bottom: 2px solid transparent;
        font-size: 14px;
        font-weight: 600;
    }}

    QTabBar::tab:selected {{
        color: {p['accent']};
        border-bottom: 2px solid {p['accent']};
    }}

    QTabBar::tab:hover {{
        color: {p['text']};
    }}

    /* ── scroll area ─────────────────────────────── */
    QScrollArea {{
        border: none;
        background-color: transparent;
    }}

    QScrollBar:vertical {{
        background-color: transparent;
        width: 6px;
    }}

    QScrollBar::handle:vertical {{
        background-color: {p['border']};
        border-radius: 3px;
        min-height: 20px;
    }}

    QScrollBar::handle:vertical:hover {{
        background-color: {p['text_muted']};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    /* ── frame / card ────────────────────────────── */
    QFrame#card {{
        background-color: {p['bg_secondary']};
        border: 1px solid {p['border']};
        border-radius: 12px;
    }}

    /* ── progress bar (XP bar, etc.) ─────────────── */
    QProgressBar {{
        background-color: {p['bg_secondary']};
        border: none;
        border-radius: 3px;
        max-height: 6px;
        text-align: center;
    }}

    QProgressBar::chunk {{
        background-color: {p['accent']};
        border-radius: 3px;
    }}

    /* ── labels ──────────────────────────────────── */
    QLabel#levelLabel {{
        font-size: 13px;
        color: {p['accent']};
        font-weight: 700;
    }}

    QLabel#xpLabel {{
        font-size: 12px;
        color: {p['text_muted']};
    }}

    QLabel#streakLabel {{
        font-size: 13px;
        color: {p['warning']};
        font-weight: 700;
    }}

    /* ── status bar ──────────────────────────────── */
    QStatusBar {{
        background-color: {p['bg']};
        color: {p['text_muted']};
        font-size: 12px;
        border-top: 1px solid {p['border']};
    }}
    """
