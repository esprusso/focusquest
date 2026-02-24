"""Comprehensive tests for the FocusQuest timer engine.

Covers: state transitions, round/cycle tracking, DB session logging,
streak calculation across days, extend-timer, micro sessions, skip,
pause/resume safety, and auto-advance mode.
"""

import pytest
from datetime import date, timedelta

from focusquest.database.db import get_session
from focusquest.database.models import Session as PomSession, UserProgress
from focusquest.timer.engine import (
    TimerEngine, TimerState, SessionType,
    EXTEND_SECONDS, DEFAULT_DURATIONS, ROUNDS_PER_CYCLE,
)

from helpers import SignalCollector, complete_session


# ═══════════════════════════════════════════════════════════════════════════
#  STATE TRANSITIONS
# ═══════════════════════════════════════════════════════════════════════════


class TestStateTransitions:

    def test_initial_state_is_idle(self, engine):
        assert engine.state == TimerState.IDLE
        assert engine.session_type == SessionType.WORK
        assert engine.remaining == DEFAULT_DURATIONS[SessionType.WORK]

    def test_start_transitions_to_working(self, engine):
        engine.start()
        assert engine.state == TimerState.WORKING

    def test_pause_transitions_to_paused(self, engine):
        engine.start()
        engine.pause()
        assert engine.state == TimerState.PAUSED

    def test_resume_restores_working(self, engine):
        engine.start()
        engine.pause()
        engine.resume()
        assert engine.state == TimerState.WORKING

    def test_resume_restores_break_state(self, engine):
        """Pausing during a break resumes to the correct break state."""
        engine.start()
        complete_session(engine)
        # Now IDLE with SHORT_BREAK next
        assert engine.session_type == SessionType.SHORT_BREAK

        engine.start()
        assert engine.state == TimerState.SHORT_BREAK

        engine.pause()
        assert engine.state == TimerState.PAUSED

        engine.resume()
        assert engine.state == TimerState.SHORT_BREAK

    def test_reset_goes_to_idle(self, engine):
        engine.start()
        engine._on_tick()  # advance a bit
        engine.reset()
        assert engine.state == TimerState.IDLE
        # Remaining should be reset to full duration
        assert engine.remaining == DEFAULT_DURATIONS[SessionType.WORK]

    def test_start_is_noop_when_already_running(self, engine):
        engine.start()
        remaining_before = engine.remaining
        engine._on_tick()
        engine.start()  # should be noop
        assert engine.state == TimerState.WORKING

    def test_pause_is_noop_when_idle(self, engine):
        engine.pause()
        assert engine.state == TimerState.IDLE

    def test_resume_is_noop_when_not_paused(self, engine):
        engine.start()
        engine.resume()  # already running
        assert engine.state == TimerState.WORKING

    def test_state_changed_signal_fires_on_transitions(self, engine):
        c = SignalCollector()
        engine.state_changed.connect(c)

        engine.start()
        assert c.last == TimerState.WORKING

        engine.pause()
        assert c.last == TimerState.PAUSED

        engine.resume()
        assert c.last == TimerState.WORKING

    def test_completion_transitions_to_idle(self, engine):
        """With auto_advance=False, completing goes to IDLE."""
        engine.start()
        complete_session(engine)
        assert engine.state == TimerState.IDLE

    def test_completion_with_auto_advance(self, engine_auto):
        """With auto_advance=True, completing starts the next session."""
        engine_auto.start()
        complete_session(engine_auto)
        assert engine_auto.state == TimerState.SHORT_BREAK


# ═══════════════════════════════════════════════════════════════════════════
#  TICK / COUNTDOWN
# ═══════════════════════════════════════════════════════════════════════════


class TestCountdown:

    def test_tick_decrements_remaining(self, engine):
        engine.start()
        initial = engine.remaining
        engine._on_tick()
        assert engine.remaining == initial - 1

    def test_tick_signal_emits_remaining(self, engine):
        c = SignalCollector()
        engine.tick.connect(c)

        engine.start()
        engine._on_tick()

        assert len(c) == 1
        assert c.last == engine.remaining

    def test_percent_complete_at_halfway(self, engine):
        engine.set_duration(SessionType.WORK, 100)
        engine.start()
        for _ in range(50):
            engine._on_tick()
        assert engine.percent_complete == pytest.approx(0.5, abs=0.02)

    def test_percent_starts_at_zero(self, engine):
        engine.start()
        assert engine.percent_complete == pytest.approx(0.0, abs=0.01)

    def test_remaining_never_goes_negative(self, engine):
        engine.set_duration(SessionType.WORK, 60)
        engine.start()
        for _ in range(80):
            if engine.state == TimerState.IDLE:
                break
            engine._on_tick()
        # Should have completed; remaining should be the next session's
        assert engine.remaining >= 0


