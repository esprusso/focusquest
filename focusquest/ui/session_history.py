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


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convert '#RRGGBB' to 'rgba(R, G, B, alpha)'."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


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
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)
        self._header = header

        self._rows_container = QVBoxLayout()
        self._rows_container.setSpacing(4)
        layout.addLayout(self._rows_container)

        self._empty_label = QLabel("No sessions yet today \u2014 ready when you are!")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty_label)

        self._row_widgets: list[QWidget] = []

        # Apply default styles (before any palette is provided)
        self._apply_styles()

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
        text_color = self._palette.get("text", "#E2E2F0")
        text_muted = self._palette.get("text_muted", "#7A7A9A")
        border_color = self._palette.get("border", "#313154")
        hover_bg = _hex_to_rgba(
            self._palette.get("accent", "#CBA6F7"), 0.06,
        )

        frame = QFrame(self)
        frame.setStyleSheet(
            f"QFrame {{ background: transparent; border-radius: 6px;"
            f"  padding: 4px 8px; }}"
            f"QFrame:hover {{ background: {hover_bg}; }}"
        )
        row = QHBoxLayout(frame)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(8)

        # Task label (clickable)
        label_text = sess.task_label or "Untitled session"
        task_lbl = QLabel(label_text)
        task_lbl.setStyleSheet(
            f"font-size: 12px; color: {text_color};"
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
        dur_lbl.setStyleSheet(f"font-size: 12px; color: {text_muted};")
        dur_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Time completed
        if sess.end_time:
            time_str = sess.end_time.strftime("%-I:%M %p").lower()
        else:
            time_str = ""
        time_lbl = QLabel(time_str)
        time_lbl.setStyleSheet(f"font-size: 11px; color: {border_color};")
        time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        row.addWidget(task_lbl)
        row.addWidget(dur_lbl)
        row.addWidget(time_lbl)

        return frame

    # ── theming ───────────────────────────────────────────────────────

    def _apply_styles(self) -> None:
        """Set label stylesheets from the current palette (or defaults)."""
        text_muted = self._palette.get("text_muted", "#7A7A9A")
        border_color = self._palette.get("border", "#313154")

        self._header.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {text_muted};"
        )
        self._empty_label.setStyleSheet(
            f"font-size: 12px; color: {border_color};"
        )

    def apply_palette(self, palette: dict[str, str]) -> None:
        self._palette = palette
        self._apply_styles()
        # Re-build existing rows with the new palette
        if self._row_widgets:
            self.refresh()
