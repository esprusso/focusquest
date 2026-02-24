"""Comprehensive tests for the FocusQuest XP and leveling system.

Covers: base XP by duration, streak bonus, daily kickoff, cycle bonus,
leveling curve, level titles, idempotency guard, persistence,
break sessions, signal emissions, and integration with the timer engine.
"""

import pytest
from datetime import date, timedelta

from focusquest.database.db import get_session
from focusquest.database.models import (
    UserProgress, DailyStats, Session as PomSession,
)
from focusquest.gamification.xp import (
    XPEngine,
    xp_for_level,
    level_for_xp,
    xp_to_next_level,
    xp_in_current_level,
    title_for_level,
    _xp_delta,
    BASE_XP_PER_LEVEL,
    LEVEL_SCALING,
)
from focusquest.timer.engine import TimerEngine, TimerState, SessionType

from helpers import SignalCollector, complete_session


# ── helpers ──────────────────────────────────────────────────────────────

def _make_xp_engine(qapp):
    return XPEngine(parent=None)


def _award_work(xp_engine, **kwargs):
    """Award a standard work session with sensible defaults."""
    defaults = dict(
        session_type="work",
        duration_minutes=25,
        task_label="",
        round_number=1,
        rounds_per_cycle=4,
        was_micro=False,
        session_date=date.today(),
        db_session_id=None,
    )
    defaults.update(kwargs)
    return xp_engine.award_session(**defaults)


# ═══════════════════════════════════════════════════════════════════════════
#  LEVELING CURVE
# ═══════════════════════════════════════════════════════════════════════════


class TestLevelingCurve:

    def test_xp_for_level_1_is_zero(self):
        assert xp_for_level(1) == 0

    def test_xp_for_level_2(self):
        """Level 1→2 costs 200 XP."""
        assert xp_for_level(2) == 200

    def test_xp_delta_level_1(self):
        assert _xp_delta(1) == 200

    def test_xp_delta_level_2(self):
        """15% more than level 1."""
        assert _xp_delta(2) == round(200 * LEVEL_SCALING)

    def test_xp_delta_increases_each_level(self):
        """Each level delta should be strictly more than the last."""
        for lvl in range(1, 50):
            assert _xp_delta(lvl + 1) > _xp_delta(lvl)

    def test_xp_for_level_3(self):
        expected = _xp_delta(1) + _xp_delta(2)
        assert xp_for_level(3) == expected

    def test_xp_for_level_5(self):
        expected = sum(_xp_delta(l) for l in range(1, 5))
        assert xp_for_level(5) == expected

    def test_level_for_xp_zero(self):
        assert level_for_xp(0) == 1

    def test_level_for_xp_at_boundary(self):
        """Exactly enough XP to reach level 2."""
        assert level_for_xp(200) == 2

    def test_level_for_xp_just_below_boundary(self):
        assert level_for_xp(199) == 1

    def test_level_for_xp_high(self):
        """Large XP should produce a high level."""
        assert level_for_xp(100_000) > 20

    def test_xp_to_next_level(self):
        assert xp_to_next_level(0) == 200  # need 200 to reach level 2
        assert xp_to_next_level(100) == 100

    def test_xp_in_current_level(self):
        earned, needed = xp_in_current_level(0)
        assert earned == 0
        assert needed == 200

    def test_xp_in_current_level_mid(self):
        earned, needed = xp_in_current_level(100)
        assert earned == 100
        assert needed == 200

    def test_xp_in_current_level_at_level_2(self):
        earned, needed = xp_in_current_level(200)
        assert earned == 0
        assert needed == _xp_delta(2)

    def test_roundtrip_level(self):
        """Computing level from XP and back should be consistent."""
        for total_xp in [0, 100, 200, 500, 1000, 5000, 50000]:
            level = level_for_xp(total_xp)
            assert xp_for_level(level) <= total_xp
            assert xp_for_level(level + 1) > total_xp


# ═══════════════════════════════════════════════════════════════════════════
#  LEVEL TITLES
# ═══════════════════════════════════════════════════════════════════════════