# ═══════════════════════════════════════════════════════════════════════════
#  ROUND TRACKING / CYCLE
# ═══════════════════════════════════════════════════════════════════════════


class TestRoundTracking:

    def test_starts_at_round_1(self, engine):
        assert engine.current_round == 1
        assert engine.rounds_per_cycle == ROUNDS_PER_CYCLE

    def test_full_4_round_cycle(self, engine):
        """Work → short break → work → ... → 4th work → long break → round 1."""
        for r in range(1, 5):
            assert engine.current_round == r
            assert engine.session_type == SessionType.WORK

            # Work session
            engine.start()
            complete_session(engine)

            if r < 4:
                assert engine.session_type == SessionType.SHORT_BREAK
                engine.start()
                complete_session(engine)
            else:
                assert engine.session_type == SessionType.LONG_BREAK
                engine.start()
                complete_session(engine)

        # After full cycle
        assert engine.current_round == 1
        assert engine.session_type == SessionType.WORK

    def test_round_stays_during_break(self, engine):
        """Round number doesn't change until the break completes."""
        engine.start()
        complete_session(engine)  # work done
        # Still round 1 during the break
        assert engine.current_round == 1

    def test_round_increments_after_short_break(self, engine):
        engine.start()
        complete_session(engine)
        engine.start()  # short break
        complete_session(engine)
        assert engine.current_round == 2

    def test_round_resets_after_long_break(self, engine):
        # Fast-forward to round 4
        for _ in range(3):
            engine.start()  # work
            complete_session(engine)
            engine.start()  # short break
            complete_session(engine)

        assert engine.current_round == 4
        engine.start()  # round 4 work
        complete_session(engine)
        assert engine.session_type == SessionType.LONG_BREAK

        engine.start()  # long break
        complete_session(engine)
        assert engine.current_round == 1


# ═══════════════════════════════════════════════════════════════════════════
#  DATABASE SESSION LOGGING
# ═══════════════════════════════════════════════════════════════════════════


class TestDBLogging:

    def test_session_record_created_on_start(self, engine):
        engine.start()
        with get_session() as db:
            sessions = db.query(PomSession).all()
            assert len(sessions) == 1
            assert sessions[0].session_type == "work"
            assert sessions[0].completed is False

    def test_session_marked_complete(self, engine):
        engine.start()
        complete_session(engine)
        with get_session() as db:
            s = db.query(PomSession).first()
            assert s.completed is True
            assert s.end_time is not None
            assert s.duration_seconds == DEFAULT_DURATIONS[SessionType.WORK]

    def test_task_label_persisted(self, engine):
        engine.task_label = "Write tests"
        engine.start()
        complete_session(engine)
        with get_session() as db:
            s = db.query(PomSession).first()
            assert s.task_label == "Write tests"

    def test_break_session_logged(self, engine):
        engine.start()
        complete_session(engine)
        engine.start()  # short break
        complete_session(engine)
        with get_session() as db:
            sessions = db.query(PomSession).all()
            assert len(sessions) == 2
            assert sessions[1].session_type == "short_break"
            assert sessions[1].completed is True

    def test_reset_does_not_complete_session(self, engine):
        engine.start()
        engine.reset()
        with get_session() as db:
            s = db.query(PomSession).first()
            assert s.completed is False

    def test_session_completed_signal_data(self, engine):
        c = SignalCollector()
        engine.session_completed.connect(c)

        engine.task_label = "My task"
        engine.start()
        complete_session(engine)

        data = c.last
        assert data["session_type"] == "work"
        assert data["task_label"] == "My task"
        assert data["round_number"] == 1
        assert data["was_micro"] is False
        assert data["extensions"] == 0
        assert data["start_time"] is not None
        assert data["end_time"] is not None
        assert data["duration_seconds"] == DEFAULT_DURATIONS[SessionType.WORK]

    def test_no_db_writes_when_disabled(self, engine_no_db):
        engine_no_db.start()
        complete_session(engine_no_db)
        with get_session() as db:
            assert db.query(PomSession).count() == 0

    def test_auto_advance_creates_new_session_record(self, engine_auto):
        engine_auto.start()
        complete_session(engine_auto)
        # Auto-advance should create a second record for the break
        with get_session() as db:
            sessions = db.query(PomSession).all()
            assert len(sessions) == 2
            assert sessions[0].completed is True
            assert sessions[0].session_type == "work"
            assert sessions[1].completed is False
            assert sessions[1].session_type == "short_break"


