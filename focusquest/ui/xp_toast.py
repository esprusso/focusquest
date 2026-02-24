"""Floating "+XP" notification that appears after a session completes.

Usage::

    toast = XPToast(parent_widget)
    toast.show_award(120, [
        {"name": "Session", "amount": 100},
        {"name": "Daily Kickoff", "amount": 50},
    ])
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGraphicsOpacityEffect,
)


def _hex_to_rgba(hex_color: str, alpha: int) -> str:
    """Convert '#RRGGBB' + 0-255 alpha to 'rgba(R, G, B, A)'."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


class XPToast(QWidget):
    """A floating XP notification that fades in, holds, then fades out."""

    DISPLAY_MS = 2800
    FADE_IN_MS = 300
    FADE_OUT_MS = 900

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedWidth(320)
        self.hide()

        # Palette (populated by apply_palette, falls back to Midnight)
        self._palette: dict[str, str] = {}

        self._build_ui()

        # Opacity effect for fade
        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._opacity.setOpacity(0.0)

        self._fade_anim = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._fade_out)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._amount_label = QLabel("+100 XP", self)
        self._amount_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._amount_label)

        self._bonus_label = QLabel("", self)
        self._bonus_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bonus_label.setWordWrap(True)
        layout.addWidget(self._bonus_label)

        # Apply default styles
        self._apply_xp_styles()

    # ── theming ───────────────────────────────────────────────────────────

    def _apply_xp_styles(self) -> None:
        """Apply the normal +XP appearance from the current palette."""
        bg = self._palette.get("bg_secondary", "#232340")
        success = self._palette.get("success", "#A6E3A1")
        text_muted = self._palette.get("text_muted", "#7A7A9A")

        self.setStyleSheet(
            "XPToast {"
            f"  background-color: {_hex_to_rgba(bg, 200)};"
            f"  border: 1px solid {_hex_to_rgba(success, 80)};"
            "  border-radius: 12px;"
            "}"
        )
        self._amount_label.setStyleSheet(
            f"font-size: 24px; font-weight: 700; color: {success};"
            "background: transparent; border: none;"
        )
        self._bonus_label.setStyleSheet(
            f"font-size: 11px; color: {text_muted};"
            "background: transparent; border: none;"
        )

    def _apply_levelup_styles(self) -> None:
        """Apply the LEVEL UP! appearance from the current palette."""
        bg = self._palette.get("bg_secondary", "#232340")
        accent = self._palette.get("accent", "#CBA6F7")
        accent2 = self._palette.get("accent2", "#89B4FA")

        self.setStyleSheet(
            "XPToast {"
            f"  background-color: {_hex_to_rgba(bg, 220)};"
            f"  border: 1px solid {_hex_to_rgba(accent, 120)};"
            "  border-radius: 12px;"
            "}"
        )
        self._amount_label.setStyleSheet(
            f"font-size: 26px; font-weight: 700; color: {accent};"
            "background: transparent; border: none;"
        )
        self._bonus_label.setStyleSheet(
            f"font-size: 13px; color: {accent2}; font-weight: 600;"
            "background: transparent; border: none;"
        )

    def apply_palette(self, palette: dict[str, str]) -> None:
        """Update colours to match the active theme."""
        self._palette = palette
        # Re-apply whichever style variant is currently showing.
        # If the toast is hidden it will be re-styled by show_award/show_level_up
        # anyway, so just apply the default XP styles.
        self._apply_xp_styles()

    # ── public API ───────────────────────────────────────────────────────

    def show_award(self, amount: int, bonuses: list[dict]) -> None:
        """Display the toast with XP amount and bonus breakdown."""
        self._apply_xp_styles()
        self._amount_label.setText(f"+{amount} XP")

        # Build bonus text from breakdown
        if len(bonuses) > 1:
            parts = [f"{b['name']} +{b['amount']}" for b in bonuses]
            self._bonus_label.setText("  \u00b7  ".join(parts))
            self._bonus_label.show()
        else:
            self._bonus_label.hide()

        self.adjustSize()
        self._position()
        self.show()
        self.raise_()

        # Fade in
        self._fade_anim.stop()
        try:
            self._fade_anim.finished.disconnect()
        except TypeError:
            pass
        self._fade_anim.setDuration(self.FADE_IN_MS)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.start()

        # Schedule fade out
        self._dismiss_timer.start(self.DISPLAY_MS)

    def show_level_up(self, new_level: int, title: str) -> None:
        """Show a special level-up toast."""
        self._apply_levelup_styles()
        self._amount_label.setText(f"LEVEL {new_level}!")
        self._bonus_label.setText(title)
        self._bonus_label.show()

        self.adjustSize()
        self._position()
        self.show()
        self.raise_()

        # Fade in
        self._fade_anim.stop()
        try:
            self._fade_anim.finished.disconnect()
        except TypeError:
            pass
        self._fade_anim.setDuration(self.FADE_IN_MS)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.start()

        # Hold longer for level-up
        self._dismiss_timer.start(self.DISPLAY_MS + 1000)

    # ── internal ─────────────────────────────────────────────────────────

    def _fade_out(self) -> None:
        self._fade_anim.stop()
        try:
            self._fade_anim.finished.disconnect()
        except TypeError:
            pass
        self._fade_anim.setDuration(self.FADE_OUT_MS)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade_anim.finished.connect(self._on_fade_out_done)
        self._fade_anim.start()

    def _on_fade_out_done(self) -> None:
        self.hide()
        self._apply_xp_styles()

    def _position(self) -> None:
        """Centre horizontally near the top of the parent widget."""
        if self.parent():
            pw = self.parent().width()
            x = (pw - self.width()) // 2
            self.move(x, 60)
