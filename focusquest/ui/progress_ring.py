"""Circular progress ring widget rendered with QPainter.

The ring is the centrepiece of the Focus tab:
- Depletes clockwise as the session progresses.
- Colour-coded by timer state (working=coral, break=teal, etc.).
- Shows MM:SS in bold text at the centre plus a state label.
- Smooth animated transitions between states.
- Idle pulse animation to invite interaction.
- Celebration burst (sparkle particles) when a session completes.
"""

from __future__ import annotations

import math
import random
from typing import Optional

from PyQt6.QtCore import (
    Qt, QRectF, QPointF, QTimer, QPropertyAnimation,
    QVariantAnimation, QEasingCurve, pyqtProperty,
)
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QConicalGradient, QRadialGradient,
    QFont, QFontMetrics,
)
from PyQt6.QtWidgets import QWidget

from ..timer.engine import TimerState, SessionType
from .styles import STATE_COLORS


# ── helpers ──────────────────────────────────────────────────────────────────

def _lerp_color(c1: QColor, c2: QColor, t: float) -> QColor:
    """Linearly interpolate between two QColors."""
    t = max(0.0, min(1.0, t))
    return QColor(
        int(c1.red()   + (c2.red()   - c1.red())   * t),
        int(c1.green() + (c2.green() - c1.green()) * t),
        int(c1.blue()  + (c2.blue()  - c1.blue())  * t),
        int(c1.alpha() + (c2.alpha() - c1.alpha()) * t),
    )


# ── sparkle particle ────────────────────────────────────────────────────────

class _Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "color", "size")

    def __init__(self, cx: float, cy: float, color: QColor) -> None:
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(2.0, 6.0)
        self.x = cx
        self.y = cy
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.life = 1.0
        self.color = QColor(color)
        self.size = random.uniform(3, 7)

    def tick(self, dt: float) -> bool:
        """Advance and return True if still alive."""
        self.x += self.vx * dt * 60
        self.y += self.vy * dt * 60
        self.vy += 0.12 * dt * 60  # gravity
        self.life -= dt * 1.8
        return self.life > 0


# ── main widget ──────────────────────────────────────────────────────────────