# ═══════════════════════════════════════════════════════════════════════════
#  STREAK CALCULATION
# ═══════════════════════════════════════════════════════════════════════════


class TestStreaks:

    def test_first_session_starts_streak_at_1(self, engine):
        c = SignalCollector()
        engine.streak_updated.connect(c)

        engine.start()
        complete_session(engine)

        current, longest = c.last
        assert current == 1
        assert longest == 1

    def test_same_day_keeps_streak_at_1(self, engine):
        """Multiple sessions on the same day don't inflate the streak."""
        engine.start()
        complete_session(engine)
        engine.start()  # break
        complete_session(engine)
        engine.start()  # second work
        complete_session(engine)

        with get_session() as db:
            p = db.query(UserProgress).first()
            assert p.current_streak_days == 1

    def test_consecutive_days_extend_streak(self, engine):
        """Fake yesterday's session, complete today — streak grows."""
        yesterday = date.today() - timedelta(days=1)
        with get_session() as db:
            p = db.query(UserProgress).first()
            p.last_session_date = yesterday
            p.current_streak_days = 5

        c = SignalCollector()
        engine.streak_updated.connect(c)

        engine.start()
        complete_session(engine)

        current, longest = c.last
        assert current == 6
        assert longest == 6

    def test_gap_breaks_streak(self, engine):
        """A 2+ day gap resets current streak to 1, preserves longest."""
        three_days_ago = date.today() - timedelta(days=3)
        with get_session() as db:
            p = db.query(UserProgress).first()
            p.last_session_date = three_days_ago
            p.current_streak_days = 10
            p.longest_streak_days = 10

        engine.start()
        complete_session(engine)

        with get_session() as db:
            p = db.query(UserProgress).first()
            assert p.current_streak_days == 1
            assert p.longest_streak_days == 10  # preserved

    def test_break_sessions_dont_update_streak(self, engine):
        engine.start()
        complete_session(engine)

        c = SignalCollector()
        engine.streak_updated.connect(c)

        engine.start()  # break
        complete_session(engine)
        assert len(c) == 0  # no streak signal for breaks

    def test_streak_not_emitted_when_db_disabled(self, engine_no_db):
        c = SignalCollector()
        engine_no_db.streak_updated.connect(c)

        engine_no_db.start()
        complete_session(engine_no_db)
        assert len(c) == 0

    def test_longest_streak_updates_when_new_record(self, engine):
        yesterday = date.today() - timedelta(days=1)
        with get_session() as db:
            p = db.query(UserProgress).first()
            p.last_session_date = yesterday
            p.current_streak_days = 3
            p.longest_streak_days = 3

        engine.start()
        complete_session(engine)

        with get_session() as db:
            p = db.query(UserProgress).first()
            assert p.current_streak_days == 4
            assert p.longest_streak_days == 4  # new record


# ═══════════════════════════════════════════════════════════════════════════
#  EXTEND TIMER ("+5 more minutes")
# ═══════════════════════════════════════════════════════════════════════════