class TestLevelTitles:

    def test_level_1_title(self):
        assert title_for_level(1) == "Focus Apprentice"

    def test_level_4_title(self):
        assert title_for_level(4) == "Focus Apprentice"

    def test_level_5_title(self):
        assert title_for_level(5) == "Concentration Adept"

    def test_level_10_title(self):
        assert title_for_level(10) == "Flow State Warrior"

    def test_level_15_title(self):
        assert title_for_level(15) == "Deep Work Sage"

    def test_level_20_title(self):
        assert title_for_level(20) == "Pomodoro Master"

    def test_level_25_title(self):
        assert title_for_level(25) == "Time Bender"

    def test_level_30_title(self):
        assert title_for_level(30) == "Legendary Focuser"

    def test_level_99_title(self):
        assert title_for_level(99) == "Legendary Focuser"


# ═══════════════════════════════════════════════════════════════════════════
#  BASE XP BY DURATION
# ═══════════════════════════════════════════════════════════════════════════


class TestBaseXPByDuration:

    def test_25_min_session(self, qapp):
        xp = _make_xp_engine(qapp)
        result = _award_work(xp, duration_minutes=25)
        # First session → base + daily kickoff (streak is 0)
        assert result["xp_earned"] == 100 + 50

    def test_15_min_session(self, qapp):
        xp = _make_xp_engine(qapp)
        result = _award_work(xp, duration_minutes=15)
        assert result["xp_earned"] == 65 + 50

    def test_10_min_session(self, qapp):
        xp = _make_xp_engine(qapp)
        result = _award_work(xp, duration_minutes=10)
        assert result["xp_earned"] == 40 + 50

    def test_12_min_session_gives_10_min_rate(self, qapp):
        xp = _make_xp_engine(qapp)
        result = _award_work(xp, duration_minutes=12)
        assert result["xp_earned"] == 40 + 50

    def test_30_min_extended_gives_25_rate(self, qapp):
        xp = _make_xp_engine(qapp)
        result = _award_work(xp, duration_minutes=30)
        assert result["xp_earned"] == 100 + 50

    def test_5_min_session_gives_10_min_rate(self, qapp):
        """Even tiny durations get the lowest bucket."""
        xp = _make_xp_engine(qapp)
        result = _award_work(xp, duration_minutes=5)
        assert result["xp_earned"] == 40 + 50


# ═══════════════════════════════════════════════════════════════════════════
#  STREAK BONUS
# ═══════════════════════════════════════════════════════════════════════════


class TestStreakBonus:

    def test_zero_streak_no_bonus(self, qapp):
        xp = _make_xp_engine(qapp)
        result = _award_work(xp)
        bonuses = {b["name"]: b["amount"] for b in result["bonuses"]}
        assert "Streak" not in " ".join(bonuses.keys())

    def test_5_day_streak_bonus(self, qapp):
        with get_session() as db:
            p = db.query(UserProgress).first()
            p.current_streak_days = 5
        xp = _make_xp_engine(qapp)
        result = _award_work(xp)
        bonuses = {b["name"]: b["amount"] for b in result["bonuses"]}
        assert bonuses["Streak x5"] == 50

    def test_streak_cap_at_100(self, qapp):
        with get_session() as db:
            p = db.query(UserProgress).first()
            p.current_streak_days = 20
        xp = _make_xp_engine(qapp)
        result = _award_work(xp)
        bonuses = {b["name"]: b["amount"] for b in result["bonuses"]}
        assert bonuses["Streak x20"] == 100  # capped

    def test_streak_cap_at_exactly_10(self, qapp):
        with get_session() as db:
            p = db.query(UserProgress).first()
            p.current_streak_days = 10
        xp = _make_xp_engine(qapp)
        result = _award_work(xp)
        bonuses = {b["name"]: b["amount"] for b in result["bonuses"]}
        assert bonuses["Streak x10"] == 100


# ═══════════════════════════════════════════════════════════════════════════
#  DAILY KICKOFF BONUS
# ═══════════════════════════════════════════════════════════════════════════


