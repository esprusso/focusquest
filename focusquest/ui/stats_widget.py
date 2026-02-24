"""Stats dashboard — rewarding proof that effort is paying off.

Sections
--------
1. **Today's Summary** — session ring, focus minutes, XP, streak
2. **Weekly Activity Chart** — QPainter bar chart, 7 days, today highlighted
3. **Monthly Heatmap** — GitHub-style 30-day contribution grid with hover tooltips
4. **All-Time Stats** — 6 stat cards in a 3×2 grid
5. **Level Progress** — XP bar + visual roadmap with upcoming unlock teasers

All charts are custom QPainter widgets — no matplotlib needed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from PyQt6.QtCore import Qt, QRectF, QPointF, QRect
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QFont, QConicalGradient, QFontMetrics,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QGridLayout, QProgressBar, QToolTip, QSizePolicy,
)

from ..database.db import get_session
from ..database.models import UserProgress, DailyStats, Session
from ..gamification.xp import xp_in_current_level, xp_for_level, title_for_level
from ..gamification.unlockables import REGISTRY, UnlockableItem


# ═══════════════════════════════════════════════════════════════════════════
#  FORMAT HELPERS
# ═══════════════════════════════════════════════════════════════════════════


def _format_focus_hours(total_minutes: int) -> str:
    """125 → '2h 5m', 0 → '0m', 60 → '1h 0m'."""
    if total_minutes <= 0:
        return "0m"
    hours = total_minutes // 60
    mins = total_minutes % 60
    if hours == 0:
        return f"{mins}m"
    return f"{hours}h {mins}m"


def _format_hour(hour: int | None) -> str:
    """14 → '2 PM', None → '—'."""
    if hour is None:
        return "\u2014"
    if hour == 0:
        return "12 AM"
    if hour < 12:
        return f"{hour} AM"
    if hour == 12:
        return "12 PM"
    return f"{hour - 12} PM"


# ═══════════════════════════════════════════════════════════════════════════
#  DATA CACHE
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class _StatsCache:
    """Snapshot of all data the dashboard needs."""

    # Today
    today_sessions: int = 0
    today_minutes: int = 0
    today_xp: int = 0
    # Progress
    level: int = 1
    total_xp: int = 0
    earned_in_level: int = 0
    needed_for_level: int = 200
    streak: int = 0
    title: str = "Focus Apprentice"
    # All-time
    total_sessions: int = 0
    total_minutes: int = 0
    longest_streak: int = 0
    favorite_hour: int | None = None
    avg_sessions_per_day: float = 0.0
    # Chart data
    weekly: list[tuple[str, int, bool]] = field(default_factory=list)
    weekly_total_minutes: int = 0
    monthly: list[dict] = field(default_factory=list)
    # Teasers
    teasers: list = field(default_factory=list)
    next_unlock: object | None = None


def _load_stats() -> _StatsCache:
    """Run all queries in a single session and return a filled cache."""
    cache = _StatsCache()
    today = date.today()

    with get_session() as db:
        # ── UserProgress ──────────────────────────────────────────────
        progress: UserProgress | None = db.query(UserProgress).first()
        if progress:
            cache.level = progress.current_level
            cache.total_xp = progress.total_xp
            earned, needed = xp_in_current_level(progress.total_xp)
            cache.earned_in_level = earned
            cache.needed_for_level = needed
            cache.streak = progress.current_streak_days
            cache.title = title_for_level(progress.current_level)
            cache.total_sessions = progress.total_sessions_completed
            cache.total_minutes = progress.total_focus_minutes
            cache.longest_streak = progress.longest_streak_days

        # ── Today's DailyStats ────────────────────────────────────────
        today_row: DailyStats | None = (
            db.query(DailyStats).filter_by(date=today).first()
        )
        if today_row:
            cache.today_sessions = today_row.sessions_completed
            cache.today_minutes = today_row.focus_minutes
            cache.today_xp = today_row.xp_earned

        # ── Weekly chart (last 7 days) ────────────────────────────────
        weekly: list[tuple[str, int, bool]] = []
        weekly_total = 0
        for offset in range(6, -1, -1):
            day = today - timedelta(days=offset)
            label = day.strftime("%a")
            is_today = offset == 0
            row: DailyStats | None = (
                db.query(DailyStats).filter_by(date=day).first()
            )
            minutes = row.focus_minutes if row else 0
            weekly.append((label, minutes, is_today))
            weekly_total += minutes
        cache.weekly = weekly
        cache.weekly_total_minutes = weekly_total

        # ── Monthly heatmap (last 30 days) ────────────────────────────
        monthly: list[dict] = []
        for offset in range(29, -1, -1):
            day = today - timedelta(days=offset)
            row: DailyStats | None = (
                db.query(DailyStats).filter_by(date=day).first()
            )
            monthly.append({
                "date": day,
                "sessions": row.sessions_completed if row else 0,
                "minutes": row.focus_minutes if row else 0,
                "xp": row.xp_earned if row else 0,
            })
        cache.monthly = monthly

        # ── Favorite focus hour ───────────────────────────────────────
        try:
            from sqlalchemy import func, cast, Integer
            # SQLite: strftime('%H', start_time) gives the hour as a string
            hour_col = func.cast(
                func.strftime('%H', Session.start_time), Integer
            ).label('hr')
            result = (
                db.query(hour_col, func.count().label('cnt'))
                .filter(
                    Session.session_type == 'work',
                    Session.completed.is_(True),
                )
                .group_by('hr')
                .order_by(func.count().desc())
                .first()
            )
            if result:
                cache.favorite_hour = int(result[0])
        except Exception:
            pass  # graceful fallback

        # ── Average sessions per active day ───────────────────────────
        try:
            from sqlalchemy import func
            active_days = (
                db.query(func.count())
                .filter(DailyStats.sessions_completed > 0)
                .scalar()
            ) or 0
            if active_days > 0 and cache.total_sessions > 0:
                cache.avg_sessions_per_day = round(
                    cache.total_sessions / active_days, 1
                )
        except Exception:
            pass

    # ── Teasers (no DB needed) ────────────────────────────────────────
    cache.teasers = REGISTRY.teasers(cache.level, count=3)
    cache.next_unlock = REGISTRY.next_upcoming(cache.level)

    return cache


# ═══════════════════════════════════════════════════════════════════════════
#  SESSION RING — mini donut chart for today's sessions
# ═══════════════════════════════════════════════════════════════════════════


class _SessionRing(QWidget):
    """Mini circular progress ring showing completed / target sessions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(64, 64)
        self._completed = 0
        self._target = 6
        self._accent = "#CBA6F7"
        self._track = "#3A3A4E"
        self._text_color = "#E2E2F0"

    def set_data(self, completed: int, target: int = 6) -> None:
        self._completed = completed
        self._target = max(target, 1)
        self.update()

    def set_colors(self, accent: str, track: str, text: str) -> None:
        self._accent = accent
        self._track = track
        self._text_color = text
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        s = min(self.width(), self.height())
        pen_width = 5
        rect = QRectF(
            pen_width / 2, pen_width / 2,
            s - pen_width, s - pen_width,
        )

        # Track
        track_pen = QPen(QColor(self._track), pen_width)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(rect, 0, 360 * 16)

        # Filled arc
        pct = min(self._completed / self._target, 1.0)
        if pct > 0:
            arc_pen = QPen(QColor(self._accent), pen_width)
            arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(arc_pen)
            span = int(pct * 360 * 16)
            painter.drawArc(rect, 90 * 16, -span)

        # Center text
        painter.setPen(QColor(self._text_color))
        font = QFont()
        font.setPixelSize(14)
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(
            QRect(0, 0, s, s),
            Qt.AlignmentFlag.AlignCenter,
            f"{self._completed}/{self._target}",
        )

        painter.end()


