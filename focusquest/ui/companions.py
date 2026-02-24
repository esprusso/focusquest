"""Animated companion characters drawn with QPainter.

Each companion lives below the progress ring in the Focus tab.
They react to the timer state with distinct animations:

    idle      — gentle ambient movement
    focus     — active, engaged animation
    celebrate — burst of energy on session complete (2s)
    sleep     — calm, drowsy during breaks/paused

No image assets — all procedural via QPainter.
"""

from __future__ import annotations

import math
import random
from typing import ClassVar

from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QBrush, QPainterPath,
    QRadialGradient, QLinearGradient,
)
from PyQt6.QtWidgets import QWidget


# ── base class ──────────────────────────────────────────────────────────


class BaseCompanion(QWidget):
    """Abstract animated companion widget.

    Subclasses override ``_paint_*`` methods for each animation state.
    """

    WIDGET_WIDTH: ClassVar[int] = 120
    WIDGET_HEIGHT: ClassVar[int] = 60

    # Phase increment per tick for each state
    _PHASE_SPEEDS: ClassVar[dict[str, float]] = {
        "idle":      0.04,
        "focus":     0.06,
        "celebrate": 0.10,
        "sleep":     0.02,
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(self.WIDGET_WIDTH, self.WIDGET_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._state: str = "idle"
        self._prev_state: str = "idle"
        self._phase: float = 0.0
        self._session_progress: float = 0.0    # 0..1

        # Celebrate particles (subclasses populate via _spawn_particles)
        self._particles: list[dict] = []

        self._timer = QTimer(self)
        self._timer.setInterval(33)   # ~30 fps
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self._celebrate_timer = QTimer(self)
        self._celebrate_timer.setSingleShot(True)
        self._celebrate_timer.timeout.connect(self._end_celebrate)

    # ── public API ──────────────────────────────────────────────────

    def set_state(self, state: str) -> None:
        """Set the companion's animation state.

        *state* is one of ``"idle"``, ``"focus"``, ``"sleep"``.
        (``"celebrate"`` is triggered via :meth:`trigger_celebrate`.)
        """
        if state == self._state:
            return
        if self._state == "celebrate":
            # Don't interrupt celebration
            self._prev_state = state
            return
        self._state = state
        self._phase = 0.0

    def trigger_celebrate(self) -> None:
        """Start a 2‑second celebration, then return to previous state."""
        self._prev_state = self._state
        self._state = "celebrate"
        self._phase = 0.0
        self._particles.clear()
        self._spawn_particles()
        self._celebrate_timer.start(2000)

    def set_session_progress(self, progress: float) -> None:
        """0.0 → 1.0 — used by growth‑dependent companions (Sprout, Zen)."""
        self._session_progress = max(0.0, min(1.0, progress))

    # ── internals ───────────────────────────────────────────────────

    def _tick(self) -> None:
        speed = self._PHASE_SPEEDS.get(self._state, 0.04)
        self._phase += speed
        if self._phase > 100 * math.pi:
            self._phase -= 100 * math.pi

        # Advance particles
        alive: list[dict] = []
        for p in self._particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] += 0.08  # gravity
            p["life"] -= 0.025
            if p["life"] > 0:
                alive.append(p)
        self._particles = alive

        self.update()

    def _end_celebrate(self) -> None:
        self._state = self._prev_state
        self._phase = 0.0
        self._particles.clear()

    def _spawn_particles(self) -> None:
        """Override in subclasses for custom celebrate particles."""
        cx, cy = self.WIDGET_WIDTH / 2, self.WIDGET_HEIGHT / 2
        for _ in range(12):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(1.5, 4.0)
            self._particles.append({
                "x": cx, "y": cy,
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed - 2.0,
                "life": 1.0,
                "color": QColor(
                    random.choice(["#FFD700", "#FF6B6B", "#A6E3A1", "#89B4FA"])
                ),
                "size": random.uniform(2, 5),
            })

    def _paint_particles(self, painter: QPainter) -> None:
        for p in self._particles:
            c = QColor(p["color"])
            c.setAlpha(int(255 * max(0, p["life"])))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(c)
            s = p["size"] * p["life"]
            painter.drawEllipse(QPointF(p["x"], p["y"]), s, s)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        dispatch = {
            "idle":      self._paint_idle,
            "focus":     self._paint_focus,
            "celebrate": self._paint_celebrate,
            "sleep":     self._paint_sleep,
        }
        fn = dispatch.get(self._state, self._paint_idle)
        fn(painter)

        # Particles on top
        if self._particles:
            self._paint_particles(painter)

        painter.end()

    # ── override these ──────────────────────────────────────────────

    def _paint_idle(self, painter: QPainter) -> None:
        pass

    def _paint_focus(self, painter: QPainter) -> None:
        self._paint_idle(painter)

    def _paint_celebrate(self, painter: QPainter) -> None:
        self._paint_idle(painter)

    def _paint_sleep(self, painter: QPainter) -> None:
        self._paint_idle(painter)


# ── 1. Sprout ───────────────────────────────────────────────────────────


class SproutCompanion(BaseCompanion):
    """A small plant that grows during focus sessions."""

    def _stem_height(self) -> float:
        if self._state == "focus":
            return 15.0 + 25.0 * self._session_progress
        return 15.0

    def _paint_idle(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        base_y = self.WIDGET_HEIGHT - 8
        sway = 3.0 * math.sin(self._phase)
        h = self._stem_height()

        # Stem
        stem_top_x = cx + sway
        stem_top_y = base_y - h
        painter.setPen(QPen(QColor("#4CAF50"), 3, Qt.PenStyle.SolidLine))
        painter.drawLine(
            QPointF(cx, base_y), QPointF(stem_top_x, stem_top_y),
        )

        # Pot / soil
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#5D4037"))
        painter.drawRoundedRect(
            QRectF(cx - 12, base_y - 2, 24, 8), 3, 3,
        )

        # Left leaf
        leaf = QPainterPath()
        mid_y = base_y - h * 0.5
        leaf.moveTo(cx + sway * 0.5, mid_y)
        leaf.quadTo(cx - 16 + sway, mid_y - 6, cx - 8 + sway, mid_y + 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#66BB6A"))
        painter.drawPath(leaf)

        # Right leaf
        rleaf = QPainterPath()
        rleaf.moveTo(cx + sway * 0.5, mid_y - 2)
        rleaf.quadTo(cx + 16 + sway, mid_y - 8, cx + 8 + sway, mid_y + 2)
        painter.setBrush(QColor("#81C784"))
        painter.drawPath(rleaf)

    def _paint_focus(self, painter: QPainter) -> None:
        self._paint_idle(painter)

        # Extra leaves as the plant grows
        if self._session_progress > 0.4:
            cx = self.WIDGET_WIDTH / 2
            base_y = self.WIDGET_HEIGHT - 8
            h = self._stem_height()
            sway = 3.0 * math.sin(self._phase)
            top_y = base_y - h * 0.8

            leaf = QPainterPath()
            leaf.moveTo(cx + sway, top_y)
            leaf.quadTo(cx - 12 + sway, top_y - 5, cx - 5 + sway, top_y + 3)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#388E3C"))
            painter.drawPath(leaf)

    def _paint_celebrate(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        base_y = self.WIDGET_HEIGHT - 8
        h = 40.0
        sway = 2.0 * math.sin(self._phase * 3)

        # Full stem
        painter.setPen(QPen(QColor("#4CAF50"), 3))
        painter.drawLine(
            QPointF(cx, base_y), QPointF(cx + sway, base_y - h),
        )

        # Pot
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#5D4037"))
        painter.drawRoundedRect(QRectF(cx - 12, base_y - 2, 24, 8), 3, 3)

        # Flower at top
        flower_x = cx + sway
        flower_y = base_y - h
        petal_colors = ["#FF7043", "#FFD54F", "#FF8A65", "#FFAB40", "#FFF176"]
        for i in range(5):
            angle = (i / 5) * 2 * math.pi + self._phase * 2
            px = flower_x + 7 * math.cos(angle)
            py = flower_y + 7 * math.sin(angle)
            painter.setBrush(QColor(petal_colors[i]))
            painter.drawEllipse(QPointF(px, py), 4, 4)

        # Centre
        painter.setBrush(QColor("#FFD700"))
        painter.drawEllipse(QPointF(flower_x, flower_y), 3, 3)

    def _paint_sleep(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        base_y = self.WIDGET_HEIGHT - 8

        # Droopy stem (leaning right)
        painter.setPen(QPen(QColor("#4CAF50"), 3))
        painter.drawLine(
            QPointF(cx, base_y), QPointF(cx + 8, base_y - 12),
        )

        # Pot
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#5D4037"))
        painter.drawRoundedRect(QRectF(cx - 12, base_y - 2, 24, 8), 3, 3)

        # Droopy leaf
        leaf = QPainterPath()
        leaf.moveTo(cx + 8, base_y - 12)
        leaf.quadTo(cx + 18, base_y - 6, cx + 14, base_y - 2)
        painter.setBrush(QColor("#66BB6A"))
        painter.setOpacity(0.6)
        painter.drawPath(leaf)
        painter.setOpacity(1.0)

    def _spawn_particles(self) -> None:
        cx = self.WIDGET_WIDTH / 2
        top_y = self.WIDGET_HEIGHT - 48
        for _ in range(10):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(1.0, 3.0)
            self._particles.append({
                "x": cx, "y": top_y,
                "vx": math.cos(angle) * speed,
                "vy": -abs(math.sin(angle) * speed) - 1.5,
                "life": 1.0,
                "color": QColor(random.choice(["#FFD700", "#FF7043", "#FFF176"])),
                "size": random.uniform(2, 4),
            })


# ── 2. Ember ────────────────────────────────────────────────────────────


class EmberCompanion(BaseCompanion):
    """A little flame that dances while you work."""

    def _draw_flame(
        self, painter: QPainter, cx: float, base_y: float,
        height: float, flicker: float,
    ) -> None:
        """Draw a layered teardrop flame."""
        layers = [
            ("#FF6B00", 1.0),     # outer
            ("#FF9500", 0.75),    # mid
            ("#FFD700", 0.5),     # inner
            ("#FFFDE7", 0.28),    # core
        ]
        for color_hex, scale in layers:
            h = height * scale
            w = 8 * scale + 2
            ox = random.uniform(-flicker, flicker)
            oy = random.uniform(-flicker * 0.5, flicker * 0.3)

            path = QPainterPath()
            tip_y = base_y - h + oy
            path.moveTo(cx + ox, tip_y)
            path.cubicTo(
                cx - w + ox, base_y - h * 0.4 + oy,
                cx - w * 0.6 + ox, base_y + oy,
                cx + ox, base_y + 2 + oy,
            )
            path.cubicTo(
                cx + w * 0.6 + ox, base_y + oy,
                cx + w + ox, base_y - h * 0.4 + oy,
                cx + ox, tip_y,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color_hex))
            painter.drawPath(path)

    def _paint_idle(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        base_y = self.WIDGET_HEIGHT - 6
        h = 20 + 3 * math.sin(self._phase)
        self._draw_flame(painter, cx, base_y, h, flicker=2.0)

    def _paint_focus(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        base_y = self.WIDGET_HEIGHT - 6
        h = 25 + 15 * self._session_progress + 4 * math.sin(self._phase * 1.5)
        self._draw_flame(painter, cx, base_y, h, flicker=3.5)

    def _paint_celebrate(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        base_y = self.WIDGET_HEIGHT - 6
        h = 42 + 5 * math.sin(self._phase * 3)
        self._draw_flame(painter, cx, base_y, h, flicker=4.5)

    def _paint_sleep(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        base_y = self.WIDGET_HEIGHT - 6
        pulse = 0.6 + 0.15 * math.sin(self._phase)
        painter.setOpacity(pulse)

        # Small glowing ember
        grad = QRadialGradient(cx, base_y - 5, 10)
        grad.setColorAt(0.0, QColor("#FF6B00"))
        grad.setColorAt(0.5, QColor("#CC3300"))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawEllipse(QPointF(cx, base_y - 5), 10, 8)
        painter.setOpacity(1.0)

    def _spawn_particles(self) -> None:
        cx = self.WIDGET_WIDTH / 2
        for _ in range(12):
            self._particles.append({
                "x": cx + random.uniform(-6, 6),
                "y": self.WIDGET_HEIGHT - 30,
                "vx": random.uniform(-1.5, 1.5),
                "vy": random.uniform(-4, -1.5),
                "life": 1.0,
                "color": QColor(
                    random.choice(["#FFFDE7", "#FFD700", "#FF9500"])
                ),
                "size": random.uniform(1.5, 3.5),
            })


# ── 3. Ripple ───────────────────────────────────────────────────────────


class RippleCompanion(BaseCompanion):
    """A water droplet that creates expanding circles."""

    def _draw_droplet(self, painter: QPainter, cx: float, cy: float) -> None:
        path = QPainterPath()
        path.moveTo(cx, cy - 6)
        path.cubicTo(cx - 5, cy, cx - 4, cy + 5, cx, cy + 6)
        path.cubicTo(cx + 4, cy + 5, cx + 5, cy, cx, cy - 6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#4FC3F7"))
        painter.drawPath(path)

    def _draw_rings(
        self, painter: QPainter, cx: float, cy: float, count: int, speed: float,
    ) -> None:
        for i in range(count):
            offset = (self._phase * speed + i * (1.0 / count)) % 1.0
            radius = 5 + offset * 30
            alpha = int(160 * (1.0 - offset))
            pen = QPen(QColor(79, 195, 247, alpha), 1.5)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy + 10), radius, radius * 0.4)

    def _paint_idle(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        cy = self.WIDGET_HEIGHT / 2 - 5
        self._draw_droplet(painter, cx, cy)
        self._draw_rings(painter, cx, cy, count=1, speed=0.3)

    def _paint_focus(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        cy = self.WIDGET_HEIGHT / 2 - 5
        self._draw_droplet(painter, cx, cy)
        self._draw_rings(painter, cx, cy, count=3, speed=0.5)

    def _paint_celebrate(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        cy = self.WIDGET_HEIGHT / 2 - 5
        # Bouncing droplet
        bounce = abs(8 * math.sin(self._phase * 3))
        self._draw_droplet(painter, cx, cy - bounce)
        self._draw_rings(painter, cx, cy, count=4, speed=1.0)

    def _paint_sleep(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        cy = self.WIDGET_HEIGHT / 2 - 3
        pulse = 0.5 + 0.15 * math.sin(self._phase)
        painter.setOpacity(pulse)
        self._draw_droplet(painter, cx, cy)
        painter.setOpacity(1.0)

    def _spawn_particles(self) -> None:
        cx = self.WIDGET_WIDTH / 2
        cy = self.WIDGET_HEIGHT / 2
        for _ in range(10):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(2, 5)
            self._particles.append({
                "x": cx, "y": cy,
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed - 2,
                "life": 1.0,
                "color": QColor(
                    random.choice(["#4FC3F7", "#81D4FA", "#B3E5FC"])
                ),
                "size": random.uniform(2, 4),
            })


# ── 4. Pixel ────────────────────────────────────────────────────────────


class PixelCompanion(BaseCompanion):
    """A retro pixel art robot with idle animations."""

    _PX = 4  # size of each "pixel"

    def _draw_robot(
        self, painter: QPainter,
        cx: float, base_y: float,
        eye_color: str = "#00E676",
        body_alpha: float = 1.0,
        arm_offset: int = 0,
    ) -> None:
        px = self._PX
        # Body origin: top-left of the 8x8 grid centred at cx
        ox = cx - 4 * px
        oy = base_y - 8 * px

        painter.setOpacity(body_alpha)
        painter.setPen(Qt.PenStyle.NoPen)

        # Body (rows 2-7, cols 1-6) — 6x6 block
        painter.setBrush(QColor("#607D8B"))
        painter.drawRect(QRectF(ox + px, oy + 2 * px, 6 * px, 6 * px))

        # Head (rows 0-2, cols 2-5) — 4x2 block
        painter.setBrush(QColor("#78909C"))
        painter.drawRect(QRectF(ox + 2 * px, oy, 4 * px, 2 * px))

        # Antenna (row -1, col 3.5)
        painter.setBrush(QColor("#FFC107"))
        painter.drawRect(QRectF(ox + 3.5 * px, oy - px, px, px))

        # Eyes (row 1, cols 3 and 4)
        painter.setBrush(QColor(eye_color))
        painter.drawRect(QRectF(ox + 3 * px, oy + px, px, px))
        painter.drawRect(QRectF(ox + 4 * px, oy + px, px, px))

        # Arms (rows 3-5, cols 0 and 7)
        painter.setBrush(QColor("#546E7A"))
        # left arm
        painter.drawRect(QRectF(
            ox, oy + (3 + arm_offset) * px, px, 2 * px,
        ))
        # right arm
        painter.drawRect(QRectF(
            ox + 7 * px, oy + (3 - arm_offset) * px, px, 2 * px,
        ))

        # Feet (row 8, cols 2 and 5)
        painter.setBrush(QColor("#455A64"))
        painter.drawRect(QRectF(ox + 2 * px, oy + 8 * px, px, px))
        painter.drawRect(QRectF(ox + 5 * px, oy + 8 * px, px, px))

        painter.setOpacity(1.0)

    def _paint_idle(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        bob = 2 * math.sin(self._phase)
        base_y = self.WIDGET_HEIGHT - 4 + bob
        self._draw_robot(painter, cx, base_y)

    def _paint_focus(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        base_y = self.WIDGET_HEIGHT - 4
        # Typing animation: arms alternate
        arm = 1 if math.sin(self._phase * 4) > 0 else -1
        # Blink every ~3s
        eye = "#00E676"
        if (self._phase % 6.0) > 5.8:
            eye = "#607D8B"  # closed
        self._draw_robot(painter, cx, base_y, eye_color=eye, arm_offset=arm)

    def _paint_celebrate(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        # Jump
        jump = 10 * max(0, math.sin(self._phase * 2.5))
        base_y = self.WIDGET_HEIGHT - 4 - jump
        self._draw_robot(painter, cx, base_y, eye_color="#F44336")

    def _paint_sleep(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        base_y = self.WIDGET_HEIGHT - 4
        self._draw_robot(
            painter, cx, base_y,
            eye_color="#607D8B", body_alpha=0.7,
        )

        # Z's
        px = self._PX
        ox = cx + 5 * px
        oy = base_y - 9 * px
        z_phase = self._phase * 0.5
        for i in range(2):
            alpha = int(180 * (0.5 + 0.5 * math.sin(z_phase + i * 1.5)))
            painter.setPen(QPen(QColor(255, 255, 255, alpha), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            size = 4 + i * 3
            drift = i * 6
            painter.drawText(
                QPointF(ox + drift, oy - drift - 4 * math.sin(z_phase + i)),
                "z",
            )

    def _spawn_particles(self) -> None:
        cx = self.WIDGET_WIDTH / 2
        for _ in range(8):
            self._particles.append({
                "x": cx + random.uniform(-12, 12),
                "y": self.WIDGET_HEIGHT - 20,
                "vx": random.uniform(-1.5, 1.5),
                "vy": random.uniform(-3.5, -1),
                "life": 1.0,
                "color": QColor(
                    random.choice(["#00E676", "#FFC107", "#F44336"])
                ),
                "size": random.uniform(2, 4),
            })


# ── 5. Nova ─────────────────────────────────────────────────────────────


class NovaCompanion(BaseCompanion):
    """A small star that pulses and glows brighter as you focus."""

    def _draw_star(
        self, painter: QPainter,
        cx: float, cy: float,
        outer_r: float, inner_r: float,
        color: str, glow_r: float = 0,
    ) -> None:
        # Glow
        if glow_r > 0:
            grad = QRadialGradient(cx, cy, glow_r)
            grad.setColorAt(0.0, QColor(255, 215, 0, 50))
            grad.setColorAt(1.0, QColor(255, 215, 0, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(grad)
            painter.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        # Star shape
        path = QPainterPath()
        points = 5
        for i in range(points * 2):
            angle = (i / (points * 2)) * 2 * math.pi - math.pi / 2
            r = outer_r if i % 2 == 0 else inner_r
            px = cx + r * math.cos(angle)
            py = cy + r * math.sin(angle)
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        path.closeSubpath()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawPath(path)

    def _paint_idle(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        cy = self.WIDGET_HEIGHT / 2
        scale = 0.95 + 0.05 * math.sin(self._phase * 1.5)
        outer = 14 * scale
        inner = 6 * scale
        self._draw_star(painter, cx, cy, outer, inner, "#FFD700", glow_r=20)

    def _paint_focus(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        cy = self.WIDGET_HEIGHT / 2
        scale = 0.95 + 0.08 * math.sin(self._phase * 2)
        brightness = self._session_progress
        outer = (14 + 4 * brightness) * scale
        inner = (6 + 2 * brightness) * scale
        glow = 20 + 15 * brightness
        # Shift toward white
        color = "#FFD700" if brightness < 0.7 else "#FFFDE7"
        self._draw_star(painter, cx, cy, outer, inner, color, glow_r=glow)

    def _paint_celebrate(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        cy = self.WIDGET_HEIGHT / 2
        self._draw_star(painter, cx, cy, 18, 8, "#FFFDE7", glow_r=35)

        # Rays
        for i in range(6):
            angle = (i / 6) * 2 * math.pi + self._phase * 1.5
            ray_len = 20 + 10 * math.sin(self._phase * 3 + i)
            ex = cx + ray_len * math.cos(angle)
            ey = cy + ray_len * math.sin(angle)
            alpha = int(200 * (0.5 + 0.5 * math.sin(self._phase * 2 + i)))
            painter.setPen(QPen(QColor(255, 215, 0, alpha), 2))
            painter.drawLine(QPointF(cx, cy), QPointF(ex, ey))

    def _paint_sleep(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        cy = self.WIDGET_HEIGHT / 2
        painter.setOpacity(0.4)
        self._draw_star(painter, cx, cy, 12, 5, "#B0A060", glow_r=12)
        painter.setOpacity(1.0)


# ── 6. Zen ──────────────────────────────────────────────────────────────


class ZenCompanion(BaseCompanion):
    """A floating lotus that opens petals with each completed pomodoro."""

    def _draw_lotus(
        self, painter: QPainter,
        cx: float, cy: float,
        openness: float,          # 0..1
        alpha: float = 1.0,
    ) -> None:
        painter.setOpacity(alpha)
        hover = 2 * math.sin(self._phase * 0.8)
        cy += hover

        petal_color = QColor("#F48FB1")
        inner_color = QColor("#F8BBD0")
        centre_color = QColor("#FFD54F")

        # 6 petals in pairs (3 pairs)
        petal_pairs = [
            (0.0, 0.33),   # pair 1 opens at 0%
            (0.33, 0.66),  # pair 2 opens at 33%
            (0.66, 1.0),   # pair 3 opens at 66%
        ]

        for pair_idx, (start_pct, _) in enumerate(petal_pairs):
            pair_open = max(0.0, min(1.0, (openness - start_pct) / 0.34))
            if pair_open <= 0:
                continue

            for side in (-1, 1):
                angle = side * (25 + 35 * pair_open) * (math.pi / 180)
                base_angle = pair_idx * 0.3 * side

                # Petal shape
                path = QPainterPath()
                length = 14 * pair_open
                width = 5 * pair_open

                # Petal base at centre, extends outward
                tip_x = cx + math.sin(angle + base_angle) * length
                tip_y = cy - math.cos(angle + base_angle) * length - 4

                path.moveTo(cx, cy - 2)
                path.quadTo(
                    cx + side * width, cy - length * 0.6,
                    tip_x, tip_y,
                )
                path.quadTo(
                    cx - side * width * 0.3, cy - length * 0.4,
                    cx, cy - 2,
                )

                c = inner_color if pair_idx == 2 else petal_color
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(c)
                painter.drawPath(path)

        # Centre dot
        painter.setBrush(centre_color)
        painter.drawEllipse(QPointF(cx, cy - 2), 3, 3)

        # Stem
        painter.setPen(QPen(QColor("#66BB6A"), 2))
        painter.drawLine(QPointF(cx, cy + 2), QPointF(cx, cy + 15))

        painter.setOpacity(1.0)

    def _paint_idle(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        cy = self.WIDGET_HEIGHT / 2 + 2
        self._draw_lotus(painter, cx, cy, openness=0.15)

    def _paint_focus(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        cy = self.WIDGET_HEIGHT / 2 + 2
        self._draw_lotus(painter, cx, cy, openness=self._session_progress)

    def _paint_celebrate(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        cy = self.WIDGET_HEIGHT / 2 + 2
        self._draw_lotus(painter, cx, cy, openness=1.0)

    def _paint_sleep(self, painter: QPainter) -> None:
        cx = self.WIDGET_WIDTH / 2
        cy = self.WIDGET_HEIGHT / 2 + 5  # settled lower
        self._draw_lotus(painter, cx, cy, openness=0.05, alpha=0.6)

    def _spawn_particles(self) -> None:
        cx = self.WIDGET_WIDTH / 2
        cy = self.WIDGET_HEIGHT / 2 - 5
        for _ in range(8):
            self._particles.append({
                "x": cx + random.uniform(-5, 5),
                "y": cy,
                "vx": random.uniform(-0.8, 0.8),
                "vy": random.uniform(-3.0, -1.0),
                "life": 1.0,
                "color": QColor(
                    random.choice(["#FFD54F", "#FFF176", "#FFEE58"])
                ),
                "size": random.uniform(1.5, 3),
            })


# ── factory ─────────────────────────────────────────────────────────────

COMPANION_WIDGETS: dict[str, type[BaseCompanion]] = {
    "sprout": SproutCompanion,
    "ember":  EmberCompanion,
    "ripple": RippleCompanion,
    "pixel":  PixelCompanion,
    "nova":   NovaCompanion,
    "zen":    ZenCompanion,
}


def create_companion(key: str, parent: QWidget | None = None) -> BaseCompanion:
    """Create a companion widget by key.  Falls back to Sprout."""
    cls = COMPANION_WIDGETS.get(key, SproutCompanion)
    return cls(parent)
