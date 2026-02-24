"""Tests for the stats dashboard: data loading, widgets, format helpers.

Covers:
- Format helpers (_format_focus_hours, _format_hour)
- _load_stats data queries (empty DB, populated DB, weekly/monthly)
- Session ring, bar chart, heatmap, level roadmap (paint + set_data)
- StatCard basics
- StatsWidget refresh and apply_palette
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from PyQt6.QtWidgets import QApplication

from focusquest.database.db import get_session
from focusquest.database.models import UserProgress, DailyStats, Session
from focusquest.ui.stats_widget import (
    _format_focus_hours,
    _format_hour,
    _load_stats,
    _StatsCache,
    _SessionRing,
    WeeklyBarChart,
    MonthlyHeatmap,
    _LevelRoadmap,
    StatCard,
    StatsWidget,
)
from focusquest.gamification.unlockables import REGISTRY


# ═══════════════════════════════════════════════════════════════════════
#  FORMAT HELPERS
# ═══════════════════════════════════════════════════════════════════════


class TestFormatFocusHours:
    def test_zero_minutes(self):
        assert _format_focus_hours(0) == "0m"

    def test_negative_minutes(self):
        assert _format_focus_hours(-5) == "0m"

    def test_minutes_only(self):
        assert _format_focus_hours(45) == "45m"

    def test_exact_hour(self):
        assert _format_focus_hours(60) == "1h 0m"

    def test_hours_and_minutes(self):
        assert _format_focus_hours(125) == "2h 5m"

    def test_large_value(self):
        assert _format_focus_hours(600) == "10h 0m"

    def test_one_minute(self):
        assert _format_focus_hours(1) == "1m"


class TestFormatHour:
    def test_none(self):
        assert _format_hour(None) == "\u2014"

    def test_midnight(self):
        assert _format_hour(0) == "12 AM"

    def test_morning(self):
        assert _format_hour(9) == "9 AM"

    def test_noon(self):
        assert _format_hour(12) == "12 PM"

    def test_afternoon(self):
        assert _format_hour(14) == "2 PM"

    def test_eleven_am(self):
        assert _format_hour(11) == "11 AM"

    def test_eleven_pm(self):
        assert _format_hour(23) == "11 PM"


# ═══════════════════════════════════════════════════════════════════════
#  DATA LOADING
# ═══════════════════════════════════════════════════════════════════════


class TestLoadStats:
    """Test _load_stats with various DB states."""

    def test_empty_db_returns_defaults(self):
        cache = _load_stats()
        assert cache.level == 1
        assert cache.total_xp == 0
        assert cache.today_sessions == 0
        assert cache.today_minutes == 0
        assert len(cache.weekly) == 7
        assert len(cache.monthly) == 30
        assert cache.favorite_hour is None
        assert cache.avg_sessions_per_day == 0.0

    def test_weekly_has_7_entries(self):
        cache = _load_stats()
        assert len(cache.weekly) == 7
        # Each entry is (label, value, is_today)
        for label, value, is_today in cache.weekly:
            assert isinstance(label, str)
            assert isinstance(value, int)
            assert isinstance(is_today, bool)

    def test_weekly_last_entry_is_today(self):
        cache = _load_stats()
        # Last entry should be today
        _, _, is_today = cache.weekly[-1]
        assert is_today is True

    def test_weekly_first_6_are_not_today(self):
        cache = _load_stats()
        for _, _, is_today in cache.weekly[:6]:
            assert is_today is False

    def test_monthly_has_30_entries(self):
        cache = _load_stats()
        assert len(cache.monthly) == 30
        # Each entry has required keys
        for entry in cache.monthly:
            assert "date" in entry
            assert "sessions" in entry
            assert "minutes" in entry
            assert "xp" in entry

    def test_monthly_last_entry_is_today(self):
        cache = _load_stats()
        today = date.today()
        assert cache.monthly[-1]["date"] == today

    def test_monthly_first_entry_is_29_days_ago(self):
        cache = _load_stats()
        today = date.today()
        expected = today - timedelta(days=29)
        assert cache.monthly[0]["date"] == expected

    def test_with_user_progress(self):
        with get_session() as db:
            progress = db.query(UserProgress).first()
            progress.total_xp = 500
            progress.current_level = 3
            progress.total_sessions_completed = 10
            progress.total_focus_minutes = 250
            progress.current_streak_days = 3
            progress.longest_streak_days = 7

        cache = _load_stats()
        assert cache.level == 3
        assert cache.total_xp == 500
        assert cache.total_sessions == 10
        assert cache.total_minutes == 250
        assert cache.streak == 3
        assert cache.longest_streak == 7

    def test_with_today_daily_stats(self):
        today = date.today()
        with get_session() as db:
            db.add(DailyStats(
                date=today,
                sessions_completed=4,
                focus_minutes=100,
                xp_earned=420,
            ))

        cache = _load_stats()
        assert cache.today_sessions == 4
        assert cache.today_minutes == 100
        assert cache.today_xp == 420

    def test_weekly_picks_up_daily_stats(self):
        today = date.today()
        yesterday = today - timedelta(days=1)
        with get_session() as db:
            db.add(DailyStats(
                date=today,
                sessions_completed=2,
                focus_minutes=50,
                xp_earned=200,
            ))
            db.add(DailyStats(
                date=yesterday,
                sessions_completed=3,
                focus_minutes=75,
                xp_earned=300,
            ))

        cache = _load_stats()
        # Last entry (today) should have 50 minutes
        assert cache.weekly[-1][1] == 50
        # Second-to-last (yesterday) should have 75
        assert cache.weekly[-2][1] == 75
        assert cache.weekly_total_minutes == 125

    def test_favorite_hour_with_sessions(self):
        with get_session() as db:
            # Add sessions at different hours
            for _ in range(3):
                db.add(Session(
                    start_time=datetime(2025, 1, 15, 14, 0),
                    session_type="work",
                    completed=True,
                    duration_seconds=1500,
                ))
            for _ in range(1):
                db.add(Session(
                    start_time=datetime(2025, 1, 15, 9, 0),
                    session_type="work",
                    completed=True,
                    duration_seconds=1500,
                ))

        cache = _load_stats()
        assert cache.favorite_hour == 14

    def test_avg_sessions_per_day(self):
        today = date.today()
        with get_session() as db:
            progress = db.query(UserProgress).first()
            progress.total_sessions_completed = 12
            # Add 4 active days
            for i in range(4):
                db.add(DailyStats(
                    date=today - timedelta(days=i),
                    sessions_completed=3,
                    focus_minutes=75,
                    xp_earned=300,
                ))

        cache = _load_stats()
        assert cache.avg_sessions_per_day == 3.0  # 12 / 4

    def test_teasers_populated(self):
        cache = _load_stats()
        # At level 1, there should be teasers
        assert len(cache.teasers) > 0
        assert cache.next_unlock is not None

    def test_level_progress_values(self):
        with get_session() as db:
            progress = db.query(UserProgress).first()
            progress.total_xp = 500
            progress.current_level = 3

        cache = _load_stats()
        assert cache.earned_in_level >= 0
        assert cache.needed_for_level > 0
        assert cache.title != ""


# ═══════════════════════════════════════════════════════════════════════
#  SESSION RING WIDGET
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.usefixtures("qapp")
class TestSessionRing:
    def test_create(self):
        w = _SessionRing()
        assert w.width() == 64
        assert w.height() == 64

    def test_set_data(self):
        w = _SessionRing()
        w.set_data(3, 6)
        assert w._completed == 3
        assert w._target == 6

    def test_set_data_zero_target(self):
        w = _SessionRing()
        w.set_data(0, 0)
        assert w._target == 1  # clamped to avoid division by zero

    def test_paint_no_crash(self):
        w = _SessionRing()
        w.set_data(3, 6)
        w.repaint()

    def test_paint_full_ring(self):
        w = _SessionRing()
        w.set_data(6, 6)
        w.repaint()

    def test_paint_over_target(self):
        w = _SessionRing()
        w.set_data(10, 6)
        w.repaint()  # Should not crash (pct clamped to 1.0)


# ═══════════════════════════════════════════════════════════════════════
#  WEEKLY BAR CHART
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.usefixtures("qapp")
class TestWeeklyBarChart:
    def test_create(self):
        w = WeeklyBarChart()
        assert w.minimumHeight() == 180

    def test_set_data_empty(self):
        w = WeeklyBarChart()
        w.set_data([])
        w.repaint()  # No crash

    def test_set_data_normal(self):
        data = [("Mon", 30, False), ("Tue", 45, False), ("Wed", 0, False),
                ("Thu", 60, False), ("Fri", 25, False), ("Sat", 0, False),
                ("Sun", 90, True)]
        w = WeeklyBarChart()
        w.set_data(data)
        w.repaint()

    def test_set_data_all_zeros(self):
        data = [(d, 0, d == "Sun") for d in
                ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]]
        w = WeeklyBarChart()
        w.set_data(data)
        w.repaint()  # No crash with max_val=0

    def test_set_colors(self):
        w = WeeklyBarChart()
        w.set_colors("#FF0000", "#00FF00", "#000000",
                      "#FFFFFF", "#888888", "#333333")
        assert w._accent == "#FF0000"


# ═══════════════════════════════════════════════════════════════════════
#  MONTHLY HEATMAP
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.usefixtures("qapp")
class TestMonthlyHeatmap:
    def test_create(self):
        w = MonthlyHeatmap()
        assert w.hasMouseTracking()

    def test_set_data_empty(self):
        w = MonthlyHeatmap()
        w.set_data([])
        w.repaint()

    def test_set_data_30_days(self):
        today = date.today()
        data = [
            {"date": today - timedelta(days=29 - i),
             "sessions": i % 3, "minutes": i * 10, "xp": i * 40}
            for i in range(30)
        ]
        w = MonthlyHeatmap()
        w.set_data(data)
        w.repaint()

    def test_cell_at_returns_none_outside(self):
        from PyQt6.QtCore import QPoint
        w = MonthlyHeatmap()
        w.set_data([{"date": date.today(), "sessions": 0, "minutes": 0, "xp": 0}])
        result = w._cell_at(QPoint(999, 999))
        assert result is None

    def test_cell_at_returns_index_inside(self):
        from PyQt6.QtCore import QPoint
        today = date.today()
        data = [
            {"date": today - timedelta(days=29 - i),
             "sessions": 1, "minutes": 30, "xp": 100}
            for i in range(30)
        ]
        w = MonthlyHeatmap()
        w.set_data(data)
        # Cell 0 is at approximately (2, 2) to (20, 20)
        result = w._cell_at(QPoint(10, 10))
        assert result == 0

    def test_intensity_buckets(self):
        w = MonthlyHeatmap()
        assert w._intensity(0) == 0.0
        assert w._intensity(15) == 0.3
        assert w._intensity(45) == 0.6
        assert w._intensity(90) == 1.0

    def test_set_colors(self):
        w = MonthlyHeatmap()
        w.set_colors("#FF0000", "#222222", "#888888")
        assert w._accent == "#FF0000"


# ═══════════════════════════════════════════════════════════════════════
#  LEVEL ROADMAP
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.usefixtures("qapp")
class TestLevelRoadmap:
    def test_create(self):
        w = _LevelRoadmap()
        assert w.minimumHeight() == 72

    def test_set_data_no_teasers(self):
        w = _LevelRoadmap()
        w.set_data(30, [], None)
        w.repaint()  # Shows "all unlocked" message

    def test_set_data_with_teasers(self):
        teasers = REGISTRY.teasers(5, count=3)
        next_up = REGISTRY.next_upcoming(5)
        w = _LevelRoadmap()
        w.set_data(5, teasers, next_up)
        w.repaint()

    def test_set_colors(self):
        w = _LevelRoadmap()
        w.set_colors("#AA00FF", "#0088FF", "#222222", "#FFFFFF", "#888888")
        assert w._accent == "#AA00FF"


# ═══════════════════════════════════════════════════════════════════════
#  STAT CARD
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.usefixtures("qapp")
class TestStatCard:
    def test_create(self):
        card = StatCard("Sessions", "42")
        assert card._value_lbl.text() == "42"
        assert card._title_lbl.text() == "Sessions"

    def test_set_value(self):
        card = StatCard("XP", "0")
        card.set_value("1,250")
        assert card._value_lbl.text() == "1,250"

    def test_with_icon(self):
        card = StatCard("Streak", "5", icon="\U0001f525")
        assert "\U0001f525" in card._value_lbl.text()
        assert "5" in card._value_lbl.text()


# ═══════════════════════════════════════════════════════════════════════
#  STATS WIDGET INTEGRATION
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.usefixtures("qapp")
class TestStatsWidget:
    def test_create_and_refresh_empty_db(self):
        w = StatsWidget()
        w.refresh()  # deferred in __init__ via QTimer; call explicitly
        # Should not crash on empty DB
        assert w._cache is not None

    def test_refresh_populates_level(self):
        with get_session() as db:
            progress = db.query(UserProgress).first()
            progress.total_xp = 500
            progress.current_level = 3

        w = StatsWidget()
        w.refresh()
        assert "Level 3" in w._level_lbl.text()

    def test_refresh_populates_today(self):
        today = date.today()
        with get_session() as db:
            db.add(DailyStats(
                date=today,
                sessions_completed=2,
                focus_minutes=50,
                xp_earned=200,
            ))

        w = StatsWidget()
        w.refresh()
        assert w._cache.today_sessions == 2
        assert "50" in w._today_minutes_lbl.text()
        assert "200" in w._today_xp_lbl.text()

    def test_apply_palette(self):
        w = StatsWidget()
        palette = {
            "accent": "#FF0000",
            "accent2": "#00FF00",
            "bg": "#000000",
            "bg_secondary": "#111111",
            "text": "#FFFFFF",
            "text_muted": "#888888",
            "border": "#333333",
        }
        w.apply_palette(palette)
        assert w._chart._accent == "#FF0000"
        assert w._heatmap._accent == "#FF0000"
        assert w._roadmap._accent == "#FF0000"

    def test_session_target_default(self):
        assert StatsWidget.SESSION_TARGET == 6
