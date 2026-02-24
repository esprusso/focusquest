# FocusQuest

A gamified Pomodoro timer for macOS, built with Python and PyQt6.

Designed with ADHD-friendly features: a gentle start screen, positive-only messaging, micro-sessions for low-energy days, flow-state extensions, and streak tracking that never guilt-trips.

## Requirements

- **macOS 13+** (Apple Silicon recommended)
- **Python 3.11+**
- PyQt6, SQLAlchemy, numpy

## Quick Start

```bash
pip install -r requirements.txt
python -m focusquest
```

Or equivalently:

```bash
python main.py
```

## Features

### Timer
- **Pomodoro Cycle** — 25 / 5 / 15 min work / short-break / long-break (configurable)
- **Micro Sessions** — 10 or 15 min for low-energy days
- **Flow State Extension** — +5 min button when you're in the zone
- **Auto-Advance** — optionally start the next session automatically

### Gamification
- **XP & Leveling** — earn XP for completed sessions with streak, cycle, and daily kickoff bonuses
- **9 Themes** — Midnight, Ocean, Forest, Sunset, Neon, Aurora, Minimal, Synthwave, Galaxy
- **6 Companions** — animated characters that react to your focus state
- **4 Titles** — milestone rewards for session count and streaks
- **Collection Panel** — browse and equip unlocked themes and companions

### Stats Dashboard
- Today's summary ring, weekly bar chart, monthly heatmap, all-time stats
- Level progress roadmap with upcoming unlock teasers
- All charts are custom QPainter widgets — no matplotlib needed

### macOS Integration
- **Native Menu Bar** — FocusQuest / View / Window menus with standard macOS roles
- **System Tray** — timer persists in the menu bar when you close the window
- **Desktop Notifications** — session start/end alerts via Notification Center
- **Sound Effects** — synthesized audio cues (numpy WAV generation, no bundled files)
- **Dock Icon** — generated at runtime
- **Appearance Aware** — Minimal theme respects macOS light/dark mode

### Keyboard Shortcuts
| Shortcut | Action |
|----------|--------|
| `Space` | Start / Pause / Resume |
| `Escape` | Stop / Reset |
| `Cmd+,` | Settings |
| `Cmd+S` | Stats tab |
| `Cmd+T` | Cycle themes |
| `Cmd+M` | Minimize |
| `Cmd+W` | Close window |
| `Cmd+Q` | Quit (with confirmation if timer is running) |

### ADHD-Friendly Design
- **Gentle Start** — welcoming screen with streak info, cumulative progress, and next unlock teaser
- **Positive-Only Messaging** — no "you broke your streak" or guilt language anywhere
- **Session History** — last 5 today's sessions below the timer with clickable labels for quick reuse
- **Compact Mode** — shrink to just the ring and time for minimal desktop footprint
- **Always on Top** — keep the timer visible while working

## Configuration

Settings are accessible via `Cmd+,` or the gear icon. Includes:

- Timer durations and rounds per cycle
- Auto-start work/break sessions
- Sound on/off and volume
- Notifications and Do Not Disturb
- Minimize to tray on close
- Always on top
- Compact mode

## Data Storage

All data persists at `~/Library/Application Support/FocusQuest/`:

| File | Purpose |
|------|---------|
| `focusquest.db` | SQLite database (sessions, progress, daily stats, unlocks) |
| `settings.json` | User preferences |
| `sounds/*.wav` | Cached WAV files (generated on first run) |

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
python -m focusquest

# Run the test suite (326 tests)
python -m pytest tests/ -v
```

### Project Structure

```
focusquest/
  __init__.py
  __main__.py          # Module entry point
  app.py               # Main window, wiring, menu bar
  settings.py          # JSON config persistence
  audio/
    sounds.py          # Numpy WAV synthesis + QSoundEffect playback
  database/
    db.py              # SQLAlchemy engine, session factory, migrations
    models.py          # ORM models (Session, UserProgress, DailyStats, Unlock)
  gamification/
    xp.py              # XP calculation engine with bonuses
    unlockables.py     # Theme/companion/title catalog + UnlockManager
  timer/
    engine.py          # QTimer-based state machine with signals
  ui/
    background_effects.py  # Aurora + Galaxy animated backgrounds
    collection_panel.py    # Browse/equip unlocked items
    companions.py          # 6 animated companion widgets
    gentle_start.py        # Welcome overlay
    progress_ring.py       # Gradient progress ring (QPainter)
    session_history.py     # Today's recent sessions
    settings_dialog.py     # Preferences modal
    stats_widget.py        # Full stats dashboard
    styles.py              # Theme palettes + stylesheet generation
    timer_widget.py        # Timer display with controls
    unlock_popup.py        # New unlock celebration
    xp_toast.py            # Floating XP notification
tests/
  conftest.py          # Shared fixtures (QApp, in-memory DB, engines)
  test_engine.py       # Timer engine state machine tests
  test_xp.py           # XP calculation and persistence tests
  test_stats.py        # Stats widget and chart tests
  test_unlockables.py  # Unlock catalog and manager tests
  test_sounds.py       # Sound generation and settings tests
  test_polish.py       # Polish pass tests (shortcuts, compact, history, etc.)
```

## Packaging as .app

To create a standalone macOS application bundle:

```bash
pip install py2app
python setup.py py2app
```

The `.app` bundle will be created in the `dist/` directory.

## Tech Stack

- **Python 3.12** — core language
- **PyQt6** — UI framework (widgets, QPainter, signals/slots, multimedia)
- **SQLAlchemy 2.0** — ORM with SQLite backend
- **numpy** — WAV audio synthesis (sine waves with ADSR envelopes)

## License

MIT
