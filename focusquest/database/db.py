"""Database connection and session management."""

from pathlib import Path
from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session as OrmSession

from .models import Base, UserProgress

# ── paths ────────────────────────────────────────────────────────────────────

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "FocusQuest"
DB_PATH = APP_SUPPORT_DIR / "focusquest.db"

# ── engine & session factory (created lazily) ─────────────────────────────

_engine = None
_SessionFactory = None


def _get_engine():
    global _engine
    if _engine is None:
        APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{DB_PATH}",
            connect_args={"check_same_thread": False},
            echo=False,
        )
    return _engine


def _get_session_factory():
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=_get_engine(), expire_on_commit=False)
    return _SessionFactory


# ── public API ────────────────────────────────────────────────────────────


def configure_engine(url: str) -> None:
    """Override the database connection URL.  Used by tests to point at
    an in-memory SQLite database instead of the real one on disk."""
    global _engine, _SessionFactory
    _SessionFactory = None
    _engine = create_engine(
        url,
        connect_args={"check_same_thread": False},
        echo=False,
    )


def _run_migrations(engine) -> None:
    """Schema migrations for existing databases.

    Runs after ``create_all`` so new columns exist in fresh installs.
    Each migration is idempotent — safe to run repeatedly.
    """
    insp = inspect(engine)
    table_names = set(insp.get_table_names())

    with engine.connect() as conn:
        # ── M1: add xp_awarded column to sessions ──────────────────────
        if "sessions" in table_names:
            columns = {c["name"] for c in insp.get_columns("sessions")}
            if "xp_awarded" not in columns:
                conn.execute(text(
                    "ALTER TABLE sessions "
                    "ADD COLUMN xp_awarded BOOLEAN NOT NULL DEFAULT 0"
                ))

        # ── M2: rename character → companion in unlocks ────────────────
        if "unlocks" in table_names:
            conn.execute(text(
                "UPDATE unlocks SET unlock_type = 'companion' "
                "WHERE unlock_type = 'character'"
            ))

            # Rename old theme keys to new ones
            _theme_renames = {
                "default": "midnight",
                "ocean_breeze": "ocean",
                "dark_forest": "forest",
                "sunset_fire": "sunset",
                "midnight_pro": "neon",
            }
            for old_key, new_key in _theme_renames.items():
                conn.execute(text(
                    "UPDATE unlocks SET unlock_key = :new "
                    "WHERE unlock_type = 'theme' AND unlock_key = :old"
                ), {"old": old_key, "new": new_key})

            # Rename old companion keys
            _companion_renames = {
                "apprentice": "sprout",
                "scholar": "ember",
                "warrior": "ripple",
                "mage": "pixel",
                "legend": "zen",
            }
            for old_key, new_key in _companion_renames.items():
                conn.execute(text(
                    "UPDATE unlocks SET unlock_key = :new "
                    "WHERE unlock_type = 'companion' AND unlock_key = :old"
                ), {"old": old_key, "new": new_key})

        conn.commit()


def init_db() -> None:
    """Create all tables, run migrations, and seed defaults."""
    engine = _get_engine()
    Base.metadata.create_all(engine)
    _run_migrations(engine)

    # Seed default UserProgress row
    factory = _get_session_factory()
    with factory() as session:
        if session.query(UserProgress).count() == 0:
            session.add(UserProgress())
            session.commit()


@contextmanager
def get_session():
    """Yield a SQLAlchemy session; commit on success, rollback on error."""
    factory = _get_session_factory()
    session: OrmSession = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
