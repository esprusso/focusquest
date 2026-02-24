"""Celebratory "NEW UNLOCK!" overlay shown when a player earns something.

Uses the same fade‑in/out pattern as :class:`XPToast` but with a larger
card, gold sparkle text, and a click‑to‑dismiss interaction.
"""

from __future__ import annotations

import math
import random

from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QPointF, QRectF,
)
from PyQt6.QtGui import QPainter, QColor, QFont, QPen
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGraphicsOpacityEffect

from ..gamification.unlockables import UnlockableItem, ThemeDef


class UnlockPopup(QWidget):
    """Full‑width overlay celebrating a new unlock."""

    DISPLAY_MS = 3500
    FADE_IN_MS = 400
    FADE_OUT_MS = 600

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(300)
        self.hide()

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
        self.setStyleSheet(
            "UnlockPopup {"
            "  background-color: rgba(20, 20, 40, 230);"
            "  border: 2px solid rgba(255, 215, 0, 150);"
            "  border-radius: 14px;"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._header = QLabel("NEW UNLOCK!", self)
        self._header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._header.setStyleSheet(
            "font-size: 20px; font-weight: 700; color: #FFD700;"
            "background: transparent; border: none;"
            "letter-spacing: 2px;"
        )
        layout.addWidget(self._header)

        self._name_label = QLabel("", self)
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_label.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #CBA6F7;"
            "background: transparent; border: none;"
        )
        layout.addWidget(self._name_label)

        self._desc_label = QLabel("", self)
        self._desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._desc_label.setWordWrap(True)
        self._desc_label.setStyleSheet(
            "font-size: 12px; color: #7A7A9A;"
            "background: transparent; border: none;"
        )
        layout.addWidget(self._desc_label)

        self._dismiss_hint = QLabel("tap anywhere to dismiss", self)
        self._dismiss_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dismiss_hint.setStyleSheet(
            "font-size: 10px; color: #4A4A5E;"
            "background: transparent; border: none;"
            "padding-top: 4px;"
        )
        layout.addWidget(self._dismiss_hint)

    # ── public API ─────────────────────────────────────────────────────

    def show_unlock(self, item: UnlockableItem) -> None:
        """Display the unlock celebration for *item*."""
        self._name_label.setText(item.name)
        self._desc_label.setText(item.preview_description)

        # Colour the name by type
        type_colors = {
            "theme":     "#CBA6F7",
            "companion": "#89B4FA",
            "title":     "#F9E2AF",
        }
        color = type_colors.get(item.unlock_type, "#CBA6F7")
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
        self._particles.clear()
        w, h = self.width(), self.height()
        for _ in range(20):
            self._particles.append({
                "x": random.uniform(10, w - 10),
                "y": random.uniform(10, h - 10),
                "vx": random.uniform(-1.5, 1.5),
                "vy": random.uniform(-2.5, -0.5),
                "life": 1.0,
                "color": QColor(
                    random.choice(["#FFD700", "#FFF176", "#FFAB40", "#FFE082"])
                ),
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
