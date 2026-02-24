"""Shared pytest fixtures for FocusQuest tests."""

import sys
import pytest

from PyQt6.QtWidgets import QApplication

from focusquest.database.db import configure_engine, init_db
from focusquest.timer.engine import TimerEngine


@pytest.fixture(scope="session")
def qapp():
    """A single QApplication instance shared across the entire test run."""
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture(autouse=True)
def test_db():
    """Point every test at a fresh in-memory SQLite database."""
    configure_engine("sqlite:///:memory:")
    init_db()
    yield


@pytest.fixture
def engine(qapp):
    """Fresh TimerEngine with DB enabled, auto-advance OFF."""
    return TimerEngine(parent=None, db_enabled=True, auto_advance=False)


@pytest.fixture
def engine_auto(qapp):
    """Fresh TimerEngine with auto-advance ON."""
    return TimerEngine(parent=None, db_enabled=True, auto_advance=True)


@pytest.fixture
def engine_no_db(qapp):
    """Fresh TimerEngine with DB disabled (pure state-machine tests)."""
    return TimerEngine(parent=None, db_enabled=False, auto_advance=False)
