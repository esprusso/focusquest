"""Theme, companion, and title unlocks for FocusQuest.

Unlock Catalog
--------------
**Themes** (9) — visual skins that change the entire app look:

    Lv 1   Midnight    dark bg, warm orange ring  (default)
    Lv 3   Ocean       deep navy, teal/aqua accents
    Lv 5   Forest      dark green, gold/amber accents
    Lv 8   Sunset      dark warm tones, pink/coral/gold
    Lv 12  Neon        true black, neon cyan/magenta
    Lv 16  Aurora      dark + animated northern‑lights gradient
    Lv 20  Minimal     clean monochrome, respects macOS light/dark
    Lv 25  Synthwave   retro purple/pink, 80s grid aesthetic
    Lv 30  Galaxy      deep space with star particles

**Companions** (6) — small animated characters near the timer:

    Lv 1   Sprout      plant that grows during focus
    Lv 5   Ember       dancing flame
    Lv 10  Ripple      water droplet, expanding rings
    Lv 15  Pixel       retro pixel robot
    Lv 20  Nova        pulsing star
    Lv 25  Zen         lotus that opens petals each pomodoro

**Titles** (4) — earned by session count / streak milestones.

Persistence
-----------
Unlocks are stored in the ``Unlock`` table.  The ``UnlockManager`` handles
check‑and‑unlock logic, equipping, and querying what's available.

Registry
--------
``REGISTRY`` is a module‑level singleton that wraps every unlockable and
exposes look‑up helpers (``get``, ``next_upcoming``, ``teasers``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..database.db import get_session
from ..database.models import Unlock


# ── catalog dataclasses ──────────────────────────────────────────────────


@dataclass(frozen=True)
class ThemeDef:
    key: str
    name: str
    required_level: int
    description: str
    preview_description: str
    palette: dict[str, str]
    ring_colors: dict[str, tuple[str, str]]   # TimerState name → (primary, secondary)
    background_effect: str | None = None       # None | "aurora" | "galaxy"


@dataclass(frozen=True)
class CompanionDef:
    key: str
    name: str
    required_level: int
    description: str
    preview_description: str
    widget_class: str   # e.g. "SproutCompanion"


@dataclass(frozen=True)
class TitleDef:
    key: str
    name: str
    required_sessions: int
    description: str


# ── 9 themes with full palettes + per‑theme ring colours ────────────────

THEMES: list[ThemeDef] = [
    # ── 1. Midnight (default) ───────────────────────────────────────────
    ThemeDef(
        key="midnight",
        name="Midnight",
        required_level=1,
        description="The classic FocusQuest look.",
        preview_description="Dark background with warm orange ring accents",
        palette={
            "bg":           "#1A1A2E",
            "bg_secondary": "#232340",
            "surface":      "#2A2A4A",
            "accent":       "#CBA6F7",
            "accent2":      "#89B4FA",
            "text":         "#E2E2F0",
            "text_muted":   "#7A7A9A",
            "success":      "#A6E3A1",
            "warning":      "#F9E2AF",
            "danger":       "#F38BA8",
            "border":       "#313154",
        },
        ring_colors={
            "working":     ("#FF6B6B", "#FFA07A"),
            "short_break": ("#4ECDC4", "#44B09E"),
            "long_break":  ("#A18CD1", "#7B68EE"),
            "paused":      ("#6C7086", "#585B70"),
            "idle":        ("#4A4A5E", "#3A3A4E"),
        },
    ),

    # ── 2. Ocean ────────────────────────────────────────────────────────
    ThemeDef(
        key="ocean",
        name="Ocean",
        required_level=3,
        description="Deep navy background with teal/aqua accents.",
        preview_description="Calm blues to keep you focused",
        palette={
            "bg":           "#0A1628",
            "bg_secondary": "#112240",
            "surface":      "#1A3358",
            "accent":       "#89B4FA",
            "accent2":      "#74C7EC",
            "text":         "#E2E2F0",
            "text_muted":   "#6C8BBF",
            "success":      "#A6E3A1",
            "warning":      "#F9E2AF",
            "danger":       "#F38BA8",
            "border":       "#1E3A5F",
        },
        ring_colors={
            "working":     ("#4ECDC4", "#2CB5A8"),
            "short_break": ("#74C7EC", "#58A6D4"),
            "long_break":  ("#89B4FA", "#6C96E0"),
            "paused":      ("#4A6080", "#3A5070"),
            "idle":        ("#2A4060", "#1A3050"),
        },
    ),

    # ── 3. Forest ───────────────────────────────────────────────────────
    ThemeDef(
        key="forest",
        name="Forest",
        required_level=5,
        description="Dark green background with gold/amber accents.",
        preview_description="Nature‑inspired tones for deep work",
        palette={
            "bg":           "#0D1F0D",
            "bg_secondary": "#162616",
            "surface":      "#1E3A1E",
            "accent":       "#D4A626",
            "accent2":      "#94E2D5",
            "text":         "#E2E2F0",
            "text_muted":   "#6B8A6B",
            "success":      "#A6E3A1",
            "warning":      "#F9E2AF",
            "danger":       "#F38BA8",
            "border":       "#1E3A1E",
        },
        ring_colors={
            "working":     ("#D4A626", "#C49220"),
            "short_break": ("#6ABF6A", "#50A050"),
            "long_break":  ("#94E2D5", "#70C4B8"),
            "paused":      ("#4A6040", "#3A5030"),
            "idle":        ("#2A4020", "#1A3010"),
        },
    ),

    # ── 4. Sunset ───────────────────────────────────────────────────────
    ThemeDef(
        key="sunset",
        name="Sunset",
        required_level=8,
        description="Dark warm tones with pink/coral/gold gradients.",
        preview_description="Warm energy for evening focus sessions",
        palette={
            "bg":           "#1F0D0A",
            "bg_secondary": "#2E1510",
            "surface":      "#3D1A10",
            "accent":       "#FAB387",
            "accent2":      "#F38BA8",
            "text":         "#E2E2F0",
            "text_muted":   "#9A7060",
            "success":      "#A6E3A1",
            "warning":      "#F9E2AF",
            "danger":       "#F38BA8",
            "border":       "#3D1A10",
        },
        ring_colors={
            "working":     ("#F38BA8", "#FAB387"),
            "short_break": ("#FAB387", "#F9E2AF"),
            "long_break":  ("#CBA6F7", "#F38BA8"),
            "paused":      ("#7A5040", "#604030"),
            "idle":        ("#4A2A1A", "#3A1A0A"),
        },
    ),

    # ── 5. Neon ─────────────────────────────────────────────────────────
    ThemeDef(
        key="neon",
        name="Neon",
        required_level=12,
        description="True black background with neon cyan/magenta accents.",
        preview_description="Electric vibes on a pitch‑black canvas",
        palette={
            "bg":           "#050508",
            "bg_secondary": "#0A0A12",
            "surface":      "#12121E",
            "accent":       "#00FFFF",
            "accent2":      "#FF00FF",
            "text":         "#F0F0FF",
            "text_muted":   "#505070",
            "success":      "#00FF88",
            "warning":      "#FFFF00",
            "danger":       "#FF3366",
            "border":       "#1A1A2A",
        },
        ring_colors={
            "working":     ("#00FFFF", "#FF00FF"),
            "short_break": ("#00FF88", "#00CCFF"),
            "long_break":  ("#FF00FF", "#8B00FF"),
            "paused":      ("#303050", "#202040"),
            "idle":        ("#1A1A30", "#101020"),
        },
    ),

    # ── 6. Aurora ───────────────────────────────────────────────────────
    ThemeDef(
        key="aurora",
        name="Aurora",
        required_level=16,
        description="Dark theme with a subtle animated northern‑lights gradient.",
        preview_description="Shimmering greens and purples dance behind your timer",
        palette={
            "bg":           "#0A0F1A",
            "bg_secondary": "#101828",
            "surface":      "#182238",
            "accent":       "#66FFCC",
            "accent2":      "#9966FF",
            "text":         "#E8F0FF",
            "text_muted":   "#5A7090",
            "success":      "#66FFCC",
            "warning":      "#FFCC66",
            "danger":       "#FF6688",
            "border":       "#1E2E48",
        },
        ring_colors={
            "working":     ("#66FFCC", "#33CC99"),
            "short_break": ("#9966FF", "#6633CC"),
            "long_break":  ("#3399FF", "#66FFCC"),
            "paused":      ("#3A4A60", "#2A3A50"),
            "idle":        ("#1A2A40", "#0F1F30"),
        },
        background_effect="aurora",
    ),

    # ── 7. Minimal (macOS light/dark aware) ─────────────────────────────
    ThemeDef(
        key="minimal",
        name="Minimal",
        required_level=20,
        description="Clean monochrome theme that respects macOS appearance.",
        preview_description="Less is more — adapts to your system light/dark mode",
        palette={
            # Dark variant stored here; light variant in MINIMAL_LIGHT_PALETTE
            "bg":           "#1C1C1E",
            "bg_secondary": "#2C2C2E",
            "surface":      "#3A3A3C",
            "accent":       "#0A84FF",
            "accent2":      "#5E5CE6",
            "text":         "#F2F2F7",
            "text_muted":   "#8E8E93",
            "success":      "#30D158",
            "warning":      "#FF9F0A",
            "danger":       "#FF453A",
            "border":       "#38383A",
        },
        ring_colors={
            "working":     ("#007AFF", "#5856D6"),
            "short_break": ("#34C759", "#30D158"),
            "long_break":  ("#5856D6", "#AF52DE"),
            "paused":      ("#8E8E93", "#636366"),
            "idle":        ("#48484A", "#3A3A3C"),
        },
    ),

    # ── 8. Synthwave ────────────────────────────────────────────────────
    ThemeDef(
        key="synthwave",
        name="Synthwave",
        required_level=25,
        description="Retro purple/pink, 80s grid aesthetic.",
        preview_description="Neon grids and chrome sunsets — totally radical",
        palette={
            "bg":           "#1A0A2E",
            "bg_secondary": "#241040",
            "surface":      "#2E1850",
            "accent":       "#FF2E97",
            "accent2":      "#00F0FF",
            "text":         "#F0E0FF",
            "text_muted":   "#7A5A9A",
            "success":      "#00FF88",
            "warning":      "#FFDD00",
            "danger":       "#FF2E97",
            "border":       "#3A2060",
        },
        ring_colors={
            "working":     ("#FF2E97", "#FF6EC7"),
            "short_break": ("#00F0FF", "#00B8CC"),
            "long_break":  ("#9B59B6", "#FF2E97"),
            "paused":      ("#4A2A60", "#3A1A50"),
            "idle":        ("#2A1040", "#1A0830"),
        },
    ),

    # ── 9. Galaxy ───────────────────────────────────────────────────────
    ThemeDef(
        key="galaxy",
        name="Galaxy",
        required_level=30,
        description="Deep space background with subtle star particles.",
        preview_description="Focus among the stars — with twinkling constellations",
        palette={
            "bg":           "#050510",
            "bg_secondary": "#0A0A1E",
            "surface":      "#10102A",
            "accent":       "#B4BEFE",
            "accent2":      "#CBA6F7",
            "text":         "#E8E8FF",
            "text_muted":   "#5A5A80",
            "success":      "#A6E3A1",
            "warning":      "#F9E2AF",
            "danger":       "#F38BA8",
            "border":       "#1A1A34",
        },
        ring_colors={
            "working":     ("#CBA6F7", "#B4BEFE"),
            "short_break": ("#89B4FA", "#74C7EC"),
            "long_break":  ("#F5C2E7", "#CBA6F7"),
            "paused":      ("#3A3A5A", "#2A2A4A"),
            "idle":        ("#1A1A34", "#101024"),
        },
        background_effect="galaxy",
    ),
]


# Light palette variant for the "Minimal" theme when macOS is in light mode.
MINIMAL_LIGHT_PALETTE: dict[str, str] = {
    "bg":           "#F5F5F7",
    "bg_secondary": "#EAEAEC",
    "surface":      "#FFFFFF",
    "accent":       "#007AFF",
    "accent2":      "#5856D6",
    "text":         "#1D1D1F",
    "text_muted":   "#86868B",
    "success":      "#34C759",
    "warning":      "#FF9500",
    "danger":       "#FF3B30",
    "border":       "#D1D1D6",
}

MINIMAL_LIGHT_RING_COLORS: dict[str, tuple[str, str]] = {
    "working":     ("#007AFF", "#5856D6"),
    "short_break": ("#34C759", "#30D158"),
    "long_break":  ("#5856D6", "#AF52DE"),
    "paused":      ("#8E8E93", "#636366"),
    "idle":        ("#C7C7CC", "#AEAEB2"),
}


# ── 6 companions ────────────────────────────────────────────────────────

COMPANIONS: list[CompanionDef] = [
    CompanionDef(
        key="sprout", name="Sprout", required_level=1,
        description="A small plant that grows during focus sessions.",
        preview_description="Watch your little sprout grow with every minute of focus",
        widget_class="SproutCompanion",
    ),
    CompanionDef(
        key="ember", name="Ember", required_level=5,
        description="A little flame that dances while you work.",
        preview_description="A flickering flame that burns brighter as you focus",
        widget_class="EmberCompanion",
    ),
    CompanionDef(
        key="ripple", name="Ripple", required_level=10,
        description="A water droplet that creates expanding circles.",
        preview_description="Mesmerising ripples that expand with your concentration",
        widget_class="RippleCompanion",
    ),
    CompanionDef(
        key="pixel", name="Pixel", required_level=15,
        description="A retro pixel art robot with idle animations.",
        preview_description="A tiny 8‑bit buddy that types alongside you",
        widget_class="PixelCompanion",
    ),
    CompanionDef(
        key="nova", name="Nova", required_level=20,
        description="A small star that pulses and glows brighter as you focus.",
        preview_description="A celestial companion that shines with your effort",
        widget_class="NovaCompanion",
    ),
    CompanionDef(
        key="zen", name="Zen", required_level=25,
        description="A floating lotus that opens petals with each completed pomodoro.",
        preview_description="Inner peace, visualised — petals bloom as you complete rounds",
        widget_class="ZenCompanion",
    ),
]

# Backward‑compat alias
CHARACTERS = COMPANIONS


# ── 4 titles (session / streak milestones) ──────────────────────────────

TITLES: list[TitleDef] = [
    TitleDef("first_steps",  "First Steps",   1,   "Completed your first session."),
    TitleDef("on_a_roll",    "On a Roll",     10,  "10 sessions done!"),
    TitleDef("centurion",    "Centurion",     100, "100 sessions — legendary!"),
    TitleDef("week_warrior", "Week Warrior",  7,   "7‑day streak achieved."),
]


# ── theme look‑up helpers ───────────────────────────────────────────────

_THEME_MAP: dict[str, ThemeDef] = {t.key: t for t in THEMES}


def get_theme_def(key: str) -> ThemeDef | None:
    """Return the ThemeDef for *key*, or ``None``."""
    return _THEME_MAP.get(key)


# ── unlock registry ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class UnlockableItem:
    """Uniform wrapper around any unlockable for the collection UI."""
    key: str
    unlock_type: str           # "theme" | "companion" | "title"
    name: str
    description: str
    preview_description: str
    required_level: int        # 0 for title‑type (uses required_sessions instead)
    required_sessions: int     # 0 for theme/companion
    definition: ThemeDef | CompanionDef | TitleDef = field(repr=False)


class UnlockRegistry:
    """Single source of truth for every unlockable in the game.

    Populated at import time from ``THEMES``, ``COMPANIONS`` and ``TITLES``.
    """

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], UnlockableItem] = {}

        for t in THEMES:
            self._items[("theme", t.key)] = UnlockableItem(
                key=t.key, unlock_type="theme", name=t.name,
                description=t.description,
                preview_description=t.preview_description,
                required_level=t.required_level, required_sessions=0,
                definition=t,
            )

        for c in COMPANIONS:
            self._items[("companion", c.key)] = UnlockableItem(
                key=c.key, unlock_type="companion", name=c.name,
                description=c.description,
                preview_description=c.preview_description,
                required_level=c.required_level, required_sessions=0,
                definition=c,
            )

        for t in TITLES:
            self._items[("title", t.key)] = UnlockableItem(
                key=t.key, unlock_type="title", name=t.name,
                description=t.description,
                preview_description=t.description,
                required_level=0, required_sessions=t.required_sessions,
                definition=t,
            )

    # ── queries ─────────────────────────────────────────────────────

    def all_items(self) -> list[UnlockableItem]:
        return list(self._items.values())

    def get(self, unlock_type: str, key: str) -> UnlockableItem | None:
        return self._items.get((unlock_type, key))

    def items_by_type(self, unlock_type: str) -> list[UnlockableItem]:
        return [i for i in self._items.values() if i.unlock_type == unlock_type]

    def next_upcoming(self, current_level: int) -> UnlockableItem | None:
        """Return the lowest‑level unlockable the player hasn't reached yet."""
        candidates = [
            i for i in self._items.values()
            if i.required_level > current_level and i.unlock_type != "title"
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda i: i.required_level)

    def teasers(self, current_level: int, count: int = 3) -> list[UnlockableItem]:
        """Return the next *count* upcoming level‑gated unlockables."""
        candidates = sorted(
            (i for i in self._items.values()
             if i.required_level > current_level and i.unlock_type != "title"),
            key=lambda i: i.required_level,
        )
        return candidates[:count]


