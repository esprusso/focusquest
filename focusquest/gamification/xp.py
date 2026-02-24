"""XP and leveling logic for FocusQuest — the core dopamine loop.

XP Awards
---------
- 25-min pomodoro:            100 XP
- 15-min session:              65 XP
- 10-min session:              40 XP
- Full cycle (4 pomodoros):  +150 XP bonus
- Daily streak:               streak_days x 10 XP per session (cap 100)
- First session of the day:  +50 XP  ("Daily Kickoff")
- Breaks:                      0 XP

Leveling Curve
--------------
Level 1->2: 200 XP.  Each subsequent level requires 15% more XP than
the previous.  The formula is stored in :func:`_xp_delta` so it's
trivial to re-tune.

Level Titles
------------
Every 5 levels earns a new title:
    1-4  Focus Apprentice
    5-9  Concentration Adept
   10-14 Flow State Warrior
   15-19 Deep Work Sage
   20-24 Pomodoro Master
   25-29 Time Bender
   30+   Legendary Focuser

XP Event System
---------------
``XPEngine`` is a :class:`QObject` that emits two signals:

* **xp_awarded(data)** — amount, reason string, bonuses breakdown
* **level_up(data)**   — new level, new title, unlocks earned

Persistence
-----------
``award_session`` updates both ``UserProgress`` and ``DailyStats``.
It is idempotent: a ``db_session_id`` guard prevents double-counting
if an event is replayed.
"""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QObject, pyqtSignal

from ..database.db import get_session
from ..database.models import UserProgress, DailyStats, Session as PomSession


# ── leveling constants (easy to adjust) ──────────────────────────────────

BASE_XP_PER_LEVEL = 200   # XP to go from level 1 → 2
LEVEL_SCALING = 1.15       # each level needs 15% more than the last


# ── level math ───────────────────────────────────────────────────────────


def _xp_delta(level: int) -> int:
    """XP needed to go from *level* to *level + 1*.

    This is the single knob that controls the leveling curve.
    """
    return round(BASE_XP_PER_LEVEL * (LEVEL_SCALING ** (level - 1)))


def xp_for_level(level: int) -> int:
    """Total cumulative XP required to *reach* the given level.

    ``xp_for_level(1)`` is 0 (you start at level 1 with zero XP).
    """
    if level <= 1:
        return 0
    return sum(_xp_delta(l) for l in range(1, level))


def level_for_xp(total_xp: int) -> int:
    """Return the level a player is at given their total XP."""
    level = 1
    while xp_for_level(level + 1) <= total_xp:
        level += 1
    return level


def xp_to_next_level(total_xp: int) -> int:
    """XP still needed to reach the next level."""
    current = level_for_xp(total_xp)
    return xp_for_level(current + 1) - total_xp


def xp_in_current_level(total_xp: int) -> tuple[int, int]:
    """Return ``(earned_in_level, needed_for_level)``."""
    level = level_for_xp(total_xp)
    floor = xp_for_level(level)
    ceiling = xp_for_level(level + 1)
    return total_xp - floor, ceiling - floor


# ── level titles ─────────────────────────────────────────────────────────

# Ordered descending so the first match wins.
LEVEL_TITLES: list[tuple[int, str]] = [
    (30, "Legendary Focuser"),
    (25, "Time Bender"),
    (20, "Pomodoro Master"),
    (15, "Deep Work Sage"),
    (10, "Flow State Warrior"),
    (5,  "Concentration Adept"),
    (1,  "Focus Apprentice"),
]


def title_for_level(level: int) -> str:
    """Return the fun title for *level*."""
    for threshold, title in LEVEL_TITLES:
        if level >= threshold:
            return title
    return "Focus Apprentice"


# ── XP engine ────────────────────────────────────────────────────────────


