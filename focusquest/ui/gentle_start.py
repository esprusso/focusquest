"""Gentle start overlay — shown at app launch.

Greets the user with positive streak messaging, cumulative progress,
an upcoming unlock teaser, and a friendly "Ready when you are" button.
Uses only positive, encouraging language throughout.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QSizePolicy,
)

from ..database.db import get_session
from ..database.models import UserProgress
from ..gamification.unlockables import REGISTRY


class GentleStartWidget(QWidget):
    """Welcome overlay shown when the app first opens."""

    start_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette: dict[str, str] = {}
        self._build_ui()
        self._populate()

    # ── build ─────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 40, 32, 32)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Greeting
        self._greeting = QLabel("", self)
        self._greeting.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._greeting.setWordWrap(True)
        self._greeting.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(self._greeting)

        # Streak message
        self._streak_msg = QLabel("", self)
        self._streak_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._streak_msg.setWordWrap(True)
        self._streak_msg.setStyleSheet("font-size: 14px; opacity: 0.8;")
        layout.addWidget(self._streak_msg)

        # Cumulative progress
        self._progress_msg = QLabel("", self)
        self._progress_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress_msg.setWordWrap(True)
        self._progress_msg.setStyleSheet("font-size: 13px; opacity: 0.6;")
        layout.addWidget(self._progress_msg)

        # Unlock teaser
        self._unlock_teaser = QLabel("", self)
        self._unlock_teaser.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._unlock_teaser.setWordWrap(True)
        self._unlock_teaser.setStyleSheet("font-size: 13px; opacity: 0.6;")
        layout.addWidget(self._unlock_teaser)

        layout.addSpacing(12)

        # Start button
        btn = QPushButton("Ready when you are", self)
        btn.setObjectName("primaryButton")
        btn.setFixedHeight(48)
        btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed,
        )
        btn.clicked.connect(self.start_requested.emit)
        layout.addWidget(btn)

    # ── populate with DB data ─────────────────────────────────────────

    def _populate(self) -> None:
        """Fill in streak, progress, and unlock teaser from the database."""
        streak = 0
        total_sessions = 0
        total_minutes = 0
        level = 1
        is_new_user = True

        with get_session() as db:
            progress = db.query(UserProgress).first()
            if progress:
                streak = progress.current_streak_days
                total_sessions = progress.total_sessions_completed
                total_minutes = progress.total_focus_minutes
                level = progress.current_level
                is_new_user = total_sessions == 0

        # ── greeting ─────────────────────────────────────────────────
        if is_new_user:
            self._greeting.setText("Welcome to FocusQuest!")
            self._streak_msg.setText(
                "Ready to begin your focus journey?"
            )
        elif streak >= 7:
            self._greeting.setText(
                f"You\u2019re on fire! \U0001f525"
            )
            self._streak_msg.setText(
                f"{streak}-day streak \u2014 incredible!"
            )
        elif streak >= 3:
            self._greeting.setText("Welcome back!")
            self._streak_msg.setText(
                f"You\u2019re on a {streak}-day streak!"
            )
        elif streak == 1:
            self._greeting.setText("Great start!")
            self._streak_msg.setText(
                "Day 1 of a new streak!"
            )
        else:
            # streak == 0, returning user — NEVER mention broken streak
            self._greeting.setText("Welcome back!")
            self._streak_msg.setText(
                "Let\u2019s start a new streak today."
            )

        # ── cumulative progress ──────────────────────────────────────
        if total_sessions > 0:
            hours = total_minutes // 60
            mins = total_minutes % 60
            if hours > 0:
                time_str = f"{hours}h {mins}m"
            else:
                time_str = f"{mins}m"
            self._progress_msg.setText(
                f"You\u2019ve focused for {time_str} total "
                f"across {total_sessions} session{'s' if total_sessions != 1 else ''}."
            )
        else:
            self._progress_msg.setText("")

        # ── unlock teaser ────────────────────────────────────────────
        next_item = REGISTRY.next_upcoming(level)
        if next_item:
            self._unlock_teaser.setText(
                f"Next unlock: {next_item.name} "
                f"(Level {next_item.required_level})"
            )
        else:
            self._unlock_teaser.setText("")

    # ── theming ───────────────────────────────────────────────────────

    def apply_palette(self, palette: dict[str, str]) -> None:
        self._palette = palette
