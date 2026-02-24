"""Session history widget — shows last 5 completed work sessions from today.

Sits below the timer in the Focus tab.  Clicking a task label emits
``label_clicked(str)`` so the timer can auto-fill the task input.
"""

from __future__ import annotations

from datetime import date, datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy,
)

from ..database.db import get_session
from ..database.models import Session


class SessionHistoryWidget(QWidget):
    """Displays today's recently completed work sessions."""

    label_clicked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette: dict[str, str] = {}
        self._build_ui()

    # ── build ─────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(6)

        header = QLabel("Today's Sessions")
        header.setStyleSheet("font-size: 13px; font-weight: 600; opacity: 0.7;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)
        self._header = header

        self._rows_container = QVBoxLayout()
        self._rows_container.setSpacing(4)
        layout.addLayout(self._rows_container)

        self._empty_label = QLabel("No sessions yet today — ready when you are!")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("font-size: 12px; opacity: 0.5;")
        layout.addWidget(self._empty_label)

        self._row_widgets: list[QWidget] = []

    # ── refresh ───────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload today's sessions from the database."""
        # Clear old rows
        for w in self._row_widgets:
            w.setParent(None)
            w.deleteLater()
        self._row_widgets.clear()

        today = date.today()

        with get_session() as db:
            sessions = (
                db.query(Session)
                .filter(
                    Session.session_type == "work",
                    Session.completed == True,  # noqa: E712
                )
                .order_by(Session.end_time.desc())
                .all()
            )
            # Filter to today (in Python to avoid SQL date function portability)
            today_sessions = [
                s for s in sessions
                if s.end_time is not None
                and s.end_time.date() == today
            ][:5]

        if not today_sessions:
            self._empty_label.setVisible(True)
            return

        self._empty_label.setVisible(False)

        for sess in today_sessions:
            row = self._make_row(sess)
            self._rows_container.addWidget(row)
            self._row_widgets.append(row)

    # ── row builder ───────────────────────────────────────────────────

    def _make_row(self, sess: Session) -> QWidget:
        frame = QFrame(self)
        frame.setStyleSheet(
            "QFrame { background: transparent; border-radius: 6px; padding: 4px 8px; }"
            "QFrame:hover { background: rgba(255,255,255,0.04); }"
        )
        row = QHBoxLayout(frame)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(8)

        # Task label (clickable)
        label_text = sess.task_label or "Untitled session"
        task_lbl = QLabel(label_text)
        task_lbl.setStyleSheet(
            "font-size: 12px; cursor: pointer; text-decoration: none;"
        )
        task_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        task_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred,
        )
        # Click handler
        if sess.task_label:
            label = sess.task_label
            task_lbl.mousePressEvent = lambda e, l=label: self.label_clicked.emit(l)

        # Duration
        mins = (sess.duration_seconds or 0) // 60
        dur_lbl = QLabel(f"{mins}m")
        dur_lbl.setStyleSheet("font-size: 12px; opacity: 0.5;")
        dur_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Time completed
        if sess.end_time:
            time_str = sess.end_time.strftime("%-I:%M %p").lower()
        else:
            time_str = ""
        time_lbl = QLabel(time_str)
        time_lbl.setStyleSheet("font-size: 11px; opacity: 0.4;")
        time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        row.addWidget(task_lbl)
        row.addWidget(dur_lbl)
        row.addWidget(time_lbl)

        return frame

    # ── theming ───────────────────────────────────────────────────────

    def apply_palette(self, palette: dict[str, str]) -> None:
        self._palette = palette