# ═══════════════════════════════════════════════════════════════════════════
#  WEEKLY BAR CHART
# ═══════════════════════════════════════════════════════════════════════════


class WeeklyBarChart(QWidget):
    """Bar chart showing focus minutes per day for the last 7 days."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: list[tuple[str, int, bool]] = []
        self._accent = "#CBA6F7"
        self._accent2 = "#B4BEFE"
        self._bg = "#1A1A2E"
        self._text_color = "#E2E2F0"
        self._text_muted = "#6C7086"
        self._border = "#3A3A4E"
        self.setMinimumHeight(180)

    def set_data(self, data: list[tuple[str, int, bool]]) -> None:
        """data: list of (label, value, is_today) tuples."""
        self._data = data
        self.update()

    def set_colors(
        self,
        accent: str,
        accent2: str,
        bg: str,
        text: str,
        text_muted: str,
        border: str,
    ) -> None:
        self._accent = accent
        self._accent2 = accent2
        self._bg = bg
        self._text_color = text
        self._text_muted = text_muted
        self._border = border
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        if not self._data:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        left_margin = 8
        right_margin = 8
        top_margin = 20
        bottom_margin = 28
        chart_w = w - left_margin - right_margin
        chart_h = h - top_margin - bottom_margin

        max_val = max((v for _, v, _ in self._data), default=1) or 1

        # ── gridlines ─────────────────────────────────────────────────
        grid_pen = QPen(QColor(self._border))
        grid_pen.setStyle(Qt.PenStyle.DotLine)
        grid_pen.setWidthF(0.5)
        painter.setPen(grid_pen)

        for frac in (0.25, 0.50, 0.75):
            y = int(top_margin + chart_h * (1.0 - frac))
            painter.drawLine(left_margin, y, w - right_margin, y)

        # ── max-value label ───────────────────────────────────────────
        small_font = QFont()
        small_font.setPixelSize(9)
        painter.setFont(small_font)
        painter.setPen(QColor(self._text_muted))
        painter.drawText(
            QRect(left_margin, 2, 60, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{max_val} min",
        )

        # ── bars ──────────────────────────────────────────────────────
        bar_count = len(self._data)
        total_bar_space = chart_w
        bar_spacing = total_bar_space / bar_count
        bar_width = int(bar_spacing * 0.55)
        bar_radius = 4

        label_font = QFont()
        label_font.setPixelSize(11)
        value_font = QFont()
        value_font.setPixelSize(9)
        value_font.setWeight(QFont.Weight.Medium)

        for i, (label, value, is_today) in enumerate(self._data):
            cx = int(left_margin + bar_spacing * (i + 0.5))
            bar_x = cx - bar_width // 2

            bar_h = int((value / max_val) * chart_h) if value > 0 else 0
            bar_y = top_margin + chart_h - bar_h

            if bar_h > 0:
                # Glow behind today's bar
                if is_today and bar_h > 2:
                    glow_color = QColor(self._accent2)
                    glow_color.setAlpha(40)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(glow_color)
                    glow_extra = 4
                    painter.drawRoundedRect(
                        bar_x - glow_extra,
                        bar_y - glow_extra,
                        bar_width + glow_extra * 2,
                        bar_h + glow_extra,
                        bar_radius + 2, bar_radius + 2,
                    )

                # Main bar
                color = QColor(self._accent2 if is_today else self._accent)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawRoundedRect(
                    bar_x, bar_y, bar_width, bar_h,
                    bar_radius, bar_radius,
                )

                # Value label above bar
                painter.setPen(QColor(self._text_muted))
                painter.setFont(value_font)
                painter.drawText(
                    QRect(bar_x - 10, bar_y - 16, bar_width + 20, 14),
                    Qt.AlignmentFlag.AlignCenter,
                    str(value),
                )

            # Day label below
            painter.setPen(
                QColor(self._text_color if is_today else self._text_muted)
            )
            painter.setFont(label_font)
            lbl_y = top_margin + chart_h + 4
            painter.drawText(
                QRect(cx - 20, lbl_y, 40, 20),
                Qt.AlignmentFlag.AlignCenter,
                label,
            )

        painter.end()


# ═══════════════════════════════════════════════════════════════════════════
#  MONTHLY HEATMAP
# ═══════════════════════════════════════════════════════════════════════════


class MonthlyHeatmap(QWidget):
    """GitHub-style 30-day contribution grid with hover tooltips."""

    CELL_SIZE = 18
    CELL_GAP = 3
    COLS = 6
    ROWS = 5

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: list[dict] = []
        self._accent = "#CBA6F7"
        self._bg_secondary = "#2A2A3E"
        self._text_muted = "#6C7086"
        self.setMouseTracking(True)

        total_w = self.COLS * (self.CELL_SIZE + self.CELL_GAP) - self.CELL_GAP
        total_h = self.ROWS * (self.CELL_SIZE + self.CELL_GAP) - self.CELL_GAP
        self.setMinimumSize(total_w + 4, total_h + 4)

    def set_data(self, data: list[dict]) -> None:
        """data: list of {date, sessions, minutes, xp} for 30 days."""
        self._data = data
        self.update()

    def set_colors(
        self, accent: str, bg_secondary: str, text_muted: str,
    ) -> None:
        self._accent = accent
        self._bg_secondary = bg_secondary
        self._text_muted = text_muted
        self.update()

    def _cell_rect(self, index: int) -> QRectF:
        """Return the rect for cell at the given index (0 = oldest)."""
        col = index % self.COLS
        row = index // self.COLS
        x = 2 + col * (self.CELL_SIZE + self.CELL_GAP)
        y = 2 + row * (self.CELL_SIZE + self.CELL_GAP)
        return QRectF(x, y, self.CELL_SIZE, self.CELL_SIZE)

    def _cell_at(self, pos) -> int | None:
        """Return cell index at the given QPoint, or None."""
        for i in range(min(len(self._data), self.COLS * self.ROWS)):
            if self._cell_rect(i).contains(QPointF(pos.x(), pos.y())):
                return i
        return None

    def _intensity(self, minutes: int) -> float:
        """Map focus minutes to 0.0–1.0 intensity."""
        if minutes <= 0:
            return 0.0
        if minutes <= 30:
            return 0.3
        if minutes <= 60:
            return 0.6
        return 1.0

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        idx = self._cell_at(event.pos())
        if idx is not None and idx < len(self._data):
            d = self._data[idx]
            date_str = d["date"].strftime("%b %d")
            tip = (
                f"{date_str}: {d['sessions']} sessions, "
                f"{d['minutes']} min, {d['xp']} XP"
            )
            QToolTip.showText(event.globalPosition().toPoint(), tip, self)
        else:
            QToolTip.hideText()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        accent = QColor(self._accent)
        bg = QColor(self._bg_secondary)
        radius = 3

        count = min(len(self._data), self.COLS * self.ROWS)
        for i in range(count):
            rect = self._cell_rect(i)
            minutes = self._data[i]["minutes"]
            intensity = self._intensity(minutes)

            if intensity <= 0:
                color = bg
            else:
                color = QColor(accent)
                color.setAlphaF(intensity)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(rect, radius, radius)

        # Draw empty cells for remaining slots
        for i in range(count, self.COLS * self.ROWS):
            rect = self._cell_rect(i)
            painter.setBrush(bg)
            painter.drawRoundedRect(rect, radius, radius)

        painter.end()


# ═══════════════════════════════════════════════════════════════════════════
#  LEVEL ROADMAP
# ═══════════════════════════════════════════════════════════════════════════


class _LevelRoadmap(QWidget):
    """Horizontal track showing current level and upcoming unlocks."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._level = 1
        self._teasers: list[UnlockableItem] = []
        self._next_unlock: UnlockableItem | None = None
        self._accent = "#CBA6F7"
        self._accent2 = "#B4BEFE"
        self._bg_secondary = "#2A2A3E"
        self._text_color = "#E2E2F0"
        self._text_muted = "#6C7086"
        self.setMinimumHeight(72)

    def set_data(
        self,
        current_level: int,
        teasers: list[UnlockableItem],
        next_unlock: UnlockableItem | None = None,
    ) -> None:
        self._level = current_level
        self._teasers = teasers
        self._next_unlock = next_unlock
        self.update()

    def set_colors(
        self,
        accent: str,
        accent2: str,
        bg_secondary: str,
        text: str,
        text_muted: str,
    ) -> None:
        self._accent = accent
        self._accent2 = accent2
        self._bg_secondary = bg_secondary
        self._text_color = text
        self._text_muted = text_muted
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        margin_x = 24
        track_y = 24
        track_w = w - margin_x * 2

        if not self._teasers and self._next_unlock is None:
            # All unlocked — show congratulations
            painter.setPen(QColor(self._text_muted))
            font = QFont()
            font.setPixelSize(12)
            painter.setFont(font)
            painter.drawText(
                QRect(0, 0, w, h),
                Qt.AlignmentFlag.AlignCenter,
                "All unlocks earned! You've mastered everything.",
            )
            painter.end()
            return

        # Determine level range for the roadmap
        all_levels = [self._level] + [t.required_level for t in self._teasers]
        min_lv = self._level
        max_lv = max(all_levels) if all_levels else self._level + 10
        level_range = max(max_lv - min_lv, 1)

        def lv_to_x(lv: int) -> int:
            frac = (lv - min_lv) / level_range
            return int(margin_x + frac * track_w)

        # Track line
        track_pen = QPen(QColor(self._bg_secondary), 3)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.drawLine(margin_x, track_y, margin_x + track_w, track_y)

        # Filled portion up to current level
        filled_pen = QPen(QColor(self._accent), 3)
        filled_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(filled_pen)
        current_x = lv_to_x(self._level)
        painter.drawLine(margin_x, track_y, current_x, track_y)

        # Current level dot
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._accent))
        painter.drawEllipse(QPointF(current_x, track_y), 6, 6)

        # Current level label
        font = QFont()
        font.setPixelSize(9)
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor(self._text_color))
        painter.drawText(
            QRect(current_x - 20, track_y - 18, 40, 14),
            Qt.AlignmentFlag.AlignCenter,
            f"Lv.{self._level}",
        )

        # Teaser dots + labels
        label_font = QFont()
        label_font.setPixelSize(9)
        painter.setFont(label_font)

        for teaser in self._teasers:
            tx = lv_to_x(teaser.required_level)
            # Dot
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self._text_muted))
            painter.drawEllipse(QPointF(tx, track_y), 4, 4)

            # Label below
            type_icon = "\u2b50" if teaser.unlock_type == "theme" else "\u2728"
            label = f"{type_icon} Lv.{teaser.required_level}"
            painter.setPen(QColor(self._text_muted))
            painter.drawText(
                QRect(tx - 28, track_y + 10, 56, 14),
                Qt.AlignmentFlag.AlignCenter,
                label,
            )

            # Name below level
            painter.drawText(
                QRect(tx - 34, track_y + 24, 68, 14),
                Qt.AlignmentFlag.AlignCenter,
                teaser.name,
            )

        # Teaser text at bottom
        if self._next_unlock:
            levels_away = self._next_unlock.required_level - self._level
            type_name = self._next_unlock.unlock_type
            name = self._next_unlock.name
            msg = f"{levels_away} more level{'s' if levels_away != 1 else ''} until {name} {type_name}!"

            msg_font = QFont()
            msg_font.setPixelSize(11)
            msg_font.setWeight(QFont.Weight.Medium)
            painter.setFont(msg_font)
            painter.setPen(QColor(self._accent2))
            painter.drawText(
                QRect(0, h - 18, w, 16),
                Qt.AlignmentFlag.AlignCenter,
                msg,
            )

        painter.end()


