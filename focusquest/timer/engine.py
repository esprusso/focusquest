"""Timer state machine for FocusQuest.

States
------
IDLE          Not running — waiting for user to start.
WORKING       Work timer counting down.
SHORT_BREAK   Short break timer counting down.
LONG_BREAK    Long break timer counting down.
PAUSED        Timer frozen (remembers what it was doing before).

Transitions
-----------
IDLE → WORKING | SHORT_BREAK | LONG_BREAK  (start)
WORKING → PAUSED                            (pause)
SHORT_BREAK → PAUSED                        (pause)
LONG_BREAK → PAUSED                         (pause)
PAUSED → {whatever was paused}              (resume)
{running} → IDLE or next session            (timer reaches 0)
Any → IDLE                                  (reset / skip)

ADHD-friendly design choices
-----------------------------
- Pausing is safe — no XP penalty, no streak harm.
- ``extend(seconds)`` lets you ride a flow state (+5 min default).
- ``start_micro(minutes)`` for "I can't do 25 min right now" days.
"""

from __future__ import annotations

from datetime import datetime, date
from enum import Enum, auto

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


# ── enums ─────────────────────────────────────────────────────────────────


class TimerState(Enum):
    IDLE = "idle"
    WORKING = "working"
    SHORT_BREAK = "short_break"
    LONG_BREAK = "long_break"
    PAUSED = "paused"


class SessionType(Enum):
    WORK = "work"
    SHORT_BREAK = "short_break"
    LONG_BREAK = "long_break"


# ── constants ─────────────────────────────────────────────────────────────

DEFAULT_DURATIONS: dict[SessionType, int] = {
    SessionType.WORK: 25 * 60,
    SessionType.SHORT_BREAK: 5 * 60,
    SessionType.LONG_BREAK: 15 * 60,
}

ROUNDS_PER_CYCLE = 4
EXTEND_SECONDS = 5 * 60  # +5 min flow-state extension
MICRO_PRESETS = (10, 15)  # minutes

_SESSION_TO_TIMER_STATE: dict[SessionType, TimerState] = {
    SessionType.WORK: TimerState.WORKING,
    SessionType.SHORT_BREAK: TimerState.SHORT_BREAK,
    SessionType.LONG_BREAK: TimerState.LONG_BREAK,
}


# ── engine ────────────────────────────────────────────────────────────────


