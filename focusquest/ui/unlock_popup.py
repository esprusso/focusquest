"""Celebratory "NEW UNLOCK!" overlay shown when a player earns something.

Uses the same fade-in/out pattern as :class:`XPToast` but with a larger
card, gold sparkle text, and a click-to-dismiss interaction.
"""

from __future__ import annotations

import random

from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QPointF,
)
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGraphicsOpacityEffect

from ..gamification.unlockables import UnlockableItem


def _hex_to_rgba(hex_color: str, alpha: int) -> str:
    """Convert '#RRGGBB' + 0-255 alpha to 'rgba(R, G, B, A)'."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _lighten(hex_color: str, amount: float = 0.35) -> str:
    """Lighten a hex colour towards white by *amount* (0-1)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r = int(r + (255 - r) * amount)
    g = int(g + (255 - g) * amount)
    b = int(b + (255 - b) * amount)
    return f"#{r:02X}{g:02X}{b:02X}"


class UnlockPopup(QWidget):
    """Full-width overlay celebrating a new unlock."""

    DISPLAY_MS = 3500
    FADE_IN_MS = 400
    FADE_OUT_MS = 600

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(300)
        self.hide()

        self._palette: dict[str, str] = {}

        self._build_ui()

        # Opacity
        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._opacity.setOpacity(0.0)

        self._fade_anim = QPropertyAnimation(self._opacity, b"opacity", self)

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._fade_out)

        # Sparkle particles
        self._particles: list[dict] = []
        self._particle_timer = QTimer(self)
        self._particle_timer.setInterval(33)
        self._particle_timer.timeout.connect(self._tick_particles)

    # ── build ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._header = QLabel("NEW UNLOCK!", self)
        self._header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._header)

        self._name_label = QLabel("", self)
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._name_label)

        self._desc_label = QLabel("", self)
        self._desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._desc_label.setWordWrap(True)
        layout.addWidget(self._desc_label)

        self._dismiss_hint = QLabel("tap anywhere to dismiss", self)
        self._dismiss_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._dismiss_hint)

        # Apply default styles
        self._apply_styles()

    # ── theming ───────────────────────────────────────────────────────

    def _apply_styles(self) -> None:
        """Set widget/label stylesheets from the current palette."""
        bg = self._palette.get("bg_secondary", "#232340")
        warning = self._palette.get("warning", "#F9E2AF")
        accent = self._palette.get("accent", "#CBA6F7")
        text_muted = self._palette.get("text_muted", "#7A7A9A")
        border = self._palette.get("border", "#313154")

        self.setStyleSheet(
            "UnlockPopup {"
            f"  background-color: {_hex_to_rgba(bg, 230)};"
            f"  border: 2px solid {_hex_to_rgba(warning, 150)};"
            "  border-radius: 14px;"
            "}"
        )
        self._header.setStyleSheet(
            f"font-size: 20px; font-weight: 700; color: {warning};"
            "background: transparent; border: none;"
            "letter-spacing: 2px;"
        )
        self._name_label.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {accent};"
            "background: transparent; border: none;"
        )
        self._desc_label.setStyleSheet(
            f"font-size: 12px; color: {text_muted};"
            "background: transparent; border: none;"
        )
        self._dismiss_hint.setStyleSheet(
            f"font-size: 10px; color: {border};"
            "background: transparent; border: none;"
            "padding-top: 4px;"
        )

    def apply_palette(self, palette: dict[str, str]) -> None:
        """Update colours to match the active theme."""
        self._palette = palette
        self._apply_styles()

    # ── public API ─────────────────────────────────────────────────────

    def show_unlock(self, item: UnlockableItem) -> None:
        """Display the unlock celebration for *item*."""
        accent = self._palette.get("accent", "#CBA6F7")
        accent2 = self._palette.get("accent2", "#89B4FA")
        warning = self._palette.get("warning", "#F9E2AF")

        self._name_label.setText(item.name)
        self._desc_label.setText(item.preview_description)

        # Colour the name by type
        type_colors = {
            "theme":     accent,
            "companion": accent2,
            "title":     warning,
        }
        color = type_colors.get(item.unlock_type, accent)
        self._name_label.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {color};"
            "background: transparent; border: none;"
        )

        self.adjustSize()
        self._position()
        self.show()
        self.raise_()

        # Spawn sparkles
        self._spawn_particles()
        if not self._particle_timer.isActive():
            self._particle_timer.start()

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

        self._dismiss_timer.start(self.DISPLAY_MS)

    # ── click to dismiss ───────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self._dismiss_timer.stop()
        self._fade_out()

    # ── particles ──────────────────────────────────────────────────────

    def _spawn_particles(self) -> None:
        warning = self._palette.get("warning", "#F9E2AF")
        # Generate sparkle colours as variations of the palette warning colour
        sparkle_colors = [
            warning,
            _lighten(warning, 0.3),
            _lighten(warning, 0.5),
            _lighten(warning, 0.15),
        ]
        self._particles.clear()
        w, h = self.width(), self.height()
        for _ in range(20):
            self._particles.append({
                "x": random.uniform(10, w - 10),
                "y": random.uniform(10, h - 10),
                "vx": random.uniform(-1.5, 1.5),
                "vy": random.uniform(-2.5, -0.5),
                "life": 1.0,
                "color": QColor(random.choice(sparkle_colors)),
                "size": random.uniform(2, 5),
            })

    def _tick_particles(self) -> None:
        alive: list[dict] = []
        for p in self._particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] += 0.06
            p["life"] -= 0.02
            if p["life"] > 0:
                alive.append(p)
        self._particles = alive
        if not self._particles and not self.isVisible():
            self._particle_timer.stop()
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        if not self._particles:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for p in self._particles:
            c = QColor(p["color"])
            c.setAlpha(int(255 * max(0, p["life"])))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(c)
            s = p["size"] * p["life"]
            painter.drawEllipse(QPointF(p["x"], p["y"]), s, s)
        painter.end()

    # ── fade ───────────────────────────────────────────────────────────

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
        self._fade_anim.finished.connect(self._on_fade_done)
        self._fade_anim.start()

    def _on_fade_done(self) -> None:
        self.hide()
        self._particles.clear()
        self._particle_timer.stop()

    def _position(self) -> None:
        if self.parent():
            pw = self.parent().width()
            ph = self.parent().height()
            x = (pw - self.width()) // 2
            y = (ph - self.height()) // 2 - 40
            self.move(x, max(40, y))