class TestExtendTimer:

    def test_extend_adds_time(self, engine):
        engine.start()
        before_remaining = engine.remaining
        before_total = engine.total_duration

        engine.extend(300)

        assert engine.remaining == before_remaining + 300
        assert engine.total_duration == before_total + 300

    def test_extend_default_is_5_minutes(self, engine):
        engine.start()
        before = engine.remaining
        engine.extend()
        assert engine.remaining == before + EXTEND_SECONDS
        assert EXTEND_SECONDS == 300

    def test_extend_increments_counter(self, engine):
        engine.start()
        engine.extend()
        engine.extend()
        assert engine._extensions == 2

    def test_extend_works_while_paused_from_work(self, engine):
        engine.start()
        engine.pause()
        before = engine.remaining

        engine.extend(300)
        assert engine.remaining == before + 300

    def test_extend_noop_during_break(self, engine):
        engine.start()
        complete_session(engine)
        engine.start()  # short break
        before = engine.remaining

        engine.extend(300)
        assert engine.remaining == before  # unchanged

    def test_extend_noop_during_idle(self, engine):
        before = engine.remaining
        engine.extend(300)
        assert engine.remaining == before

    def test_extend_noop_during_paused_break(self, engine):
        engine.start()
        complete_session(engine)
        engine.start()  # short break
        engine.pause()
        before = engine.remaining

        engine.extend(300)
        assert engine.remaining == before

    def test_extended_duration_in_completed_signal(self, engine):
        c = SignalCollector()
        engine.session_completed.connect(c)

        engine.set_duration(SessionType.WORK, 60)
        engine.start()
        engine.extend(300)
        complete_session(engine)

        data = c.last
        assert data["duration_seconds"] == 360
        assert data["extensions"] == 1

    def test_extend_emits_tick(self, engine):
        engine.start()

        c = SignalCollector()
        engine.tick.connect(c)

        engine.extend(300)
        assert len(c) == 1

    def test_percent_recalculates_after_extend(self, engine):
        engine.set_duration(SessionType.WORK, 100)
        engine.start()
        for _ in range(50):
            engine._on_tick()
        # 50 elapsed / 100 total = 50%
        assert engine.percent_complete == pytest.approx(0.5, abs=0.02)

        engine.extend(100)
        # 50 elapsed / 200 total = 25%
        assert engine.percent_complete == pytest.approx(0.25, abs=0.02)

    def test_extended_duration_logged_to_db(self, engine):
        engine.set_duration(SessionType.WORK, 60)
        engine.start()
        engine.extend(300)
        complete_session(engine)

        with get_session() as db:
            s = db.query(PomSession).first()
            assert s.duration_seconds == 360


# ═══════════════════════════════════════════════════════════════════════════
#  MICRO SESSIONS ("I can't do 25 min right now")
# ═══════════════════════════════════════════════════════════════════════════


class TestMicroSession:

    def test_start_micro_10(self, engine):
        engine.start_micro(10)
        assert engine.state == TimerState.WORKING
        assert engine.remaining == 600
        assert engine.total_duration == 600

    def test_start_micro_15(self, engine):
        engine.start_micro(15)
        assert engine.state == TimerState.WORKING
        assert engine.remaining == 900

    def test_micro_flag_in_completed_signal(self, engine):
        c = SignalCollector()
        engine.session_completed.connect(c)

        engine.start_micro(10)
        complete_session(engine)

        assert c.last["was_micro"] is True

    def test_normal_session_not_flagged_micro(self, engine):
        c = SignalCollector()
        engine.session_completed.connect(c)

        engine.start()
        complete_session(engine)
        assert c.last["was_micro"] is False

    def test_micro_counts_toward_round(self, engine):
        """Micro sessions advance the cycle like normal work."""
        engine.start_micro(10)
        complete_session(engine)
        assert engine.session_type == SessionType.SHORT_BREAK

    def test_micro_logged_to_db(self, engine):
        engine.start_micro(10)
        complete_session(engine)

        with get_session() as db:
            s = db.query(PomSession).first()
            assert s.session_type == "work"
            assert s.completed is True
            assert s.duration_seconds == 600

    def test_micro_updates_streak(self, engine):
        c = SignalCollector()
        engine.streak_updated.connect(c)

        engine.start_micro(10)
        complete_session(engine)
        assert len(c) == 1  # streak was updated

    def test_micro_only_from_idle(self, engine):
        engine.start()
        engine.start_micro(10)  # noop because already running
        assert engine.remaining != 600

    def test_micro_overrides_session_type_to_work(self, engine):
        """Even if next session was a break, micro forces WORK."""
        engine.start()
        complete_session(engine)
        assert engine.session_type == SessionType.SHORT_BREAK

        engine.start_micro(10)
        assert engine.state == TimerState.WORKING
        assert engine.session_type == SessionType.WORK

    def test_micro_flag_resets_after_next_session(self, engine):
        """After a micro completes, the next session isn't flagged micro."""
        c = SignalCollector()
        engine.session_completed.connect(c)

        engine.start_micro(10)
        complete_session(engine)
        assert c.last["was_micro"] is True

        engine.start()  # short break
        complete_session(engine)
        assert c.last["was_micro"] is False