class ProgressRing(QWidget):
    """Custom-painted circular timer ring."""

    # Ring geometry constants
    RING_DIAMETER = 300
    RING_THICKNESS = 14
    GLOW_EXTRA = 6  # extra radius for the glow effect

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(self.RING_DIAMETER + 40, self.RING_DIAMETER + 40)

        # ── state ──────────────────────────────────────────────────────
        self._percent: float = 0.0           # 0..1 arc fill
        self._display_percent: float = 0.0   # animated arc fill
        self._time_text: str = "25:00"
        self._state_label: str = "READY"
        self._round_text: str = "Round 1 of 4"
        self._timer_state: TimerState = TimerState.IDLE

        # Per-theme ring colors (may be overridden by set_ring_colors)
        self._ring_colors: dict[TimerState, tuple[str, str]] = dict(STATE_COLORS)

        # Colors (will be set by apply_state)
        self._primary_color = QColor("#4A4A5E")
        self._secondary_color = QColor("#3A3A4E")
        self._target_primary = QColor("#4A4A5E")
        self._target_secondary = QColor("#3A3A4E")

        # Text colors
        self._text_color = QColor("#E2E2F0")
        self._muted_color = QColor("#7A7A9A")
        self._bg_color = QColor("#1A1A2E")

        # ── arc transition animation ───────────────────────────────────
        self._arc_anim = QVariantAnimation(self)
        self._arc_anim.setDuration(500)
        self._arc_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._arc_anim.valueChanged.connect(self._on_arc_anim)

        # ── color transition animation ─────────────────────────────────
        self._color_progress: float = 1.0
        self._old_primary = QColor(self._primary_color)
        self._old_secondary = QColor(self._secondary_color)

        self._color_anim = QVariantAnimation(self)
        self._color_anim.setDuration(500)
        self._color_anim.setStartValue(0.0)
        self._color_anim.setEndValue(1.0)
        self._color_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._color_anim.valueChanged.connect(self._on_color_anim)

        # ── idle pulse ─────────────────────────────────────────────────
        self._pulse_phase: float = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(33)  # ~30 fps
        self._pulse_timer.timeout.connect(self._on_pulse_tick)

        # ── active glow pulse ──────────────────────────────────────────
        self._glow_phase: float = 0.0
        self._glow_timer = QTimer(self)
        self._glow_timer.setInterval(33)
        self._glow_timer.timeout.connect(self._on_glow_tick)

        # ── celebration particles ──────────────────────────────────────
        self._particles: list[_Particle] = []
        self._particle_timer = QTimer(self)
        self._particle_timer.setInterval(16)  # ~60 fps
        self._particle_timer.timeout.connect(self._on_particle_tick)

        # Start idle pulse
        self._pulse_timer.start()

    # ══════════════════════════════════════════════════════════════════
    #  PUBLIC API
    # ══════════════════════════════════════════════════════════════════

    def set_percent(self, pct: float) -> None:
        """Update the arc fill (0..1). Smoothly animates."""
        self._percent = pct
        # Small ticks — animate smoothly
        self._arc_anim.stop()
        self._arc_anim.setStartValue(self._display_percent)
        self._arc_anim.setEndValue(pct)
        self._arc_anim.start()

    def set_time_text(self, text: str) -> None:
        self._time_text = text
        self.update()

    def set_state_label(self, text: str) -> None:
        self._state_label = text
        self.update()

    def set_round_text(self, text: str) -> None:
        self._round_text = text
        self.update()

    def set_ring_colors(
        self, ring_colors: dict[TimerState, tuple[str, str]],
    ) -> None:
        """Override per-theme ring gradient colours.

        Pass the result of ``get_ring_colors(theme_key)`` here.
        """
        self._ring_colors = ring_colors
        # Re-apply current state to pick up the new colours
        self.apply_state(self._timer_state)

    def apply_state(self, state: TimerState) -> None:
        """Update colors and animations for a new timer state."""
        old_state = self._timer_state
        self._timer_state = state

        # Get target colors — per-theme first, then global fallback
        primary_hex, secondary_hex = self._ring_colors.get(
            state, STATE_COLORS.get(state, ("#4A4A5E", "#3A3A4E"))
        )

        # Animate color transition
        self._old_primary = QColor(self._primary_color)
        self._old_secondary = QColor(self._secondary_color)
        self._target_primary = QColor(primary_hex)
        self._target_secondary = QColor(secondary_hex)
        self._color_anim.stop()
        self._color_anim.setStartValue(0.0)
        self._color_anim.setEndValue(1.0)
        self._color_anim.start()

        # Manage animation timers
        if state == TimerState.IDLE:
            self._glow_timer.stop()
            self._glow_phase = 0.0
            if not self._pulse_timer.isActive():
                self._pulse_timer.start()
        elif state == TimerState.PAUSED:
            self._glow_timer.stop()
            self._pulse_timer.stop()
            self._glow_phase = 0.0
        else:
            # Running state — active glow
            self._pulse_timer.stop()
            self._pulse_phase = 0.0
            if not self._glow_timer.isActive():
                self._glow_timer.start()

        # Celebration when transitioning from WORKING to something else
        if old_state == TimerState.WORKING and state != TimerState.PAUSED:
            self._spawn_celebration()

    def apply_palette(self, palette: dict[str, str]) -> None:
        """Update text/bg colors from theme palette."""
        self._text_color = QColor(palette.get("text", "#E2E2F0"))
        self._muted_color = QColor(palette.get("text_muted", "#7A7A9A"))
        self._bg_color = QColor(palette.get("bg", "#1A1A2E"))
        self.update()

    def trigger_celebration(self) -> None:
        """Manually trigger celebration sparkles."""
        self._spawn_celebration()

    # ══════════════════════════════════════════════════════════════════
    #  ANIMATION SLOTS
    # ══════════════════════════════════════════════════════════════════

    def _on_arc_anim(self, value: object) -> None:
        self._display_percent = float(value)  # type: ignore[arg-type]
        self.update()

    def _on_color_anim(self, value: object) -> None:
        t = float(value)  # type: ignore[arg-type]
        self._primary_color = _lerp_color(
            self._old_primary, self._target_primary, t
        )
        self._secondary_color = _lerp_color(
            self._old_secondary, self._target_secondary, t
        )
        self.update()

    def _on_pulse_tick(self) -> None:
        """Idle state: gentle breathing pulse."""
        self._pulse_phase += 0.04
        if self._pulse_phase > 2 * math.pi:
            self._pulse_phase -= 2 * math.pi
        self.update()

    def _on_glow_tick(self) -> None:
        """Active state: subtle glow pulse."""
        self._glow_phase += 0.06
        if self._glow_phase > 2 * math.pi:
            self._glow_phase -= 2 * math.pi
        self.update()

    def _on_particle_tick(self) -> None:
        """Advance celebration particles."""
        dt = 0.016
        self._particles = [p for p in self._particles if p.tick(dt)]
        if not self._particles:
            self._particle_timer.stop()
        self.update()

    def _spawn_celebration(self) -> None:
        """Create a burst of sparkle particles from the ring."""
        cx = self.width() / 2
        cy = self.height() / 2
        radius = self.RING_DIAMETER / 2

        colors = [
            QColor("#FFD700"),  # gold
            QColor("#FF6B6B"),  # coral
            QColor("#A6E3A1"),  # green
            QColor("#89B4FA"),  # blue
            QColor("#CBA6F7"),  # purple
            QColor("#F9E2AF"),  # yellow
        ]

        for _ in range(40):
            angle = random.uniform(0, 2 * math.pi)
            px = cx + math.cos(angle) * radius
            py = cy + math.sin(angle) * radius
            color = random.choice(colors)
            self._particles.append(_Particle(px, py, color))

        if not self._particle_timer.isActive():
            self._particle_timer.start()

    # ══════════════════════════════════════════════════════════════════
    #  PAINTING
    # ══════════════════════════════════════════════════════════════════

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx, cy = w / 2, h / 2
        diameter = min(w, h) - 40
        if diameter < 100:
            diameter = 100
        radius = diameter / 2
        thickness = self.RING_THICKNESS

        ring_rect = QRectF(
            cx - radius, cy - radius,
            diameter, diameter,
        )

        # ── background track ─────────────────────────────────────────
        track_color = QColor(self._primary_color)
        track_color.setAlpha(35)
        track_pen = QPen(track_color, thickness, Qt.PenStyle.SolidLine)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.drawEllipse(ring_rect)

        # ── idle pulse glow ──────────────────────────────────────────
        if self._timer_state == TimerState.IDLE and self._pulse_phase > 0:
            pulse_alpha = int(25 + 20 * math.sin(self._pulse_phase))
            pulse_extra = 2 + 3 * math.sin(self._pulse_phase)
            glow_color = QColor(self._primary_color)
            glow_color.setAlpha(pulse_alpha)
            glow_pen = QPen(glow_color, thickness + pulse_extra, Qt.PenStyle.SolidLine)
            glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(glow_pen)
            painter.drawEllipse(ring_rect)

        # ── active arc ───────────────────────────────────────────────
        pct = self._display_percent
        if pct > 0.001:
            # Conical gradient for the arc
            gradient = QConicalGradient(cx, cy, 90)
            gradient.setColorAt(0.0, self._primary_color)
            gradient.setColorAt(0.5, self._secondary_color)
            gradient.setColorAt(1.0, self._primary_color)

            arc_pen = QPen(
                gradient, thickness, Qt.PenStyle.SolidLine,
            )
            arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(arc_pen)

            # Qt arcs: start at 12 o'clock (90*16), go clockwise (negative)
            start_angle = 90 * 16
            span_angle = -int(pct * 360 * 16)
            painter.drawArc(ring_rect, start_angle, span_angle)

            # ── active glow ──────────────────────────────────────────
            if self._glow_timer.isActive():
                glow_alpha = int(20 + 15 * math.sin(self._glow_phase))
                glow_color = QColor(self._primary_color)
                glow_color.setAlpha(glow_alpha)
                glow_pen = QPen(
                    glow_color, thickness + self.GLOW_EXTRA,
                    Qt.PenStyle.SolidLine,
                )
                glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(glow_pen)
                painter.drawArc(ring_rect, start_angle, span_angle)

        # ── centre text: time ────────────────────────────────────────
        time_font = QFont()
        time_font.setPixelSize(52)
        time_font.setWeight(QFont.Weight.Bold)
        time_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        painter.setFont(time_font)
        painter.setPen(self._text_color)

        time_rect = QRectF(ring_rect)
        time_rect.moveTop(time_rect.top() - 16)
        painter.drawText(
            time_rect, Qt.AlignmentFlag.AlignCenter, self._time_text,
        )

        # ── centre text: state label ─────────────────────────────────
        label_font = QFont()
        label_font.setPixelSize(13)
        label_font.setWeight(QFont.Weight.DemiBold)
        label_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
        painter.setFont(label_font)

        # Use state color for the label
        label_color = QColor(self._primary_color)
        label_color.setAlpha(200)
        painter.setPen(label_color)

        label_rect = QRectF(ring_rect)
        label_rect.moveTop(label_rect.top() + 30)
        painter.drawText(
            label_rect, Qt.AlignmentFlag.AlignCenter, self._state_label,
        )

        # ── centre text: round indicator ─────────────────────────────
        round_font = QFont()
        round_font.setPixelSize(11)
        painter.setFont(round_font)
        painter.setPen(self._muted_color)

        round_rect = QRectF(ring_rect)
        round_rect.moveTop(round_rect.top() + 55)
        painter.drawText(
            round_rect, Qt.AlignmentFlag.AlignCenter, self._round_text,
        )

        # ── celebration particles ────────────────────────────────────
        for p in self._particles:
            c = QColor(p.color)
            c.setAlpha(int(255 * max(0, p.life)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(c)
            size = p.size * p.life
            painter.drawEllipse(QPointF(p.x, p.y), size, size)

        painter.end()
