"""SQLAlchemy ORM models for FocusQuest."""

from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date, Float
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Session(Base):
    """Tracks each Pomodoro session (work or break)."""

    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    start_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=False, default=0)
    session_type = Column(String(20), nullable=False, default="work")  # work | short_break | long_break
    completed = Column(Boolean, nullable=False, default=False)
    task_label = Column(String(255), nullable=True)
    xp_awarded = Column(Boolean, nullable=False, default=False)

    def __repr__(self) -> str:
        return (
            f"<Session id={self.id} type={self.session_type} "
            f"completed={self.completed}>"
        )


class UserProgress(Base):
    """Single-row table tracking overall user progress."""

    __tablename__ = "user_progress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    total_xp = Column(Integer, nullable=False, default=0)
    current_level = Column(Integer, nullable=False, default=1)
    total_sessions_completed = Column(Integer, nullable=False, default=0)
    total_focus_minutes = Column(Integer, nullable=False, default=0)
    current_streak_days = Column(Integer, nullable=False, default=0)
    longest_streak_days = Column(Integer, nullable=False, default=0)
    last_session_date = Column(Date, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<UserProgress level={self.current_level} "
            f"xp={self.total_xp} streak={self.current_streak_days}>"
        )


class Unlock(Base):
    """Tracks earned unlockables (themes, characters, titles)."""

    __tablename__ = "unlocks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    unlock_type = Column(String(20), nullable=False)   # theme | character | title
    unlock_key = Column(String(64), nullable=False)    # e.g. "dark_forest", "warrior"
    unlocked_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    is_equipped = Column(Boolean, nullable=False, default=False)

    def __repr__(self) -> str:
        return (
            f"<Unlock type={self.unlock_type} key={self.unlock_key} "
            f"equipped={self.is_equipped}>"
        )


class DailyStats(Base):
    """Aggregated per-day stats for quick chart lookups."""

    __tablename__ = "daily_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, unique=True)
    sessions_completed = Column(Integer, nullable=False, default=0)
    focus_minutes = Column(Integer, nullable=False, default=0)
    xp_earned = Column(Integer, nullable=False, default=0)
    tasks_completed = Column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return (
            f"<DailyStats date={self.date} sessions={self.sessions_completed} "
            f"focus={self.focus_minutes}m>"
        )