# ═══════════════════════════════════════════════════════════════════════════
#  STAT CARD
# ═══════════════════════════════════════════════════════════════════════════


class StatCard(QFrame):
    """A small stat display card with optional icon prefix."""

    def __init__(
        self,
        title: str,
        value: str = "0",
        icon: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)

        self._icon = icon

        self._value_lbl = QLabel(f"{icon} {value}".strip() if icon else value, self)
        self._value_lbl.setObjectName("levelLabel")
        self._value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value_lbl.setStyleSheet("font-size: 18px; font-weight: 700;")

        self._title_lbl = QLabel(title, self)
        self._title_lbl.setObjectName("xpLabel")
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_lbl.setStyleSheet("font-size: 11px;")

        layout.addWidget(self._value_lbl)
        layout.addWidget(self._title_lbl)

    def set_value(self, value: str) -> None:
        text = f"{self._icon} {value}".strip() if self._icon else value
        self._value_lbl.setText(text)


# ═══════════════════════════════════════════════════════════════════════════
#  STATS WIDGET — main dashboard
# ═══════════════════════════════════════════════════════════════════════════


class StatsWidget(QWidget):
    """Stats tab: Today's Summary, Weekly Chart, Heatmap, All-Time, Level."""

    SESSION_TARGET = 6  # daily session goal for the ring

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette: dict[str, str] = {}
        self._cache: _StatsCache | None = None
        self._build_ui()
        # Defer initial refresh so the window appears before the DB queries run
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self.refresh)

    # ── build UI ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # ── [1] Today's Summary ───────────────────────────────────────
        today_card = QFrame(container)
        today_card.setObjectName("card")
        today_layout = QHBoxLayout(today_card)
        today_layout.setContentsMargins(20, 16, 20, 16)
        today_layout.setSpacing(16)

        self._session_ring = _SessionRing(today_card)
        today_layout.addWidget(self._session_ring)

        stats_col = QVBoxLayout()
        stats_col.setSpacing(6)

        self._today_header = QLabel("Today", today_card)
        self._today_header.setStyleSheet(
            "font-size: 16px; font-weight: 700;"
        )
        stats_col.addWidget(self._today_header)

        mini_row = QHBoxLayout()
        mini_row.setSpacing(16)

        self._today_minutes_lbl = QLabel("0 min", today_card)
        self._today_minutes_lbl.setObjectName("xpLabel")
        self._today_minutes_lbl.setStyleSheet("font-size: 13px;")

        self._today_xp_lbl = QLabel("0 XP", today_card)
        self._today_xp_lbl.setObjectName("xpLabel")
        self._today_xp_lbl.setStyleSheet("font-size: 13px;")

        self._streak_lbl = QLabel("0 days", today_card)
        self._streak_lbl.setObjectName("streakLabel")
        self._streak_lbl.setStyleSheet("font-size: 13px;")

        mini_row.addWidget(self._today_minutes_lbl)
        mini_row.addWidget(self._today_xp_lbl)
        mini_row.addWidget(self._streak_lbl)
        mini_row.addStretch()

        stats_col.addLayout(mini_row)
        today_layout.addLayout(stats_col, 1)

        layout.addWidget(today_card)

        # ── [2] Weekly Chart ──────────────────────────────────────────
        chart_card = QFrame(container)
        chart_card.setObjectName("card")
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(20, 16, 20, 12)
        chart_layout.setSpacing(8)

        chart_header_row = QHBoxLayout()
        chart_title = QLabel("This Week", chart_card)
        chart_title.setStyleSheet("font-size: 14px; font-weight: 600;")
        self._weekly_total_lbl = QLabel("", chart_card)
        self._weekly_total_lbl.setObjectName("xpLabel")
        self._weekly_total_lbl.setStyleSheet("font-size: 12px;")
        self._weekly_total_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        chart_header_row.addWidget(chart_title)
        chart_header_row.addStretch()
        chart_header_row.addWidget(self._weekly_total_lbl)
        chart_layout.addLayout(chart_header_row)

        self._chart = WeeklyBarChart(chart_card)
        chart_layout.addWidget(self._chart)

        layout.addWidget(chart_card)

        # ── [3] Monthly Heatmap ───────────────────────────────────────
        heat_card = QFrame(container)
        heat_card.setObjectName("card")
        heat_layout = QVBoxLayout(heat_card)
        heat_layout.setContentsMargins(20, 16, 20, 16)
        heat_layout.setSpacing(10)

        heat_title = QLabel("Last 30 Days", heat_card)
        heat_title.setStyleSheet("font-size: 14px; font-weight: 600;")
        heat_layout.addWidget(heat_title)

        self._heatmap = MonthlyHeatmap(heat_card)
        heat_layout.addWidget(self._heatmap)

        layout.addWidget(heat_card)

        # ── [4] All-Time Stats ────────────────────────────────────────
        alltime_card = QFrame(container)
        alltime_card.setObjectName("card")
        alltime_layout = QVBoxLayout(alltime_card)
        alltime_layout.setContentsMargins(20, 16, 20, 16)
        alltime_layout.setSpacing(12)

        alltime_title = QLabel("All Time", alltime_card)
        alltime_title.setStyleSheet("font-size: 14px; font-weight: 600;")
        alltime_layout.addWidget(alltime_title)

        grid = QGridLayout()
        grid.setSpacing(8)

        self._card_sessions = StatCard("Sessions", "0", "", alltime_card)
        self._card_hours = StatCard("Focus Time", "0m", "", alltime_card)
        self._card_streak = StatCard("Best Streak", "0 days", "", alltime_card)
        self._card_total_xp = StatCard("Total XP", "0", "", alltime_card)
        self._card_fav_time = StatCard("Favorite Time", "\u2014", "", alltime_card)
        self._card_avg_day = StatCard("Avg / Day", "0", "", alltime_card)

        grid.addWidget(self._card_sessions, 0, 0)
        grid.addWidget(self._card_hours, 0, 1)
        grid.addWidget(self._card_streak, 0, 2)
        grid.addWidget(self._card_total_xp, 1, 0)
        grid.addWidget(self._card_fav_time, 1, 1)
        grid.addWidget(self._card_avg_day, 1, 2)
        alltime_layout.addLayout(grid)

        layout.addWidget(alltime_card)

        # ── [5] Level Progress ────────────────────────────────────────
        level_card = QFrame(container)
        level_card.setObjectName("card")
        level_layout = QVBoxLayout(level_card)
        level_layout.setContentsMargins(20, 16, 20, 16)
        level_layout.setSpacing(8)

        level_header_row = QHBoxLayout()
        self._level_lbl = QLabel("Level 1", level_card)
        self._level_lbl.setStyleSheet("font-size: 16px; font-weight: 700;")
        self._level_title_lbl = QLabel("Focus Apprentice", level_card)
        self._level_title_lbl.setObjectName("xpLabel")
        self._level_title_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        level_header_row.addWidget(self._level_lbl)
        level_header_row.addStretch()
        level_header_row.addWidget(self._level_title_lbl)
        level_layout.addLayout(level_header_row)

        self._xp_bar = QProgressBar(level_card)
        self._xp_bar.setRange(0, 100)
        self._xp_bar.setValue(0)
        self._xp_bar.setTextVisible(False)
        self._xp_bar.setFixedHeight(8)
        level_layout.addWidget(self._xp_bar)

        self._xp_lbl = QLabel("0 / 200 XP", level_card)
        self._xp_lbl.setObjectName("xpLabel")
        self._xp_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._xp_lbl.setStyleSheet("font-size: 11px;")
        level_layout.addWidget(self._xp_lbl)

        self._roadmap = _LevelRoadmap(level_card)
        level_layout.addWidget(self._roadmap)

        layout.addWidget(level_card)

        layout.addStretch()

    # ── refresh ───────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Pull fresh data from the DB and update all widgets."""
        cache = _load_stats()
        self._cache = cache

        # [1] Today's Summary
        self._session_ring.set_data(cache.today_sessions, self.SESSION_TARGET)
        self._today_minutes_lbl.setText(f"\u23f1 {cache.today_minutes} min")
        self._today_xp_lbl.setText(f"\u2726 {cache.today_xp} XP")
        if cache.streak > 0:
            self._streak_lbl.setText(f"\U0001f525 {cache.streak} day{'s' if cache.streak != 1 else ''}")
        else:
            self._streak_lbl.setText("")

        # [2] Weekly Chart
        self._chart.set_data(cache.weekly)
        self._weekly_total_lbl.setText(
            f"{_format_focus_hours(cache.weekly_total_minutes)} total"
        )

        # [3] Monthly Heatmap
        self._heatmap.set_data(cache.monthly)

        # [4] All-Time Stats
        self._card_sessions.set_value(str(cache.total_sessions))
        self._card_hours.set_value(_format_focus_hours(cache.total_minutes))
        if cache.longest_streak > 0:
            self._card_streak.set_value(
                f"{cache.longest_streak} day{'s' if cache.longest_streak != 1 else ''}"
            )
        else:
            self._card_streak.set_value("Start today!")
        self._card_total_xp.set_value(f"{cache.total_xp:,}")
        self._card_fav_time.set_value(_format_hour(cache.favorite_hour))
        self._card_avg_day.set_value(str(cache.avg_sessions_per_day))

        # [5] Level Progress
        self._level_lbl.setText(f"Level {cache.level}")
        self._level_title_lbl.setText(cache.title)
        pct = (
            int((cache.earned_in_level / cache.needed_for_level) * 100)
            if cache.needed_for_level > 0 else 100
        )
        self._xp_bar.setValue(pct)
        self._xp_lbl.setText(
            f"{cache.earned_in_level:,} / {cache.needed_for_level:,} XP"
        )
        self._roadmap.set_data(cache.level, cache.teasers, cache.next_unlock)

    # ── theming ───────────────────────────────────────────────────────────

    def apply_palette(self, palette: dict[str, str]) -> None:
        """Re-color all charts and inline-styled labels."""
        self._palette = palette
        accent = palette.get("accent", "#CBA6F7")
        accent2 = palette.get("accent2", "#B4BEFE")
        bg = palette.get("bg", "#1A1A2E")
        bg_secondary = palette.get("bg_secondary", "#2A2A3E")
        text = palette.get("text", "#E2E2F0")
        text_muted = palette.get("text_muted", "#6C7086")
        border = palette.get("border", "#3A3A4E")

        self._session_ring.set_colors(accent, border, text)

        self._chart.set_colors(
            accent=accent, accent2=accent2, bg=bg,
            text=text, text_muted=text_muted, border=border,
        )

        self._heatmap.set_colors(
            accent=accent, bg_secondary=bg_secondary, text_muted=text_muted,
        )

        self._roadmap.set_colors(
            accent=accent, accent2=accent2, bg_secondary=bg_secondary,
            text=text, text_muted=text_muted,
        )
