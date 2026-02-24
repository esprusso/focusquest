"""Sound synthesis and playback using numpy + QSoundEffect.

All sounds are generated programmatically as WAV files using sine-wave
synthesis with ADSR envelopes.  Files are cached to disk so subsequent
app launches are instant.

Sound names
-----------
- ``session_start``  — short ascending chime (3 notes)
- ``session_complete`` — satisfying achievement arpeggio
- ``break_start``    — soft meditation bell
- ``break_warning``  — gentle double-tap at 1 min remaining
- ``level_up``       — distinct celebratory fanfare
- ``click``          — subtle button click
"""

from __future__ import annotations

import io
import struct
import wave
from pathlib import Path

import numpy as np

from PyQt6.QtCore import QObject, QUrl
from PyQt6.QtMultimedia import QSoundEffect


# ── paths ────────────────────────────────────────────────────────────────

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "FocusQuest"
SOUNDS_DIR = APP_SUPPORT_DIR / "sounds"

SOUND_NAMES = (
    "session_start",
    "session_complete",
    "break_start",
    "break_warning",
    "level_up",
    "click",
)

SAMPLE_RATE = 44100


# ═══════════════════════════════════════════════════════════════════════════
#  WAV SYNTHESIS HELPERS
# ═══════════════════════════════════════════════════════════════════════════


def _make_envelope(
    length: int,
    attack: int = 200,
    decay: int = 400,
    sustain_level: float = 0.7,
    release: int = 800,
) -> np.ndarray:
    """ADSR envelope (all durations in samples)."""
    env = np.ones(length, dtype=np.float64)
    # Attack
    a = min(attack, length)
    if a > 0:
        env[:a] = np.linspace(0.0, 1.0, a)
    # Decay
    d_end = min(a + decay, length)
    if decay > 0 and d_end > a:
        env[a:d_end] = np.linspace(1.0, sustain_level, d_end - a)
    # Sustain
    s_end = max(length - release, d_end)
    if s_end > d_end:
        env[d_end:s_end] = sustain_level
    # Release
    if release > 0 and s_end < length:
        env[s_end:] = np.linspace(sustain_level, 0.0, length - s_end)
    return env


def _sine(freq: float, duration_s: float) -> np.ndarray:
    """Pure sine wave at *freq* Hz for *duration_s* seconds."""
    t = np.linspace(0, duration_s, int(SAMPLE_RATE * duration_s), endpoint=False)
    return np.sin(2 * np.pi * freq * t)