class XPEngine(QObject):
    """Handles XP awards, leveling, and persistence.

    Signals
    -------
    xp_awarded(data: dict)
        Emitted after every XP award.  Keys:
        ``amount``, ``reason`` (str), ``bonuses`` (list of dicts),
        ``total_xp``, ``level``, ``title``.
    level_up(data: dict)
        Emitted when the player reaches a new level.  Keys:
        ``old_level``, ``new_level``, ``new_title``,
        ``unlocks_earned`` (list — filled later by the app layer).
    """

    xp_awarded = pyqtSignal(object)
    level_up = pyqtSignal(object)

    # ── award constants (easy to tweak) ──────────────────────────────────
    XP_25_MIN = 100
    XP_15_MIN = 65
    XP_10_MIN = 40

    XP_CYCLE_BONUS = 150        # completing all 4 rounds
    XP_DAILY_KICKOFF = 50       # first work session of the day
    XP_STREAK_PER_DAY = 10
    XP_STREAK_CAP = 100

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

    # ── helpers ──────────────────────────────────────────────────────────

    def _base_xp_for_duration(self, duration_minutes: int) -> int:
        """Map session duration to the base XP award."""
        if duration_minutes >= 25:
            return self.XP_25_MIN
        elif duration_minutes >= 15:
            return self.XP_15_MIN
        else:
            return self.XP_10_MIN

    # ── main entry point ─────────────────────────────────────────────────

    def award_session(
        self,
        *,
        session_type: str,
        duration_minutes: int = 25,
        task_label: str = "",
        round_number: int = 1,
        rounds_per_cycle: int = 4,
        was_micro: bool = False,
        session_date: date | None = None,
        db_session_id: int | None = None,
    ) -> dict:
        """Award XP for a completed session and update persistence.

        **Idempotent**: if *db_session_id* is provided and XP was already
        awarded for that session row, returns immediately with
        ``xp_earned=0``.

        Returns a dict with ``xp_earned``, ``level_up``, ``new_level``,
        ``old_level``, ``new_title``, and ``bonuses``.
        """
        if session_date is None:
            session_date = date.today()

        _empty = {
            "xp_earned": 0,
            "level_up": False,
            "new_level": 1,
            "old_level": 1,
            "new_title": title_for_level(1),
            "bonuses": [],
        }

        # Breaks earn nothing — breaks are their own reward.
        if session_type != "work":
            return _empty

        with get_session() as db:
            # ── idempotency guard ────────────────────────────────────
            if db_session_id is not None:
                pom = db.get(PomSession, db_session_id)
                if pom is not None and pom.xp_awarded:
                    return _empty
                if pom is not None:
                    pom.xp_awarded = True

            progress: UserProgress = db.query(UserProgress).first()
            bonuses: list[dict[str, object]] = []

            # ── 1. base XP by duration ───────────────────────────────
            base = self._base_xp_for_duration(duration_minutes)
            bonuses.append({"name": "Session", "amount": base})
            xp = base

            # ── 2. daily streak bonus ────────────────────────────────
            streak = progress.current_streak_days
            streak_bonus = min(
                streak * self.XP_STREAK_PER_DAY, self.XP_STREAK_CAP,
            )
            if streak_bonus > 0:
                bonuses.append({
                    "name": f"Streak x{streak}",
                    "amount": streak_bonus,
                })
                xp += streak_bonus

            # ── 3. first session of the day ("Daily Kickoff") ────────
            daily = (
                db.query(DailyStats)
                .filter_by(date=session_date)
                .first()
            )
            is_first_today = daily is None or daily.sessions_completed == 0
            if is_first_today:
                bonuses.append({
                    "name": "Daily Kickoff",
                    "amount": self.XP_DAILY_KICKOFF,
                })
                xp += self.XP_DAILY_KICKOFF

            # ── 4. full cycle bonus (4th pomodoro) ───────────────────
            if round_number >= rounds_per_cycle:
                bonuses.append({
                    "name": "Full Cycle!",
                    "amount": self.XP_CYCLE_BONUS,
                })
                xp += self.XP_CYCLE_BONUS

            # ── apply to user progress ───────────────────────────────
            old_level = progress.current_level
            progress.total_xp += xp
            progress.current_level = level_for_xp(progress.total_xp)
            progress.total_sessions_completed += 1
            progress.total_focus_minutes += duration_minutes

            leveled_up = progress.current_level > old_level
            new_title = title_for_level(progress.current_level)

            # ── update daily stats ───────────────────────────────────
            if daily is None:
                daily = DailyStats(
                    date=session_date,
                    sessions_completed=0,
                    focus_minutes=0,
                    xp_earned=0,
                    tasks_completed=0,
                )
                db.add(daily)
            daily.sessions_completed += 1
            daily.focus_minutes += duration_minutes
            daily.xp_earned += xp
            if task_label.strip():
                daily.tasks_completed += 1

            db.commit()

            # ── emit signals ─────────────────────────────────────────
            self.xp_awarded.emit({
                "amount": xp,
                "reason": f"+{xp} XP",
                "bonuses": bonuses,
                "total_xp": progress.total_xp,
                "level": progress.current_level,
                "title": new_title,
            })

            if leveled_up:
                self.level_up.emit({
                    "old_level": old_level,
                    "new_level": progress.current_level,
                    "new_title": new_title,
                    "unlocks_earned": [],  # filled by app after checking
                })

            return {
                "xp_earned": xp,
                "level_up": leveled_up,
                "new_level": progress.current_level,
                "old_level": old_level,
                "new_title": new_title,
                "bonuses": bonuses,
            }