# Module‑level singleton
REGISTRY = UnlockRegistry()


# ── manager ─────────────────────────────────────────────────────────────


class UnlockManager:
    """Checks eligibility and records unlocks in the database."""

    def check_and_unlock(
        self, current_level: int, total_sessions: int,
    ) -> list[dict]:
        """Unlock everything the player has earned but hasn't received yet.

        Returns a list of ``{"type", "key", "name"}`` dicts for newly
        unlocked items so the UI can show notifications.
        """
        with get_session() as db:
            existing_keys: set[tuple[str, str]] = {
                (u.unlock_type, u.unlock_key)
                for u in db.query(Unlock).all()
            }

            new_unlocks: list[dict] = []

            for theme in THEMES:
                if current_level >= theme.required_level:
                    pair = ("theme", theme.key)
                    if pair not in existing_keys:
                        db.add(Unlock(
                            unlock_type="theme",
                            unlock_key=theme.key,
                            unlocked_at=datetime.now(),
                            is_equipped=(theme.key == "midnight"),
                        ))
                        new_unlocks.append({
                            "type": "theme",
                            "key": theme.key,
                            "name": theme.name,
                        })

            for comp in COMPANIONS:
                if current_level >= comp.required_level:
                    pair = ("companion", comp.key)
                    if pair not in existing_keys:
                        db.add(Unlock(
                            unlock_type="companion",
                            unlock_key=comp.key,
                            unlocked_at=datetime.now(),
                            is_equipped=(comp.key == "sprout"),
                        ))
                        new_unlocks.append({
                            "type": "companion",
                            "key": comp.key,
                            "name": comp.name,
                        })

            for title in TITLES:
                if total_sessions >= title.required_sessions:
                    pair = ("title", title.key)
                    if pair not in existing_keys:
                        db.add(Unlock(
                            unlock_type="title",
                            unlock_key=title.key,
                            unlocked_at=datetime.now(),
                            is_equipped=False,
                        ))
                        new_unlocks.append({
                            "type": "title",
                            "key": title.key,
                            "name": title.name,
                        })

            db.commit()
            return new_unlocks

    # ── equipped queries ────────────────────────────────────────────

    def get_equipped_theme(self) -> str:
        """Return the key of the currently equipped theme."""
        with get_session() as db:
            unlock = (
                db.query(Unlock)
                .filter_by(unlock_type="theme", is_equipped=True)
                .first()
            )
            return unlock.unlock_key if unlock else "midnight"

    def get_equipped_companion(self) -> str:
        """Return the key of the currently equipped companion."""
        with get_session() as db:
            unlock = (
                db.query(Unlock)
                .filter_by(unlock_type="companion", is_equipped=True)
                .first()
            )
            return unlock.unlock_key if unlock else "sprout"

    def get_all_unlocked(self) -> set[tuple[str, str]]:
        """Return set of ``(unlock_type, unlock_key)`` for every unlock."""
        with get_session() as db:
            return {
                (u.unlock_type, u.unlock_key)
                for u in db.query(Unlock).all()
            }

    def is_unlocked(self, unlock_type: str, key: str) -> bool:
        with get_session() as db:
            return (
                db.query(Unlock)
                .filter_by(unlock_type=unlock_type, unlock_key=key)
                .count() > 0
            )

    def equip(self, unlock_type: str, unlock_key: str) -> None:
        """Equip an unlock, un‑equipping any currently equipped item of the same type."""
        with get_session() as db:
            db.query(Unlock).filter_by(
                unlock_type=unlock_type, is_equipped=True,
            ).update({"is_equipped": False})
            db.query(Unlock).filter_by(
                unlock_type=unlock_type, unlock_key=unlock_key,
            ).update({"is_equipped": True})
            db.commit()
