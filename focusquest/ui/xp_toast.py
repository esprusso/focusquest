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
        self.setStyleSheet(
            "XPToast {"
            "  background-color: rgba(30, 30, 50, 200);"
            "  border: 1px solid rgba(166, 227, 161, 80);"
            "  border-radius: 12px;"
            "}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._amount_label = QLabel("+100 XP", self)
        self._amount_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._amount_label.setStyleSheet(
            "font-size: 24px; font-weight: 700; color: #A6E3A1;"
            "background: transparent; border: none;"
        )
        layout.addWidget(self._amount_label)

        self._bonus_label = QLabel("", self)
        self._bonus_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bonus_label.setWordWrap(True)
        self._bonus_label.setStyleSheet(
            "font-size: 11px; color: #7A7A9A;"
            "background: transparent; border: none;"
        )
        layout.addWidget(self._bonus_label)

    # ── public API ───────────────────────────────────────────────────────

    def show_award(self, amount: int, bonuses: list[dict]) -> None:
        """Display the toast with XP amount and bonus breakdown."""
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
        self._amount_label.setText(f"LEVEL {new_level}!")
        self._amount_label.setStyleSheet(
            "font-size: 26px; font-weight: 700; color: #CBA6F7;"
            "background: transparent; border: none;"
        )
        self._bonus_label.setText(title)
        self._bonus_label.setStyleSheet(
            "font-size: 13px; color: #B4BEFE; font-weight: 600;"
            "background: transparent; border: none;"
        )
        self._bonus_label.show()

        self.setStyleSheet(
            "XPToast {"
            "  background-color: rgba(30, 30, 50, 220);"
            "  border: 1px solid rgba(203, 166, 247, 120);"
            "  border-radius: 12px;"
            "}"
        )

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

    def _reset_styles(self) -> None:
        """Reset to default XP colours after a level-up toast."""
        self._amount_label.setStyleSheet(
            "font-size: 24px; font-weight: 700; color: #A6E3A1;"
            "background: transparent; border: none;"
        )
        self._bonus_label.setStyleSheet(
            "font-size: 11px; color: #7A7A9A;"
            "background: transparent; border: none;"
        )
        self.setStyleSheet(
            "XPToast {"
            "  background-color: rgba(30, 30, 50, 200);"
            "  border: 1px solid rgba(166, 227, 161, 80);"
            "  border-radius: 12px;"
            "}"
        )

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
        self._reset_styles()

    def _position(self) -> None:
        """Centre horizontally near the top of the parent widget."""
        if self.parent():
            pw = self.parent().width()
            x = (pw - self.width()) // 2
            self.move(x, 60)