class TestDailyKickoff:

    def test_first_session_gets_kickoff(self, qapp):
        xp = _make_xp_engine(qapp)
        result = _award_work(xp)
        bonuses = {b["name"]: b["amount"] for b in result["bonuses"]}
        assert bonuses["Daily Kickoff"] == 50

    def test_second_session_no_kickoff(self, qapp):
        xp = _make_xp_engine(qapp)
        _award_work(xp)  # first

        result = _award_work(xp)  # second
        bonus_names = [b["name"] for b in result["bonuses"]]
        assert "Daily Kickoff" not in bonus_names

    def test_kickoff_resets_next_day(self, qapp):
        xp = _make_xp_engine(qapp)
        today = date.today()
        tomorrow = today + timedelta(days=1)

        _award_work(xp, session_date=today)  # first today

        result = _award_work(xp, session_date=tomorrow)  # first tomorrow
        bonuses = {b["name"]: b["amount"] for b in result["bonuses"]}
        assert bonuses["Daily Kickoff"] == 50


# ═══════════════════════════════════════════════════════════════════════════
#  FULL CYCLE BONUS
# ═══════════════════════════════════════════════════════════════════════════


class TestCycleBonus:

    def test_round_4_gets_cycle_bonus(self, qapp):
        xp = _make_xp_engine(qapp)
        result = _award_work(xp, round_number=4, rounds_per_cycle=4)
        bonuses = {b["name"]: b["amount"] for b in result["bonuses"]}
        assert bonuses["Full Cycle!"] == 150

    def test_round_3_no_cycle_bonus(self, qapp):
        xp = _make_xp_engine(qapp)
        result = _award_work(xp, round_number=3, rounds_per_cycle=4)
        bonus_names = [b["name"] for b in result["bonuses"]]
        assert "Full Cycle!" not in bonus_names

    def test_round_1_no_cycle_bonus(self, qapp):
        xp = _make_xp_engine(qapp)
        result = _award_work(xp, round_number=1)
        bonus_names = [b["name"] for b in result["bonuses"]]
        assert "Full Cycle!" not in bonus_names


# ═══════════════════════════════════════════════════════════════════════════
#  COMBINED XP CALCULATION
# ═══════════════════════════════════════════════════════════════════════════


class TestCombinedXP:

    def test_all_bonuses_stack(self, qapp):
        """25-min + 5-day streak + daily kickoff + cycle bonus."""
        with get_session() as db:
            p = db.query(UserProgress).first()
            p.current_streak_days = 5

        xp = _make_xp_engine(qapp)
        result = _award_work(
            xp, duration_minutes=25, round_number=4,
        )
        # 100 (base) + 50 (streak x5) + 50 (kickoff) + 150 (cycle)
        assert result["xp_earned"] == 350

    def test_micro_10_with_kickoff(self, qapp):
        xp = _make_xp_engine(qapp)
        result = _award_work(xp, duration_minutes=10)
        # 40 (base) + 50 (kickoff)
        assert result["xp_earned"] == 90


# ═══════════════════════════════════════════════════════════════════════════
#  BREAK SESSIONS
# ═══════════════════════════════════════════════════════════════════════════


class TestBreakSessions:

    def test_short_break_earns_zero(self, qapp):
        xp = _make_xp_engine(qapp)
        result = xp.award_session(session_type="short_break", duration_minutes=5)
        assert result["xp_earned"] == 0

    def test_long_break_earns_zero(self, qapp):
        xp = _make_xp_engine(qapp)
        result = xp.award_session(session_type="long_break", duration_minutes=15)
        assert result["xp_earned"] == 0


# ═══════════════════════════════════════════════════════════════════════════
#  IDEMPOTENCY
# ═══════════════════════════════════════════════════════════════════════════


class TestIdempotency:

    def test_double_award_with_session_id(self, qapp):
        """Calling award_session twice with the same DB ID doesn't double-count."""
        # Create a completed session record
        from datetime import datetime
        with get_session() as db:
            pom = PomSession(
                start_time=datetime.now(),
                end_time=datetime.now(),
                duration_seconds=1500,
                session_type="work",
                completed=True,
            )
            db.add(pom)
            db.flush()
            session_id = pom.id

        xp = _make_xp_engine(qapp)
        r1 = _award_work(xp, db_session_id=session_id)
        r2 = _award_work(xp, db_session_id=session_id)

        assert r1["xp_earned"] > 0
        assert r2["xp_earned"] == 0  # idempotent — no double-count

    def test_without_session_id_no_guard(self, qapp):
        """Without a DB session ID, each call awards XP independently."""
        xp = _make_xp_engine(qapp)
        r1 = _award_work(xp)
        r2 = _award_work(xp)
        assert r1["xp_earned"] > 0
        assert r2["xp_earned"] > 0