def _to_wav_bytes(samples: np.ndarray) -> bytes:
    """Convert a float64 numpy array (-1..1) to 16-bit PCM WAV bytes."""
    # Clip and scale
    samples = np.clip(samples, -1.0, 1.0)
    int_samples = (samples * 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(int_samples.tobytes())
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
#  SOUND GENERATORS
# ═══════════════════════════════════════════════════════════════════════════


def _generate_chime() -> bytes:
    """Session start — 3 ascending notes (C5→E5→G5), uplifting."""
    notes = [523.25, 659.25, 783.99]  # C5, E5, G5
    note_dur = 0.12
    gap = 0.03
    parts: list[np.ndarray] = []
    for freq in notes:
        tone = _sine(freq, note_dur) * 0.6
        env = _make_envelope(len(tone), attack=100, decay=200, sustain_level=0.4, release=300)
        parts.append(tone * env)
        parts.append(np.zeros(int(SAMPLE_RATE * gap)))
    # Add gentle tail
    parts.append(np.zeros(int(SAMPLE_RATE * 0.05)))
    return _to_wav_bytes(np.concatenate(parts))


def _generate_achievement() -> bytes:
    """Session complete — bright celebratory arpeggio (C5→E5→G5→C6)."""
    notes = [523.25, 659.25, 783.99, 1046.50]  # C5, E5, G5, C6
    note_dur = 0.10
    gap = 0.02
    parts: list[np.ndarray] = []
    for i, freq in enumerate(notes):
        tone = _sine(freq, note_dur) * 0.5
        # Last note held longer with reverb tail
        if i == len(notes) - 1:
            tone = _sine(freq, 0.35) * 0.5
            env = _make_envelope(len(tone), attack=80, decay=300, sustain_level=0.5, release=600)
        else:
            env = _make_envelope(len(tone), attack=60, decay=150, sustain_level=0.3, release=200)
        parts.append(tone * env)
        if i < len(notes) - 1:
            parts.append(np.zeros(int(SAMPLE_RATE * gap)))
    return _to_wav_bytes(np.concatenate(parts))


def _generate_bell() -> bytes:
    """Break start — soft meditation bell (A4, 440Hz), slow attack, long decay."""
    duration = 1.0
    base = _sine(440.0, duration) * 0.35
    # Add subtle overtone for richness
    overtone = _sine(880.0, duration) * 0.08
    combined = base + overtone
    env = _make_envelope(
        len(combined),
        attack=int(SAMPLE_RATE * 0.08),
        decay=int(SAMPLE_RATE * 0.3),
        sustain_level=0.25,
        release=int(SAMPLE_RATE * 0.55),
    )
    return _to_wav_bytes(combined * env)


def _generate_double_tap() -> bytes:
    """Break warning — gentle double-tap (800Hz), 80ms apart."""
    tap_dur = 0.04
    gap = 0.08
    tap = _sine(800.0, tap_dur) * 0.35
    env = _make_envelope(len(tap), attack=40, decay=100, sustain_level=0.2, release=200)
    tap = tap * env
    silence = np.zeros(int(SAMPLE_RATE * gap))
    return _to_wav_bytes(np.concatenate([tap, silence, tap, np.zeros(int(SAMPLE_RATE * 0.05))]))


def _generate_fanfare() -> bytes:
    """Level up — distinct fanfare (G4→B4→D5→G5), wider intervals, longer."""
    notes = [392.00, 493.88, 587.33, 783.99]  # G4, B4, D5, G5
    note_dur = 0.15
    gap = 0.03
    parts: list[np.ndarray] = []
    for i, freq in enumerate(notes):
        if i == len(notes) - 1:
            # Final note held longer with rich sustain
            tone = _sine(freq, 0.5) * 0.55
            overtone = _sine(freq * 2, 0.5) * 0.1
            combined = tone + overtone
            env = _make_envelope(len(combined), attack=100, decay=400, sustain_level=0.5, release=800)
            parts.append(combined * env)
        else:
            tone = _sine(freq, note_dur) * 0.5
            env = _make_envelope(len(tone), attack=80, decay=200, sustain_level=0.4, release=250)
            parts.append(tone * env)
            parts.append(np.zeros(int(SAMPLE_RATE * gap)))
    return _to_wav_bytes(np.concatenate(parts))


def _generate_click() -> bytes:
    """Button click — very short noise burst, subtle."""
    duration = 0.015
    n_samples = int(SAMPLE_RATE * duration)
    # Short high-frequency tick
    tick = _sine(1200.0, duration) * 0.2
    env = _make_envelope(n_samples, attack=20, decay=50, sustain_level=0.0, release=n_samples - 70)
    # Pad with silence so QSoundEffect doesn't clip
    padded = np.concatenate([tick * env, np.zeros(int(SAMPLE_RATE * 0.03))])
    return _to_wav_bytes(padded)


# Map sound names to generator functions
_GENERATORS: dict[str, callable] = {
    "session_start": _generate_chime,
    "session_complete": _generate_achievement,
    "break_start": _generate_bell,
    "break_warning": _generate_double_tap,
    "level_up": _generate_fanfare,
    "click": _generate_click,
}


# ═══════════════════════════════════════════════════════════════════════════
#  SOUND MANAGER
# ═══════════════════════════════════════════════════════════════════════════


class SoundManager(QObject):
    """Manages sound synthesis, caching, and playback.

    Usage::

        mgr = SoundManager(parent=self)
        mgr.set_volume(70)
        mgr.play("session_start")
    """

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        sounds_dir: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self._enabled = True
        self._volume = 0.7  # 0.0–1.0
        self._sounds_dir = sounds_dir or SOUNDS_DIR
        self._effects: dict[str, QSoundEffect] = {}

        self._ensure_wav_files()
        self._load_effects()

    # ── public API ────────────────────────────────────────────────────

    def set_volume(self, level: int) -> None:
        """Set volume (0-100).  Updates all loaded effects."""
        self._volume = max(0, min(level, 100)) / 100.0
        for effect in self._effects.values():
            effect.setVolume(self._volume)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def play(self, name: str) -> None:
        """Play a sound by name.  No-op if disabled or name unknown."""
        if not self._enabled:
            return
        effect = self._effects.get(name)
        if effect is not None:
            effect.play()

    @property
    def volume(self) -> int:
        """Current volume as 0-100 integer."""
        return round(self._volume * 100)

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ── internal ──────────────────────────────────────────────────────

    def _ensure_wav_files(self) -> None:
        """Generate any missing WAV files to the cache directory."""
        self._sounds_dir.mkdir(parents=True, exist_ok=True)
        for name, gen_fn in _GENERATORS.items():
            path = self._sounds_dir / f"{name}.wav"
            if not path.exists():
                path.write_bytes(gen_fn())

    def _load_effects(self) -> None:
        """Create QSoundEffect instances from cached WAV files."""
        for name in SOUND_NAMES:
            path = self._sounds_dir / f"{name}.wav"
            if path.exists():
                effect = QSoundEffect(self)
                effect.setSource(QUrl.fromLocalFile(str(path)))
                effect.setVolume(self._volume)
                self._effects[name] = effect
