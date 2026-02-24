"""Animated background effects for special themes.

Aurora  — slowly shifting northern‑lights gradient overlay
Galaxy  — twinkling star particles on a deep space backdrop

The widget is transparent for mouse events and sits behind the tab
content in the z‑order.
"""

from __future__ import annotations

import math
import random

from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import (
    QPainter, QColor, QLinearGradient, QPen,
)
from PyQt6.QtWidgets import QWidget


class BackgroundEffect(QWidget):
    """Transparent overlay that paints animated theme backgrounds."""

    def __init__(
        self,
        effect_type: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._effect_type: str | None = None
        self._phase: float = 0.0
        self._stars: list[dict] = []

        self._timer = QTimer(self)
        self._timer.setInterval(33)   # ~30 fps
        self._timer.timeout.connect(self._tick)

        if effect_type:
            self.set_effect(effect_type)

    # ── public API ─────────────────────────────────────────────────────

    def set_effect(self, effect_type: str | None) -> None:
        """Switch effect.  Pass ``None`` to disable."""
        self._effect_type = effect_type
        self._phase = 0.0
        self._stars.clear()

        if effect_type == "galaxy":
            self._init_galaxy()

        if effect_type is not None:
            if not self._timer.isActive():
                self._timer.start()
            self.show()
        else:
            self._timer.stop()
            self.hide()

        self.update()

    # ── init helpers ───────────────────────────────────────────────────

    def _init_galaxy(self) -> None:
        self._stars = [
            {
                "x": random.random(),
                "y": random.random(),
                "size": random.uniform(0.8, 2.5),
                "base_alpha": random.uniform(0.3, 0.9),
                "twinkle_speed": random.uniform(0.02, 0.07),
                "twinkle_offset": random.uniform(0, 2 * math.pi),
                "color": random.choice([
                    "#FFFFFF", "#B4BEFE", "#CBA6F7", "#89B4FA", "#E8E8FF",
                ]),
                "drift_x": random.uniform(-0.00005, 0.00005),
                "drift_y": random.uniform(-0.00003, 0.00003),
            }
            for _ in range(80)
        ]

    # ── tick ───────────────────────────────────────────────────────────

    def _tick(self) -> None:
        self._phase += 0.02
        if self._phase > 200 * math.pi:
            self._phase -= 200 * math.pi

        # Drift stars
        for s in self._stars:
            s["x"] = (s["x"] + s["drift_x"]) % 1.0
            s["y"] = (s["y"] + s["drift_y"]) % 1.0

        self.update()

    # ── painting ───────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # type: ignore[override]
        if self._effect_type is None:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._effect_type == "aurora":
            self._paint_aurora(painter)
        elif self._effect_type == "galaxy":
            self._paint_galaxy(painter)

        painter.end()

    def _paint_aurora(self, painter: QPainter) -> None:
        w, h = self.width(), self.height()
        if w == 0 or h == 0:
            return

        # Gradient that shifts over time
        grad = QLinearGradient(0, 0, w, h)

        phase = self._phase
        # Three colour stops cycling positions
        stops = [
            ((math.sin(phase * 0.3) + 1) / 2,        QColor(102, 255, 204, 25)),   # green
            ((math.sin(phase * 0.3 + 2.1) + 1) / 2,  QColor(153, 102, 255, 25)),   # purple
            ((math.sin(phase * 0.3 + 4.2) + 1) / 2,  QColor(51, 153, 255, 20)),    # blue
        ]
        # Sort by position
        stops.sort(key=lambda s: s[0])

        for pos, color in stops:
            grad.setColorAt(max(0.0, min(1.0, pos)), color)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawRect(QRectF(0, 0, w, h))

    def _paint_galaxy(self, painter: QPainter) -> None:
        w, h = self.width(), self.height()
        if w == 0 or h == 0:
            return

        painter.setPen(Qt.PenStyle.NoPen)
        phase = self._phase

        for s in self._stars:
            twinkle = 0.5 + 0.5 * math.sin(
                phase * s["twinkle_speed"] * 60 + s["twinkle_offset"]
            )
            alpha = int(255 * s["base_alpha"] * twinkle)
            color = QColor(s["color"])
            color.setAlpha(max(0, min(255, alpha)))
            painter.setBrush(color)

            sx = s["x"] * w
            sy = s["y"] * h
            painter.drawEllipse(QPointF(sx, sy), s["size"], s["size"])