# ═══════════════════════════════════════════════════════════════════════════
#  PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════


class TestPersistence:

    def test_user_progress_updated(self, qapp):
        xp = _make_xp_engine(qapp)
        result = _award_work(xp, duration_minutes=25)

        with get_session() as db:
            p = db.query(UserProgress).first()
            assert p.total_xp == result["xp_earned"]
            assert p.total_sessions_completed == 1
            assert p.total_focus_minutes == 25

    def test_daily_stats_created(self, qapp):
        xp = _make_xp_engine(qapp)
        _award_work(xp, session_date=date.today())

        with get_session() as db:
            daily = db.query(DailyStats).filter_by(date=date.today()).first()
            assert daily is not None
            assert daily.sessions_completed == 1
            assert daily.focus_minutes == 25
            assert daily.xp_earned > 0

    def test_daily_stats_accumulates(self, qapp):
        xp = _make_xp_engine(qapp)
        _award_work(xp, session_date=date.today())
        _award_work(xp, session_date=date.today())

        with get_session() as db:
            daily = db.query(DailyStats).filter_by(date=date.today()).first()
            assert daily.sessions_completed == 2

    def test_task_label_increments_tasks_completed(self, qapp):
        xp = _make_xp_engine(qapp)
        _award_work(xp, task_label="My Task")

        with get_session() as db:
            daily = db.query(DailyStats).filter_by(date=date.today()).first()
            assert daily.tasks_completed == 1

    def test_no_task_label_doesnt_increment(self, qapp):
        xp = _make_xp_engine(qapp)
        _award_work(xp, task_label="")

        with get_session() as db:
            daily = db.query(DailyStats).filter_by(date=date.today()).first()
            assert daily.tasks_completed == 0

    def test_xp_awarded_flag_set_on_session(self, qapp):
        from datetime import datetime
        with get_session() as db:
            pom = PomSession(
                start_time=datetime.now(),
                end_time=datetime.now(),
                duration_seconds=1500,
                session_type="work",
                completed=True,
            )
            db.add(pom)
            db.flush()
            session_id = pom.id

        xp = _make_xp_engine(qapp)
        _award_work(xp, db_session_id=session_id)

        with get_session() as db:
            pom = db.get(PomSession, session_id)
            assert pom.xp_awarded is True


# ═══════════════════════════════════════════════════════════════════════════
#  LEVELING UP
# ═══════════════════════════════════════════════════════════════════════════


class TestLevelUp:

    def test_level_up_detected(self, qapp):
        """Give enough XP to cross the level 1→2 boundary."""
        with get_session() as db:
            p = db.query(UserProgress).first()
            p.total_xp = 190  # need 200 to hit level 2

        xp = _make_xp_engine(qapp)
        # 25-min = 100 base. No streak. But kickoff still applies?
        # Actually, streak is 0, kickoff = 50. So 150 total.
        # 190 + 150 = 340, which > 200 → level up
        result = _award_work(xp)
        assert result["level_up"] is True
        assert result["new_level"] == 2
        assert result["old_level"] == 1

    def test_no_level_up_when_not_enough(self, qapp):
        xp = _make_xp_engine(qapp)
        # Start at 0. First session = 100+50=150. Need 200 for level 2.
        result = _award_work(xp)
        assert result["level_up"] is False
        assert result["new_level"] == 1

    def test_level_up_returns_title(self, qapp):
        with get_session() as db:
            p = db.query(UserProgress).first()
            p.total_xp = 190

        xp = _make_xp_engine(qapp)
        result = _award_work(xp)
        assert result["new_title"] == "Focus Apprentice"  # still 1-4 range