class TimerEngine(QObject):
    """Qt-based Pomodoro timer with full state machine, DB logging,
    streak tracking, and ADHD-friendly controls.

    Signals
    -------
    tick(remaining_seconds: int)
        Emitted every second while a session is running.
    state_changed(new_state: TimerState)
        Emitted on every state transition.
    session_completed(data: dict)
        Emitted after a session finishes naturally.  Keys:
        ``session_type``, ``duration_seconds``, ``start_time``,
        ``end_time``, ``task_label``, ``round_number``, ``was_micro``,
        ``extensions``.
    streak_updated(current_streak: int, longest_streak: int)
        Emitted after a work session updates the daily streak.
    """

    tick = pyqtSignal(int)
    state_changed = pyqtSignal(object)
    session_completed = pyqtSignal(object)
    streak_updated = pyqtSignal(int, int)
    break_ending_soon = pyqtSignal()  # fires once at 60s during breaks

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        db_enabled: bool = True,
        auto_advance: bool = False,
    ) -> None:
        super().__init__(parent)

        # ── configuration ─────────────────────────────────────────────
        self._durations: dict[SessionType, int] = dict(DEFAULT_DURATIONS)
        self._rounds_per_cycle: int = ROUNDS_PER_CYCLE
        self._auto_advance: bool = auto_advance
        self._db_enabled: bool = db_enabled

        # ── cycle / session state ─────────────────────────────────────
        self._state: TimerState = TimerState.IDLE
        self._paused_from: TimerState | None = None
        self._session_type: SessionType = SessionType.WORK
        self._round: int = 1  # 1-indexed; which work session in cycle

        # ── countdown state ───────────────────────────────────────────
        self._remaining: int = self._durations[SessionType.WORK]
        self._session_duration: int = self._remaining  # grows with extend()
        self._start_time: datetime | None = None
        self._task_label: str = ""
        self._is_micro: bool = False
        self._extensions: int = 0

        # ── DB tracking ───────────────────────────────────────────────
        self._db_session_id: int | None = None

        # ── break warning ────────────────────────────────────────────
        self._break_warning_fired: bool = False

        # ── Qt timer ──────────────────────────────────────────────────
        self._qt_timer = QTimer(self)
        self._qt_timer.setInterval(1000)
        self._qt_timer.timeout.connect(self._on_tick)

    # ══════════════════════════════════════════════════════════════════
    #  PUBLIC PROPERTIES
    # ══════════════════════════════════════════════════════════════════

    @property
    def state(self) -> TimerState:
        return self._state

    @property
    def session_type(self) -> SessionType:
        """The session type currently active (or next, when IDLE)."""
        return self._session_type

    @property
    def remaining(self) -> int:
        """Seconds left on the clock."""
        return self._remaining

    @property
    def total_duration(self) -> int:
        """Total seconds for this session (including extensions)."""
        return self._session_duration

    @property
    def percent_complete(self) -> float:
        """0.0 → 1.0 progress through the current session."""
        if self._session_duration <= 0:
            return 0.0
        elapsed = self._session_duration - self._remaining
        return max(0.0, min(1.0, elapsed / self._session_duration))

    @property
    def current_round(self) -> int:
        """Which work session in the cycle (1-based)."""
        return self._round

    @property
    def rounds_per_cycle(self) -> int:
        return self._rounds_per_cycle

    @property
    def is_running(self) -> bool:
        """True when actively counting down (not IDLE, not PAUSED)."""
        return self._state in (
            TimerState.WORKING,
            TimerState.SHORT_BREAK,
            TimerState.LONG_BREAK,
        )

    @property
    def task_label(self) -> str:
        return self._task_label

    @task_label.setter
    def task_label(self, value: str) -> None:
        self._task_label = value

    @property
    def auto_advance(self) -> bool:
        return self._auto_advance

    @auto_advance.setter
    def auto_advance(self, value: bool) -> None:
        self._auto_advance = value

    def duration_for(self, session_type: SessionType) -> int:
        return self._durations[session_type]

    def set_duration(self, session_type: SessionType, seconds: int) -> None:
        """Override a default duration (minimum 60 s)."""
        self._durations[session_type] = max(60, seconds)
        if self._state == TimerState.IDLE and self._session_type == session_type:
            self._remaining = self._durations[session_type]
            self._session_duration = self._remaining

    # ══════════════════════════════════════════════════════════════════
    #  CONTROLS
    # ══════════════════════════════════════════════════════════════════

    def start(self) -> None:
        """Begin the next session.  Only valid from IDLE."""
        if self._state != TimerState.IDLE:
            return
        self._begin_session(
            self._session_type,
            self._durations[self._session_type],
        )

    def start_micro(self, minutes: int = 10) -> None:
        """Start a shorter work session for low-energy moments.

        Only valid from IDLE.  The micro flag is recorded in the
        ``session_completed`` signal data.
        """
        if self._state != TimerState.IDLE:
            return
        self._is_micro = True
        self._session_type = SessionType.WORK
        self._begin_session(SessionType.WORK, minutes * 60)

    def pause(self) -> None:
        """Pause.  Safe — no XP penalty, no streak harm."""
        if not self.is_running:
            return
        self._qt_timer.stop()
        self._paused_from = self._state
        self._set_state(TimerState.PAUSED)

    def resume(self) -> None:
        """Resume from PAUSED back to whatever was running."""
        if self._state != TimerState.PAUSED or self._paused_from is None:
            return
        restore_to = self._paused_from
        self._paused_from = None
        self._set_state(restore_to)
        self._qt_timer.start()

    def reset(self) -> None:
        """Cancel the current session and return to IDLE (unsaved)."""
        self._qt_timer.stop()
        self._paused_from = None
        self._db_session_id = None  # don't complete—user cancelled
        self._start_time = None
        self._is_micro = False
        self._extensions = 0
        self._remaining = self._durations[self._session_type]
        self._session_duration = self._remaining
        self._set_state(TimerState.IDLE)

    def skip(self) -> None:
        """Advance to the next session type without completing.

        Works from any state (IDLE too — e.g. skip an upcoming break).
        """
        self._qt_timer.stop()
        self._paused_from = None
        self._db_session_id = None
        self._start_time = None
        self._is_micro = False
        self._extensions = 0
        self._advance()
        self._remaining = self._durations[self._session_type]
        self._session_duration = self._remaining
        # Always emit so UI picks up the new session_type even if
        # we were already IDLE.
        self._state = TimerState.IDLE
        self.state_changed.emit(TimerState.IDLE)

    def extend(self, seconds: int = EXTEND_SECONDS) -> None:
        """Add time to the running (or paused-from-work) session.

        The "+5 more minutes" button for flow state.  Only works for
        work sessions.
        """
        active = self._state
        if self._state == TimerState.PAUSED and self._paused_from:
            active = self._paused_from
        if active != TimerState.WORKING:
            return

        self._remaining += seconds
        self._session_duration += seconds
        self._extensions += 1
        self.tick.emit(self._remaining)

    # ══════════════════════════════════════════════════════════════════
    #  INTERNAL — timer mechanics
    # ══════════════════════════════════════════════════════════════════

    def _begin_session(
        self, session_type: SessionType, duration: int
    ) -> None:
        self._session_type = session_type
        self._remaining = duration
        self._session_duration = duration
        self._start_time = datetime.now()
        self._extensions = 0
        self._break_warning_fired = False

        if self._db_enabled:
            self._persist_start()

        self._set_state(_SESSION_TO_TIMER_STATE[session_type])
        self._qt_timer.start()

    def _on_tick(self) -> None:
        self._remaining = max(0, self._remaining - 1)
        self.tick.emit(self._remaining)

        # Break ending warning — fires once at 60 s remaining during breaks
        if (
            not self._break_warning_fired
            and self._state in (TimerState.SHORT_BREAK, TimerState.LONG_BREAK)
            and 0 < self._remaining <= 60
        ):
            self._break_warning_fired = True
            self.break_ending_soon.emit()

        if self._remaining <= 0:
            self._finish_session()

    def _finish_session(self) -> None:
        self._qt_timer.stop()
        end_time = datetime.now()
        completed_type = self._session_type
        completed_round = self._round
        completed_db_id = self._db_session_id  # capture before persist clears it

        # ── persist completion ────────────────────────────────────────
        if self._db_enabled:
            self._persist_completed(end_time)

        # ── emit session data ─────────────────────────────────────────
        self.session_completed.emit({
            "session_type": completed_type.value,
            "duration_seconds": self._session_duration,
            "start_time": self._start_time,
            "end_time": end_time,
            "task_label": self._task_label,
            "round_number": completed_round,
            "rounds_per_cycle": self._rounds_per_cycle,
            "was_micro": self._is_micro,
            "extensions": self._extensions,
            "db_session_id": completed_db_id,
        })

        # ── streak (work sessions only) ───────────────────────────────
        if completed_type == SessionType.WORK and self._db_enabled:
            current, longest = self._update_streak(end_time.date())
            self.streak_updated.emit(current, longest)

        # ── advance cycle ─────────────────────────────────────────────
        self._advance()
        self._is_micro = False
        self._extensions = 0
        self._remaining = self._durations[self._session_type]
        self._session_duration = self._remaining

        # ── auto-advance or wait for click ────────────────────────────
        if self._auto_advance:
            self._start_time = datetime.now()
            if self._db_enabled:
                self._persist_start()
            self._set_state(_SESSION_TO_TIMER_STATE[self._session_type])
            self._qt_timer.start()
        else:
            self._start_time = None
            self._db_session_id = None
            self._set_state(TimerState.IDLE)

    def _advance(self) -> None:
        """Move ``session_type`` and ``round`` to the next position."""
        if self._session_type == SessionType.WORK:
            # After work → break
            if self._round >= self._rounds_per_cycle:
                self._session_type = SessionType.LONG_BREAK
            else:
                self._session_type = SessionType.SHORT_BREAK
        else:
            # After any break → work
            if self._session_type == SessionType.LONG_BREAK:
                self._round = 1
            else:
                self._round += 1
            self._session_type = SessionType.WORK

    def _set_state(self, new_state: TimerState) -> None:
        self._state = new_state
        self.state_changed.emit(new_state)

    # ══════════════════════════════════════════════════════════════════
    #  INTERNAL — database persistence
    # ══════════════════════════════════════════════════════════════════

    def _persist_start(self) -> None:
        from ..database.db import get_session
        from ..database.models import Session as PomSession

        with get_session() as db:
            record = PomSession(
                start_time=self._start_time,
                session_type=self._session_type.value,
                completed=False,
                task_label=self._task_label or None,
            )
            db.add(record)
            db.flush()
            self._db_session_id = record.id

    def _persist_completed(self, end_time: datetime) -> None:
        if self._db_session_id is None:
            return
        from ..database.db import get_session
        from ..database.models import Session as PomSession

        with get_session() as db:
            record = db.get(PomSession, self._db_session_id)
            if record:
                record.end_time = end_time
                record.duration_seconds = self._session_duration
                record.completed = True
        self._db_session_id = None

    def _update_streak(self, session_date: date) -> tuple[int, int]:
        from ..database.db import get_session
        from ..database.models import UserProgress

        with get_session() as db:
            progress: UserProgress = db.query(UserProgress).first()
            if progress is None:
                return (0, 0)

            last = progress.last_session_date
            if last is None:
                progress.current_streak_days = 1
            elif (session_date - last).days == 1:
                progress.current_streak_days += 1
            elif (session_date - last).days == 0:
                pass  # same calendar day — no change
            else:
                progress.current_streak_days = 1  # streak broken

            progress.last_session_date = session_date
            if progress.current_streak_days > progress.longest_streak_days:
                progress.longest_streak_days = progress.current_streak_days

            return (progress.current_streak_days, progress.longest_streak_days)
