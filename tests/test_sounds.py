"""Tests for settings, sound synthesis, break-warning signal, and dialog.

Covers:
- Settings dataclass defaults and JSON round-trip
- SoundManager WAV generation and playback API
- TimerEngine break_ending_soon signal
- SettingsDialog creation and value population
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from focusquest.settings import Settings, load_settings, save_settings, SETTINGS_PATH
from focusquest.audio.sounds import (
    SoundManager,
    _generate_chime,
    _generate_achievement,
    _generate_bell,
    _generate_double_tap,
    _generate_fanfare,
    _generate_click,
    SOUND_NAMES,
)
from focusquest.timer.engine import TimerEngine, TimerState, SessionType


# ═══════════════════════════════════════════════════════════════════════
#  SETTINGS
# ═══════════════════════════════════════════════════════════════════════


class TestSettingsDefaults:
    def test_work_duration(self):
        s = Settings()
        assert s.work_duration == 25 * 60

    def test_short_break(self):
        s = Settings()
        assert s.short_break_duration == 5 * 60

    def test_long_break(self):
        s = Settings()
        assert s.long_break_duration == 15 * 60

    def test_rounds_per_cycle(self):
        s = Settings()
        assert s.rounds_per_cycle == 4

    def test_sound_enabled(self):
        s = Settings()
        assert s.sound_enabled is True

    def test_volume_default(self):
        s = Settings()
        assert s.sound_volume == 70

    def test_notifications_default(self):
        s = Settings()
        assert s.notifications_enabled is True

    def test_dnd_default(self):
        s = Settings()
        assert s.do_not_disturb is False

    def test_minimize_to_tray_default(self):
        s = Settings()
        assert s.minimize_to_tray is True

    def test_auto_start_defaults(self):
        s = Settings()
        assert s.auto_start_breaks is False
        assert s.auto_start_work is False


class TestSettingsPersistence:
    def test_round_trip(self, tmp_path, monkeypatch):
        """save → load produces identical settings."""
        path = tmp_path / "settings.json"
        monkeypatch.setattr(
            "focusquest.settings.SETTINGS_PATH", path,
        )
        monkeypatch.setattr(
            "focusquest.settings.APP_SUPPORT_DIR", tmp_path,
        )
        original = Settings(work_duration=30 * 60, sound_volume=42)
        save_settings(original)
        loaded = load_settings()
        assert loaded.work_duration == 30 * 60
        assert loaded.sound_volume == 42

    def test_missing_file_returns_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "focusquest.settings.SETTINGS_PATH",
            tmp_path / "nonexistent.json",
        )
        s = load_settings()
        assert s.work_duration == 25 * 60  # default

    def test_invalid_json_returns_defaults(self, tmp_path, monkeypatch):
        path = tmp_path / "settings.json"
        path.write_text("NOT VALID JSON", encoding="utf-8")
        monkeypatch.setattr("focusquest.settings.SETTINGS_PATH", path)
        s = load_settings()
        assert s.work_duration == 25 * 60

    def test_extra_keys_ignored(self, tmp_path, monkeypatch):
        path = tmp_path / "settings.json"
        data = {"work_duration": 1800, "unknown_future_key": True}
        path.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr("focusquest.settings.SETTINGS_PATH", path)
        s = load_settings()
        assert s.work_duration == 1800
        assert not hasattr(s, "unknown_future_key")


# ═══════════════════════════════════════════════════════════════════════
#  SOUND SYNTHESIS
# ═══════════════════════════════════════════════════════════════════════


class TestSoundGeneration:
    """Test that each generator produces valid WAV bytes."""

    @pytest.mark.parametrize("gen_fn", [
        _generate_chime,
        _generate_achievement,
        _generate_bell,
        _generate_double_tap,
        _generate_fanfare,
        _generate_click,
    ])
    def test_generator_produces_wav(self, gen_fn):
        data = gen_fn()
        assert isinstance(data, bytes)
        assert len(data) > 100  # non-trivial WAV
        # WAV files start with RIFF header
        assert data[:4] == b"RIFF"

    @pytest.mark.parametrize("gen_fn", [
        _generate_chime,
        _generate_achievement,
        _generate_bell,
        _generate_double_tap,
        _generate_fanfare,
        _generate_click,
    ])
    def test_wav_is_parseable(self, gen_fn):
        import io
        data = gen_fn()
        buf = io.BytesIO(data)
        with wave.open(buf, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 44100
            assert wf.getnframes() > 0


@pytest.mark.usefixtures("qapp")
class TestSoundManager:
    def test_create(self, tmp_path):
        mgr = SoundManager(parent=None, sounds_dir=tmp_path)
        assert mgr.enabled is True

    def test_wav_files_generated(self, tmp_path):
        SoundManager(parent=None, sounds_dir=tmp_path)
        for name in SOUND_NAMES:
            path = tmp_path / f"{name}.wav"
            assert path.exists(), f"Missing WAV: {name}"
            assert path.stat().st_size > 100

    def test_set_volume(self, tmp_path):
        mgr = SoundManager(parent=None, sounds_dir=tmp_path)
        mgr.set_volume(30)
        assert mgr.volume == 30

    def test_set_volume_clamps_high(self, tmp_path):
        mgr = SoundManager(parent=None, sounds_dir=tmp_path)
        mgr.set_volume(200)
        assert mgr.volume == 100

    def test_set_volume_clamps_low(self, tmp_path):
        mgr = SoundManager(parent=None, sounds_dir=tmp_path)
        mgr.set_volume(-10)
        assert mgr.volume == 0

    def test_set_enabled(self, tmp_path):
        mgr = SoundManager(parent=None, sounds_dir=tmp_path)
        mgr.set_enabled(False)
        assert mgr.enabled is False

    def test_play_invalid_name_no_crash(self, tmp_path):
        mgr = SoundManager(parent=None, sounds_dir=tmp_path)
        mgr.play("nonexistent_sound")  # should not raise

    def test_play_while_disabled_no_crash(self, tmp_path):
        mgr = SoundManager(parent=None, sounds_dir=tmp_path)
        mgr.set_enabled(False)
        mgr.play("click")  # should be a no-op

    def test_all_sounds_loaded(self, tmp_path):
        mgr = SoundManager(parent=None, sounds_dir=tmp_path)
        for name in SOUND_NAMES:
            assert name in mgr._effects


# ═══════════════════════════════════════════════════════════════════════
#  BREAK-WARNING SIGNAL
# ═══════════════════════════════════════════════════════════════════════


class TestBreakWarningSignal:
    """Test that break_ending_soon fires correctly."""

    def test_fires_during_short_break(self, engine_no_db):
        """break_ending_soon should fire once at 60 s during a short break."""
        eng = engine_no_db
        signals: list[bool] = []
        eng.break_ending_soon.connect(lambda: signals.append(True))

        # Manually set up a short break with 62 s remaining
        eng._state = TimerState.SHORT_BREAK
        eng._remaining = 62

        # Tick down from 62 → 61 (no fire)
        eng._on_tick()
        assert len(signals) == 0
        assert eng._remaining == 61

        # Tick 61 → 60 (fires!)
        eng._on_tick()
        assert len(signals) == 1
        assert eng._remaining == 60

        # Tick 60 → 59 (should NOT fire again)
        eng._on_tick()
        assert len(signals) == 1

    def test_fires_during_long_break(self, engine_no_db):
        eng = engine_no_db
        signals: list[bool] = []
        eng.break_ending_soon.connect(lambda: signals.append(True))

        eng._state = TimerState.LONG_BREAK
        eng._remaining = 61

        eng._on_tick()  # 61 → 60
        assert len(signals) == 1

    def test_does_not_fire_during_work(self, engine_no_db):
        eng = engine_no_db
        signals: list[bool] = []
        eng.break_ending_soon.connect(lambda: signals.append(True))

        eng._state = TimerState.WORKING
        eng._remaining = 61

        eng._on_tick()  # 61 → 60
        assert len(signals) == 0

    def test_fires_only_once(self, engine_no_db):
        eng = engine_no_db
        signals: list[bool] = []
        eng.break_ending_soon.connect(lambda: signals.append(True))

        eng._state = TimerState.SHORT_BREAK
        eng._remaining = 62

        # Tick through 62 → 0
        for _ in range(62):
            eng._on_tick()

        assert len(signals) == 1  # only once

    def test_resets_on_new_session(self, engine_no_db):
        eng = engine_no_db
        signals: list[bool] = []
        eng.break_ending_soon.connect(lambda: signals.append(True))

        # First break — fire at 60s
        eng._state = TimerState.SHORT_BREAK
        eng._remaining = 61
        eng._on_tick()
        assert len(signals) == 1

        # Begin a new session (resets the flag)
        eng._begin_session(SessionType.WORK, 1500)
        assert eng._break_warning_fired is False

    def test_does_not_fire_at_zero(self, engine_no_db):
        """Should not fire when remaining hits 0."""
        eng = engine_no_db
        signals: list[bool] = []
        eng.break_ending_soon.connect(lambda: signals.append(True))

        eng._state = TimerState.SHORT_BREAK
        eng._remaining = 1
        eng._break_warning_fired = False

        eng._on_tick()  # 1 → 0
        # remaining is 0, which is NOT > 0, so should not fire
        assert len(signals) == 0


# ═══════════════════════════════════════════════════════════════════════
#  SETTINGS DIALOG
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.usefixtures("qapp")
class TestSettingsDialog:
    def test_create(self):
        from focusquest.ui.settings_dialog import SettingsDialog
        s = Settings()
        dlg = SettingsDialog(s)
        assert dlg.windowTitle() == "Settings"

    def test_reflects_settings(self):
        from focusquest.ui.settings_dialog import SettingsDialog
        s = Settings(work_duration=30 * 60, sound_volume=50)
        dlg = SettingsDialog(s)
        assert dlg._work_spin.value() == 30
        assert dlg._vol_slider.value() == 50

    def test_changes_update_settings(self):
        from focusquest.ui.settings_dialog import SettingsDialog
        s = Settings()
        dlg = SettingsDialog(s)
        dlg._work_spin.setValue(45)
        assert s.work_duration == 45 * 60

    def test_volume_slider_updates_label(self):
        from focusquest.ui.settings_dialog import SettingsDialog
        s = Settings()
        dlg = SettingsDialog(s)
        dlg._vol_slider.setValue(85)
        assert dlg._vol_label.text() == "85%"
        assert s.sound_volume == 85

    def test_checkbox_toggles(self):
        from focusquest.ui.settings_dialog import SettingsDialog
        s = Settings()
        dlg = SettingsDialog(s)
        dlg._dnd_cb.setChecked(True)
        assert s.do_not_disturb is True

    def test_sound_preview_callback(self):
        from focusquest.ui.settings_dialog import SettingsDialog
        calls: list[bool] = []
        s = Settings()
        dlg = SettingsDialog(s, sound_preview_callback=lambda: calls.append(True))
        dlg._on_volume_released()
        assert len(calls) == 1