# ═══════════════════════════════════════════════════════════════════════════
#  SIGNALS
# ═══════════════════════════════════════════════════════════════════════════


class TestSignals:

    def test_xp_awarded_signal_emitted(self, qapp):
        xp = _make_xp_engine(qapp)
        c = SignalCollector()
        xp.xp_awarded.connect(c)

        _award_work(xp)

        assert len(c) == 1
        data = c.last
        assert data["amount"] > 0
        assert "bonuses" in data
        assert isinstance(data["bonuses"], list)

    def test_xp_awarded_signal_not_emitted_for_breaks(self, qapp):
        xp = _make_xp_engine(qapp)
        c = SignalCollector()
        xp.xp_awarded.connect(c)

        xp.award_session(session_type="short_break", duration_minutes=5)
        assert len(c) == 0

    def test_level_up_signal_emitted(self, qapp):
        with get_session() as db:
            p = db.query(UserProgress).first()
            p.total_xp = 190

        xp = _make_xp_engine(qapp)
        c = SignalCollector()
        xp.level_up.connect(c)

        _award_work(xp)

        assert len(c) == 1
        data = c.last
        assert data["new_level"] == 2
        assert data["old_level"] == 1
        assert "new_title" in data

    def test_level_up_signal_not_emitted_without_level_change(self, qapp):
        xp = _make_xp_engine(qapp)
        c = SignalCollector()
        xp.level_up.connect(c)

        _award_work(xp)  # 150 XP, need 200 to level up
        assert len(c) == 0

    def test_xp_awarded_data_includes_total_and_level(self, qapp):
        xp = _make_xp_engine(qapp)
        c = SignalCollector()
        xp.xp_awarded.connect(c)

        _award_work(xp)
        data = c.last
        assert "total_xp" in data
        assert "level" in data
        assert "title" in data
        assert data["level"] == 1
        assert data["title"] == "Focus Apprentice"


# ═══════════════════════════════════════════════════════════════════════════
#  ENGINE INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════


class TestEngineIntegration:
    """Verify the session_completed signal carries all fields the XP
    engine needs, and that an end-to-end flow works."""

    def test_session_completed_has_db_session_id(self, engine):
        c = SignalCollector()
        engine.session_completed.connect(c)

        engine.start()
        complete_session(engine)

        data = c.last
        assert "db_session_id" in data
        assert data["db_session_id"] is not None

    def test_session_completed_has_rounds_per_cycle(self, engine):
        c = SignalCollector()
        engine.session_completed.connect(c)

        engine.start()
        complete_session(engine)

        data = c.last
        assert "rounds_per_cycle" in data
        assert data["rounds_per_cycle"] == 4

    def test_end_to_end_xp_award(self, engine):
        """Complete a work session → feed data to XPEngine → verify."""
        c = SignalCollector()
        engine.session_completed.connect(c)

        engine.start()
        complete_session(engine)

        data = c.last
        xp = XPEngine(parent=None)
        result = xp.award_session(
            session_type=data["session_type"],
            duration_minutes=data["duration_seconds"] // 60,
            task_label=data.get("task_label", "") or "",
            round_number=data.get("round_number", 1),
            rounds_per_cycle=data.get("rounds_per_cycle", 4),
            was_micro=data.get("was_micro", False),
            session_date=data["end_time"].date(),
            db_session_id=data.get("db_session_id"),
        )
        assert result["xp_earned"] > 0

        # Verify idempotency — second call returns 0
        result2 = xp.award_session(
            session_type=data["session_type"],
            duration_minutes=data["duration_seconds"] // 60,
            session_date=data["end_time"].date(),
            db_session_id=data.get("db_session_id"),
        )
        assert result2["xp_earned"] == 0

    def test_break_session_no_xp(self, engine):
        """Complete work then break — break should give 0 XP."""
        engine.start()
        complete_session(engine)  # work done
        engine.start()  # short break

        c = SignalCollector()
        engine.session_completed.connect(c)
        complete_session(engine)

        data = c.last
        xp = XPEngine(parent=None)
        result = xp.award_session(
            session_type=data["session_type"],
            duration_minutes=data["duration_seconds"] // 60,
        )
        assert result["xp_earned"] == 0
