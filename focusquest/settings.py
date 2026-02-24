"""Application settings with JSON persistence.

Settings are stored at:
    ~/Library/Application Support/FocusQuest/settings.json

Usage::

    settings = load_settings()
    settings.sound_volume = 50
    save_settings(settings)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, fields
from pathlib import Path


# Reuse the app-support directory from db.py
APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "FocusQuest"
SETTINGS_PATH = APP_SUPPORT_DIR / "settings.json"


@dataclass
class Settings:
    """All user-configurable preferences."""

    # ── timer ─────────────────────────────────────────────────────────
    work_duration: int = 25 * 60           # seconds
    short_break_duration: int = 5 * 60
    long_break_duration: int = 15 * 60
    rounds_per_cycle: int = 4
    auto_start_breaks: bool = False
    auto_start_work: bool = False

    # ── audio ─────────────────────────────────────────────────────────
    sound_enabled: bool = True
    sound_volume: int = 70                 # 0-100

    # ── notifications ─────────────────────────────────────────────────
    notifications_enabled: bool = True
    do_not_disturb: bool = False

    # ── window ────────────────────────────────────────────────────────
    minimize_to_tray: bool = True
    window_x: int | None = None
    window_y: int | None = None
    window_width: int = 520
    window_height: int = 800
    always_on_top: bool = False
    compact_mode: bool = False


def load_settings() -> Settings:
    """Load settings from disk, falling back to defaults."""
    try:
        if SETTINGS_PATH.exists():
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            # Only use keys that exist in the dataclass
            valid_keys = {f.name for f in fields(Settings)}
            filtered = {k: v for k, v in data.items() if k in valid_keys}
            return Settings(**filtered)
    except Exception:
        pass
    return Settings()


def save_settings(settings: Settings) -> None:
    """Write settings to disk as JSON."""
    APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(asdict(settings), indent=2) + "\n",
        encoding="utf-8",
    )