# ═══════════════════════════════════════════════════════════════════════════
#  SKIP
# ═══════════════════════════════════════════════════════════════════════════


class TestSkip:

    def test_skip_from_working(self, engine):
        engine.start()
        engine.skip()
        assert engine.state == TimerState.IDLE
        assert engine.session_type == SessionType.SHORT_BREAK

    def test_skip_from_break(self, engine):
        engine.start()
        complete_session(engine)
        engine.start()  # short break
        engine.skip()
        assert engine.state == TimerState.IDLE
        assert engine.session_type == SessionType.WORK

    def test_skip_from_paused(self, engine):
        engine.start()
        engine.pause()
        engine.skip()
        assert engine.state == TimerState.IDLE
        assert engine.session_type == SessionType.SHORT_BREAK

    def test_skip_from_idle(self, engine):
        """Skip from idle advances to the next session type."""
        engine.skip()
        assert engine.state == TimerState.IDLE
        assert engine.session_type == SessionType.SHORT_BREAK

    def test_skip_emits_state_changed(self, engine):
        c = SignalCollector()
        engine.state_changed.connect(c)

        engine.skip()
        assert c.last == TimerState.IDLE

    def test_skip_does_not_emit_session_completed(self, engine):
        c = SignalCollector()
        engine.session_completed.connect(c)

        engine.start()
        engine.skip()
        assert len(c) == 0

    def test_skip_resets_extensions(self, engine):
        engine.start()
        engine.extend()
        engine.skip()
        assert engine._extensions == 0


# ═══════════════════════════════════════════════════════════════════════════
#  PAUSE / RESUME — "pausing is safe"
# ═══════════════════════════════════════════════════════════════════════════


class TestPauseResume:

    def test_pause_preserves_remaining_time(self, engine):
        engine.start()
        for _ in range(10):
            engine._on_tick()
        remaining_at_pause = engine.remaining

        engine.pause()
        assert engine.remaining == remaining_at_pause

    def test_resume_continues_from_where_we_left_off(self, engine):
        engine.start()
        for _ in range(10):
            engine._on_tick()
        remaining_at_pause = engine.remaining

        engine.pause()
        engine.resume()

        # Simulate one more tick
        engine._on_tick()
        assert engine.remaining == remaining_at_pause - 1

    def test_multiple_pause_resume_cycles(self, engine):
        engine.start()
        engine._on_tick()

        for _ in range(5):
            engine.pause()
            assert engine.state == TimerState.PAUSED
            engine.resume()
            assert engine.state == TimerState.WORKING
            engine._on_tick()

        # All those pauses shouldn't have lost any ticks
        # We did 1 + 5 = 6 ticks total
        expected = DEFAULT_DURATIONS[SessionType.WORK] - 6
        assert engine.remaining == expected

    def test_pause_during_break(self, engine):
        engine.start()
        complete_session(engine)
        engine.start()  # short break
        engine.pause()
        assert engine.state == TimerState.PAUSED

        engine.resume()
        assert engine.state == TimerState.SHORT_BREAK


# ═══════════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════


class TestConfiguration:

    def test_set_duration(self, engine):
        engine.set_duration(SessionType.WORK, 10 * 60)
        assert engine.duration_for(SessionType.WORK) == 600
        # When idle, remaining should also update
        assert engine.remaining == 600

    def test_duration_minimum_is_60s(self, engine):
        engine.set_duration(SessionType.WORK, 30)
        assert engine.duration_for(SessionType.WORK) == 60

    def test_auto_advance_toggle(self, engine):
        assert engine.auto_advance is False
        engine.auto_advance = True
        assert engine.auto_advance is True

    def test_is_running_property(self, engine):
        assert engine.is_running is False
        engine.start()
        assert engine.is_running is True
        engine.pause()
        assert engine.is_running is False
        engine.resume()
        assert engine.is_running is True
