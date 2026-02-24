"""Settings dialog for FocusQuest.

A modal dialog that lets users configure timer durations, audio, and
notification preferences.  Changes are saved immediately to disk and
returned to the caller so the app can apply them.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QSpinBox, QSlider, QCheckBox, QPushButton,
    QFrame, QWidget,
)

from ..settings import Settings, save_settings


class SettingsDialog(QDialog):
    """Modal dialog for all user preferences."""

    def __init__(
        self,
        settings: Settings,
        parent: QWidget | None = None,
        *,
        sound_preview_callback: callable | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(420)
        self.setModal(True)

        self._settings = settings
        self._sound_preview = sound_preview_callback

        self._build_ui()
        self._populate()

    # ══════════════════════════════════════════════════════════════════
    #  BUILD UI
    # ══════════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # ── Timer section ────────────────────────────────────────────
        root.addWidget(self._section_label("Timer"))
        timer_form = QFormLayout()
        timer_form.setContentsMargins(0, 0, 0, 0)
        timer_form.setHorizontalSpacing(20)
        timer_form.setVerticalSpacing(10)

        self._work_spin = QSpinBox()
        self._work_spin.setRange(1, 120)
        self._work_spin.setSuffix(" min")
        self._work_spin.valueChanged.connect(self._on_timer_changed)
        timer_form.addRow("Work duration:", self._work_spin)

        self._short_spin = QSpinBox()
        self._short_spin.setRange(1, 30)
        self._short_spin.setSuffix(" min")
        self._short_spin.valueChanged.connect(self._on_timer_changed)
        timer_form.addRow("Short break:", self._short_spin)

        self._long_spin = QSpinBox()
        self._long_spin.setRange(1, 60)
        self._long_spin.setSuffix(" min")
        self._long_spin.valueChanged.connect(self._on_timer_changed)
        timer_form.addRow("Long break:", self._long_spin)

        self._rounds_spin = QSpinBox()
        self._rounds_spin.setRange(1, 12)
        self._rounds_spin.valueChanged.connect(self._on_timer_changed)
        timer_form.addRow("Rounds per cycle:", self._rounds_spin)

        self._auto_breaks_cb = QCheckBox("Auto-start breaks")
        self._auto_breaks_cb.toggled.connect(self._on_toggle_changed)
        timer_form.addRow("", self._auto_breaks_cb)

        self._auto_work_cb = QCheckBox("Auto-start work sessions")
        self._auto_work_cb.toggled.connect(self._on_toggle_changed)
        timer_form.addRow("", self._auto_work_cb)

        root.addLayout(timer_form)

        # ── separator ────────────────────────────────────────────────
        root.addWidget(self._separator())

        # ── Sound & Notifications section ────────────────────────────
        root.addWidget(self._section_label("Sound & Notifications"))
        snd_form = QFormLayout()
        snd_form.setContentsMargins(0, 0, 0, 0)
        snd_form.setHorizontalSpacing(20)
        snd_form.setVerticalSpacing(10)

        self._sound_cb = QCheckBox("Sound effects")
        self._sound_cb.toggled.connect(self._on_toggle_changed)
        snd_form.addRow("", self._sound_cb)

        # Volume slider row
        vol_row = QHBoxLayout()
        vol_row.setSpacing(10)
        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setTickInterval(10)
        self._vol_label = QLabel("70%")
        self._vol_label.setMinimumWidth(36)
        self._vol_slider.valueChanged.connect(self._on_volume_changed)
        self._vol_slider.sliderReleased.connect(self._on_volume_released)
        vol_row.addWidget(self._vol_slider)
        vol_row.addWidget(self._vol_label)

        vol_wrapper = QWidget()
        vol_wrapper.setLayout(vol_row)
        snd_form.addRow("Volume:", vol_wrapper)

        self._notif_cb = QCheckBox("Desktop notifications")
        self._notif_cb.toggled.connect(self._on_toggle_changed)
        snd_form.addRow("", self._notif_cb)

        self._dnd_cb = QCheckBox("Do not disturb")
        self._dnd_cb.toggled.connect(self._on_toggle_changed)
        snd_form.addRow("", self._dnd_cb)

        root.addLayout(snd_form)

        # ── separator ────────────────────────────────────────────────
        root.addWidget(self._separator())

        # ── Window section ───────────────────────────────────────────
        root.addWidget(self._section_label("Window"))
        win_form = QFormLayout()
        win_form.setContentsMargins(0, 0, 0, 0)

        self._tray_cb = QCheckBox("Minimize to menu bar on close")
        self._tray_cb.toggled.connect(self._on_toggle_changed)
        win_form.addRow("", self._tray_cb)

        root.addLayout(win_form)

        # ── close button ─────────────────────────────────────────────
        root.addStretch()
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 15px; font-weight: 700; margin-top: 4px;")
        return lbl

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet("background-color: rgba(255,255,255,0.08);")
        return line

    # ══════════════════════════════════════════════════════════════════
    #  POPULATE FROM SETTINGS
    # ══════════════════════════════════════════════════════════════════

    def _populate(self) -> None:
        s = self._settings
        self._work_spin.setValue(s.work_duration // 60)
        self._short_spin.setValue(s.short_break_duration // 60)
        self._long_spin.setValue(s.long_break_duration // 60)
        self._rounds_spin.setValue(s.rounds_per_cycle)
        self._auto_breaks_cb.setChecked(s.auto_start_breaks)
        self._auto_work_cb.setChecked(s.auto_start_work)
        self._sound_cb.setChecked(s.sound_enabled)
        self._vol_slider.setValue(s.sound_volume)
        self._vol_label.setText(f"{s.sound_volume}%")
        self._notif_cb.setChecked(s.notifications_enabled)
        self._dnd_cb.setChecked(s.do_not_disturb)
        self._tray_cb.setChecked(s.minimize_to_tray)

    # ══════════════════════════════════════════════════════════════════
    #  CHANGE HANDLERS — save immediately
    # ══════════════════════════════════════════════════════════════════

    def _on_timer_changed(self) -> None:
        self._settings.work_duration = self._work_spin.value() * 60
        self._settings.short_break_duration = self._short_spin.value() * 60
        self._settings.long_break_duration = self._long_spin.value() * 60
        self._settings.rounds_per_cycle = self._rounds_spin.value()
        self._save()

    def _on_toggle_changed(self) -> None:
        self._settings.auto_start_breaks = self._auto_breaks_cb.isChecked()
        self._settings.auto_start_work = self._auto_work_cb.isChecked()
        self._settings.sound_enabled = self._sound_cb.isChecked()
        self._settings.notifications_enabled = self._notif_cb.isChecked()
        self._settings.do_not_disturb = self._dnd_cb.isChecked()
        self._settings.minimize_to_tray = self._tray_cb.isChecked()
        self._save()

    def _on_volume_changed(self, value: int) -> None:
        self._vol_label.setText(f"{value}%")
        self._settings.sound_volume = value
        self._save()

    def _on_volume_released(self) -> None:
        """Play a click sound when the user releases the volume slider."""
        if self._sound_preview:
            self._sound_preview()

    def _save(self) -> None:
        save_settings(self._settings)

    # ══════════════════════════════════════════════════════════════════
    #  PUBLIC
    # ══════════════════════════════════════════════════════════════════

    @property
    def settings(self) -> Settings:
        return self._settings
