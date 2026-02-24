"""Main timer display widget — the Focus tab.

Layout (top → bottom):
    - Task label input (subtle, top of card)
    - ProgressRing (large, centred)
    - Main action button row (context-dependent)
    - ADHD micro-session row (only when idle + next is work)
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QFrame, QSizePolicy,
)

from ..timer.engine import TimerEngine, TimerState, SessionType
from .progress_ring import ProgressRing
from .companions import BaseCompanion, create_companion


SESSION_LABELS: dict[TimerState, str] = {
    TimerState.IDLE:        "READY",
    TimerState.WORKING:     "FOCUS TIME",
    TimerState.SHORT_BREAK: "SHORT BREAK",
    TimerState.LONG_BREAK:  "LONG BREAK",
    TimerState.PAUSED:      "PAUSED",
}

NEXT_SESSION_LABELS: dict[SessionType, str] = {
    SessionType.WORK:        "NEXT: FOCUS",
    SessionType.SHORT_BREAK: "NEXT: SHORT BREAK",
    SessionType.LONG_BREAK:  "NEXT: LONG BREAK",
}


class TimerWidget(QWidget):
    """The main timer card shown in the Focus tab."""

    task_label_changed = pyqtSignal(str)

    def __init__(self, engine: TimerEngine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._palette: dict[str, str] = {}
        self._compact: bool = False
        self._build_ui()
        self._connect_signals()
        self._refresh_display(engine.remaining)
        self._update_button_visibility(engine.state)

    # ── build ─────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card = QFrame(self)
        card.setObjectName("card")
        root.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(32, 24, 32, 28)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ── task label input (top, subtle) ───────────────────────────
        self._task_input = QLineEdit(card)
        self._task_input.setPlaceholderText("What are you working on? (optional)")
        self._task_input.setMaxLength(100)
        self._task_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._task_input)

        layout.addSpacing(16)

        # ── progress ring (centrepiece) ──────────────────────────────
        ring_container = QHBoxLayout()
        ring_container.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._ring = ProgressRing(card)
        self._ring.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed,
        )
        self._ring.setFixedSize(340, 340)
        ring_container.addWidget(self._ring)
        layout.addLayout(ring_container)

        # ── companion slot (below ring) ────────────────────────────
        self._companion_container = QHBoxLayout()
        self._companion_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(self._companion_container)
        self._companion_widget: BaseCompanion | None = None

        layout.addSpacing(12)

        # ── main controls ────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._reset_btn = QPushButton("Stop", card)
        self._reset_btn.setObjectName("dangerButton")

        self._start_pause_btn = QPushButton("Start", card)
        self._start_pause_btn.setObjectName("primaryButton")

        self._skip_btn = QPushButton("Skip", card)
        self._skip_btn.setObjectName("secondaryButton")

        btn_row.addWidget(self._reset_btn)
        btn_row.addWidget(self._start_pause_btn)
        btn_row.addWidget(self._skip_btn)
        layout.addLayout(btn_row)

        layout.addSpacing(12)

        # ── ADHD-friendly controls ───────────────────────────────────
        adhd_row = QHBoxLayout()
        adhd_row.setSpacing(12)
        adhd_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._extend_btn = QPushButton("+5 min", card)
        self._extend_btn.setObjectName("extendButton")
        self._extend_btn.setToolTip("In the zone? Keep going!")
        self._extend_btn.setVisible(False)

        self._micro_10_btn = QPushButton("10 min", card)
        self._micro_10_btn.setObjectName("microButton")
        self._micro_10_btn.setToolTip("Low energy? Start small.")

        self._micro_15_btn = QPushButton("15 min", card)
        self._micro_15_btn.setObjectName("microButton")
        self._micro_15_btn.setToolTip("Can't do 25? That's okay.")

        adhd_row.addWidget(self._extend_btn)
        adhd_row.addWidget(self._micro_10_btn)
        adhd_row.addWidget(self._micro_15_btn)
        layout.addLayout(adhd_row)

        layout.addSpacing(12)

        # ── round dot indicators (4 dots = one cycle) ────────────────
        dot_row = QHBoxLayout()
        dot_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dot_row.setSpacing(10)
        self._dots: list[QLabel] = []
        for _ in range(4):
            dot = QLabel("○", card)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dot.setStyleSheet("font-size: 18px;")
            self._dots.append(dot)
            dot_row.addWidget(dot)
        layout.addLayout(dot_row)

    # ── signals ───────────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        self._start_pause_btn.clicked.connect(self._on_start_pause)
        self._reset_btn.clicked.connect(self._engine.reset)
        self._skip_btn.clicked.connect(self._engine.skip)
        self._extend_btn.clicked.connect(lambda: self._engine.extend())
        self._micro_10_btn.clicked.connect(lambda: self._engine.start_micro(10))
        self._micro_15_btn.clicked.connect(lambda: self._engine.start_micro(15))
        self._task_input.textChanged.connect(self._on_task_changed)

        self._engine.tick.connect(self._refresh_display)
        self._engine.state_changed.connect(self._on_state_changed)

    # ── slots ─────────────────────────────────────────────────────────────

    def _on_start_pause(self) -> None:
        state = self._engine.state
        if self._engine.is_running:
            self._engine.pause()
        elif state == TimerState.PAUSED:
            self._engine.resume()
        else:
            self._engine.task_label = self._task_input.text().strip()
            self._engine.start()

    def _on_task_changed(self, text: str) -> None:
        self.task_label_changed.emit(text)

    def _on_state_changed(self, state: TimerState) -> None:
        # ── button label ──────────────────────────────────────────────
        if self._engine.is_running:
            self._start_pause_btn.setText("Pause")
        elif state == TimerState.PAUSED:
            self._start_pause_btn.setText("Resume")
        else:
            self._start_pause_btn.setText("Start")

        # ── ring state label ─────────────────────────────────────────
        if state == TimerState.IDLE:
            lbl = NEXT_SESSION_LABELS.get(self._engine.session_type, "READY")
            self._ring.set_state_label(lbl)
        else:
            self._ring.set_state_label(SESSION_LABELS.get(state, "FOCUS TIME"))

        # ── round indicator ──────────────────────────────────────────
        r = self._engine.current_round
        total = self._engine.rounds_per_cycle
        self._ring.set_round_text(f"Round {r} of {total}")

        # ── dot indicators ───────────────────────────────────────────
        done = r - 1
        if state in (
            TimerState.SHORT_BREAK,
            TimerState.LONG_BREAK,
            TimerState.PAUSED,
        ) or (state == TimerState.IDLE
              and self._engine.session_type != SessionType.WORK):
            done = r  # show the round we just finished
        for i, dot in enumerate(self._dots):
            if i < done:
                dot.setText("●")
                if self._palette:
                    dot.setStyleSheet(
                        f"font-size: 18px; color: {self._palette.get('accent', '#CBA6F7')};"
                    )
            else:
                dot.setText("○")
                dot.setStyleSheet(
                    f"font-size: 18px; color: {self._palette.get('text_muted', '#7A7A9A')};"
                )

        # ── ring colors ──────────────────────────────────────────────
        self._ring.apply_state(state)

        # ── companion state ──────────────────────────────────────────
        if self._companion_widget is not None:
            _COMP_STATE_MAP = {
                TimerState.IDLE:        "idle",
                TimerState.WORKING:     "focus",
                TimerState.SHORT_BREAK: "idle",
                TimerState.LONG_BREAK:  "idle",
                TimerState.PAUSED:      "sleep",
            }
            self._companion_widget.set_state(
                _COMP_STATE_MAP.get(state, "idle")
            )

        # ── button visibility ────────────────────────────────────────
        self._update_button_visibility(state)

        # ── refresh the time display ─────────────────────────────────
        self._refresh_display(self._engine.remaining)

    def _update_button_visibility(self, state: TimerState) -> None:
        """Show/hide buttons based on current state."""
        is_idle = state == TimerState.IDLE
        is_work_active = state == TimerState.WORKING
        is_paused_from_work = (
            state == TimerState.PAUSED
            and self._engine._paused_from == TimerState.WORKING
        )
        next_is_work = (
            is_idle and self._engine.session_type == SessionType.WORK
        )
        is_running_or_paused = not is_idle

        # "+5 min" only during work (or paused-from-work)
        self._extend_btn.setVisible(is_work_active or is_paused_from_work)

        # Micro buttons only when idle AND next session is work (hidden in compact)
        self._micro_10_btn.setVisible(next_is_work and not self._compact)
        self._micro_15_btn.setVisible(next_is_work and not self._compact)

        # Stop/Skip only visible when running or paused
        self._reset_btn.setVisible(is_running_or_paused)
        self._skip_btn.setVisible(is_running_or_paused or is_idle)

        # Task input editable only when idle
        self._task_input.setEnabled(is_idle)

    def _refresh_display(self, remaining: int) -> None:
        minutes, seconds = divmod(remaining, 60)
        self._ring.set_time_text(f"{minutes:02d}:{seconds:02d}")

        pct = self._engine.percent_complete
        self._ring.set_percent(pct)

        # Growth‑dependent companions (Sprout, Zen) track session progress
        if self._companion_widget is not None:
            self._companion_widget.set_session_progress(pct)

    # ── companion management ──────────────────────────────────────────────

    def set_companion(self, companion_key: str) -> None:
        """Replace the current companion widget."""
        if self._companion_widget is not None:
            self._companion_widget.setParent(None)
            self._companion_widget.deleteLater()
            self._companion_widget = None

        widget = create_companion(companion_key, self)
        self._companion_widget = widget
        self._companion_container.addWidget(widget)

    # ── compact mode ─────────────────────────────────────────────────────

    def set_compact(self, compact: bool) -> None:
        """Toggle compact display: hide extras, shrink ring."""
        self._compact = compact
        self._task_input.setVisible(not compact)
        if self._companion_widget is not None:
            self._companion_widget.setVisible(not compact)
        for dot in self._dots:
            dot.setVisible(not compact)
        # Shrink / restore ring
        size = 240 if compact else 340
        self._ring.setFixedSize(size, size)
        # Refresh button visibility (respects compact flag)
        self._update_button_visibility(self._engine.state)

    # ── theming ───────────────────────────────────────────────────────────

    def apply_palette(
        self,
        palette: dict[str, str],
        ring_colors: dict | None = None,
    ) -> None:
        self._palette = palette
        self._ring.apply_palette(palette)
        if ring_colors is not None:
            self._ring.set_ring_colors(ring_colors)
