"""Tests for the unlock system: registry, manager, themes, companions.

Covers:
- UnlockRegistry queries (items, types, next_upcoming, teasers)
- Theme palette / ring-colour completeness
- UnlockManager DB operations (check_and_unlock, equip, queries)
- Companion widget creation and state management
- DB migration helpers
"""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication

from focusquest.database.db import get_session
from focusquest.database.models import Unlock, UserProgress
from focusquest.gamification.unlockables import (
    REGISTRY, THEMES, COMPANIONS, TITLES,
    ThemeDef, CompanionDef, TitleDef,
    UnlockManager, UnlockableItem,
)
from focusquest.ui.styles import (
    get_palette, get_ring_colors, build_stylesheet, STATE_COLORS,
)
from focusquest.ui.companions import (
    create_companion, BaseCompanion,
    SproutCompanion, EmberCompanion, RippleCompanion,
    PixelCompanion, NovaCompanion, ZenCompanion,
    COMPANION_WIDGETS,
)
from focusquest.timer.engine import TimerState


# ═══════════════════════════════════════════════════════════════════════
#  REGISTRY TESTS
# ═══════════════════════════════════════════════════════════════════════


class TestRegistry:
    """Verify the global REGISTRY contains all expected items."""

    def test_contains_9_themes(self):
        themes = REGISTRY.items_by_type("theme")
        assert len(themes) == 9

    def test_contains_6_companions(self):
        companions = REGISTRY.items_by_type("companion")
        assert len(companions) == 6

    def test_contains_4_titles(self):
        titles = REGISTRY.items_by_type("title")
        assert len(titles) == 4

    def test_total_items(self):
        assert len(REGISTRY.all_items()) == 9 + 6 + 4

    def test_get_existing_theme(self):
        item = REGISTRY.get("theme", "midnight")
        assert item is not None
        assert item.name == "Midnight"
        assert item.required_level == 1

    def test_get_existing_companion(self):
        item = REGISTRY.get("companion", "ember")
        assert item is not None
        assert item.name == "Ember"
        assert item.required_level == 5

    def test_get_nonexistent_returns_none(self):
        assert REGISTRY.get("theme", "nonexistent") is None
        assert REGISTRY.get("companion", "nonexistent") is None

    def test_next_upcoming_at_level_1(self):
        item = REGISTRY.next_upcoming(1)
        assert item is not None
        # Should be the lowest-level item above 1 — Ocean at 3
        assert item.required_level == 3

    def test_next_upcoming_at_level_30(self):
        # All items unlocked
        assert REGISTRY.next_upcoming(30) is None

    def test_next_upcoming_at_level_15(self):
        item = REGISTRY.next_upcoming(15)
        assert item is not None
        assert item.required_level == 16  # Aurora

    def test_teasers_returns_correct_count(self):
        teasers = REGISTRY.teasers(1, count=3)
        assert len(teasers) == 3
        # Sorted ascending
        levels = [t.required_level for t in teasers]
        assert levels == sorted(levels)

    def test_teasers_at_high_level(self):
        teasers = REGISTRY.teasers(28, count=5)
        # Only Galaxy (30) left — 1 item max
        assert len(teasers) <= 2  # galaxy + maybe synthwave if counted


class TestThemeCatalog:
    """Verify theme definitions are complete and well‑formed."""

    def test_theme_list_matches_count(self):
        assert len(THEMES) == 9

    def test_all_themes_have_required_palette_keys(self):
        required_keys = {
            "bg", "bg_secondary", "surface", "accent", "accent2",
            "text", "text_muted", "success", "warning", "danger", "border",
        }
        for theme in THEMES:
            missing = required_keys - set(theme.palette.keys())
            assert not missing, f"{theme.key} missing palette keys: {missing}"

    def test_all_themes_have_working_ring_color(self):
        for theme in THEMES:
            assert "working" in theme.ring_colors, (
                f"{theme.key} missing 'working' ring color"
            )

    def test_all_themes_have_5_ring_states(self):
        expected = {"working", "short_break", "long_break", "paused", "idle"}
        for theme in THEMES:
            assert set(theme.ring_colors.keys()) == expected, (
                f"{theme.key} has unexpected ring_colors keys"
            )

    def test_theme_levels_are_ascending(self):
        levels = [t.required_level for t in THEMES]
        assert levels == sorted(levels)

    def test_midnight_is_level_1(self):
        assert THEMES[0].key == "midnight"
        assert THEMES[0].required_level == 1

    def test_galaxy_is_level_30(self):
        assert THEMES[-1].key == "galaxy"
        assert THEMES[-1].required_level == 30

    def test_aurora_has_bg_effect(self):
        aurora = next(t for t in THEMES if t.key == "aurora")
        assert aurora.background_effect == "aurora"

    def test_galaxy_has_bg_effect(self):
        galaxy = next(t for t in THEMES if t.key == "galaxy")
        assert galaxy.background_effect == "galaxy"

    def test_most_themes_have_no_bg_effect(self):
        count = sum(1 for t in THEMES if t.background_effect is not None)
        assert count == 2  # only aurora and galaxy


class TestCompanionCatalog:
    def test_companion_count(self):
        assert len(COMPANIONS) == 6

    def test_companion_levels_ascending(self):
        levels = [c.required_level for c in COMPANIONS]
        assert levels == sorted(levels)

    def test_sprout_is_default(self):
        assert COMPANIONS[0].key == "sprout"
        assert COMPANIONS[0].required_level == 1


# ═══════════════════════════════════════════════════════════════════════
#  THEME PALETTE / STYLE TESTS
# ═══════════════════════════════════════════════════════════════════════


class TestThemePalettes:
    """Verify ``get_palette`` and ``get_ring_colors`` work for all themes."""

    def test_get_palette_midnight(self):
        p = get_palette("midnight")
        assert p["bg"] == "#1A1A2E"
        assert p["accent"] == "#CBA6F7"

    def test_get_palette_unknown_returns_default(self):
        p = get_palette("nonexistent")
        assert p["bg"] == "#1A1A2E"  # same as default

    def test_get_palette_ocean(self):
        p = get_palette("ocean")
        assert p["bg"] == "#0A1628"

    def test_get_ring_colors_midnight(self):
        rc = get_ring_colors("midnight")
        assert TimerState.WORKING in rc
        assert rc[TimerState.WORKING] == ("#FF6B6B", "#FFA07A")

    def test_get_ring_colors_neon(self):
        rc = get_ring_colors("neon")
        assert rc[TimerState.WORKING] == ("#00FFFF", "#FF00FF")

    def test_get_ring_colors_unknown_falls_back(self):
        rc = get_ring_colors("nonexistent")
        assert rc == dict(STATE_COLORS)

    def test_build_stylesheet_all_themes_no_error(self, qapp):
        """Build a QSS string for every theme — no exceptions."""
        for theme in THEMES:
            palette = get_palette(theme.key)
            qss = build_stylesheet(palette)
            assert len(qss) > 100  # non-trivial stylesheet


# ═══════════════════════════════════════════════════════════════════════
#  UNLOCK MANAGER TESTS
# ═══════════════════════════════════════════════════════════════════════


class TestUnlockManager:
    """Database‑backed unlock operations."""

    def test_check_and_unlock_seeds_defaults(self):
        mgr = UnlockManager()
        new = mgr.check_and_unlock(1, 0)
        # Should seed midnight theme + sprout companion + first_steps title (1 session → 0 sessions, so no title)
        keys = {(u["type"], u["key"]) for u in new}
        assert ("theme", "midnight") in keys
        assert ("companion", "sprout") in keys

    def test_get_equipped_theme_default(self):
        mgr = UnlockManager()
        mgr.check_and_unlock(1, 0)
        assert mgr.get_equipped_theme() == "midnight"

    def test_get_equipped_companion_default(self):
        mgr = UnlockManager()
        mgr.check_and_unlock(1, 0)
        assert mgr.get_equipped_companion() == "sprout"

    def test_level_5_unlocks_ocean_forest_ember(self):
        mgr = UnlockManager()
        mgr.check_and_unlock(1, 0)  # seed
        new = mgr.check_and_unlock(5, 2)
        keys = {(u["type"], u["key"]) for u in new}
        assert ("theme", "ocean") in keys
        assert ("theme", "forest") in keys
        assert ("companion", "ember") in keys

    def test_equip_theme_switches(self):
        mgr = UnlockManager()
        mgr.check_and_unlock(5, 0)
        mgr.equip("theme", "ocean")
        assert mgr.get_equipped_theme() == "ocean"

    def test_equip_companion_switches(self):
        mgr = UnlockManager()
        mgr.check_and_unlock(5, 0)
        mgr.equip("companion", "ember")
        assert mgr.get_equipped_companion() == "ember"

    def test_is_unlocked_true(self):
        mgr = UnlockManager()
        mgr.check_and_unlock(1, 0)
        assert mgr.is_unlocked("theme", "midnight") is True

    def test_is_unlocked_false(self):
        mgr = UnlockManager()
        mgr.check_and_unlock(1, 0)
        assert mgr.is_unlocked("theme", "neon") is False

    def test_get_all_unlocked(self):
        mgr = UnlockManager()
        mgr.check_and_unlock(5, 2)
        unlocked = mgr.get_all_unlocked()
        assert ("theme", "midnight") in unlocked
        assert ("theme", "ocean") in unlocked
        assert ("companion", "sprout") in unlocked

    def test_check_and_unlock_idempotent(self):
        mgr = UnlockManager()
        first = mgr.check_and_unlock(5, 2)
        second = mgr.check_and_unlock(5, 2)
        assert len(second) == 0  # all already unlocked

    def test_check_and_unlock_returns_only_new(self):
        mgr = UnlockManager()
        mgr.check_and_unlock(1, 0)
        new = mgr.check_and_unlock(3, 1)
        # Should only return Ocean (level 3), first_steps title (1 session)
        keys = {(u["type"], u["key"]) for u in new}
        assert ("theme", "ocean") in keys
        assert ("theme", "midnight") not in keys  # already existed


# ═══════════════════════════════════════════════════════════════════════
#  COMPANION WIDGET TESTS
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.usefixtures("qapp")
class TestCompanionWidgets:
    """Test companion creation and basic lifecycle."""

    def test_create_sprout(self):
        w = create_companion("sprout")
        assert isinstance(w, SproutCompanion)

    def test_create_all_keys(self):
        for key in ["sprout", "ember", "ripple", "pixel", "nova", "zen"]:
            w = create_companion(key)
            assert isinstance(w, BaseCompanion)
            assert w.width() == BaseCompanion.WIDGET_WIDTH
            assert w.height() == BaseCompanion.WIDGET_HEIGHT

    def test_unknown_key_defaults_to_sprout(self):
        w = create_companion("nonexistent")
        assert isinstance(w, SproutCompanion)

    def test_set_state_idle(self):
        w = create_companion("ember")
        w.set_state("idle")
        assert w._state == "idle"

    def test_set_state_focus(self):
        w = create_companion("nova")
        w.set_state("focus")
        assert w._state == "focus"

    def test_set_state_sleep(self):
        w = create_companion("pixel")
        w.set_state("sleep")
        assert w._state == "sleep"

    def test_trigger_celebrate(self):
        w = create_companion("zen")
        w.set_state("focus")
        w.trigger_celebrate()
        assert w._state == "celebrate"
        assert w._prev_state == "focus"

    def test_set_session_progress(self):
        w = create_companion("sprout")
        w.set_session_progress(0.5)
        assert w._session_progress == 0.5

    def test_session_progress_clamped(self):
        w = create_companion("sprout")
        w.set_session_progress(1.5)
        assert w._session_progress == 1.0
        w.set_session_progress(-0.5)
        assert w._session_progress == 0.0

    def test_companion_widget_map_complete(self):
        """Every CompanionDef.widget_class has a matching entry."""
        for comp in COMPANIONS:
            assert comp.key in COMPANION_WIDGETS, (
                f"Companion {comp.key} not in COMPANION_WIDGETS"
            )

    def test_paint_no_crash(self):
        """Call repaint on each companion in each state — no exceptions."""
        for key in COMPANION_WIDGETS:
            w = create_companion(key)
            for state in ["idle", "focus", "celebrate", "sleep"]:
                w.set_state(state) if state != "celebrate" else w.trigger_celebrate()
                w.repaint()  # Should not crash


# ═══════════════════════════════════════════════════════════════════════
#  DB MIGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════


class TestMigrations:
    """Test that old‑format DB rows are renamed correctly."""

    def test_old_character_type_migrated(self):
        """Insert an old 'character' row and verify it becomes 'companion'."""
        with get_session() as db:
            db.add(Unlock(
                unlock_type="character",
                unlock_key="apprentice",
                is_equipped=True,
            ))
            db.commit()

        # Run migrations
        from focusquest.database.db import _get_engine, _run_migrations
        _run_migrations(_get_engine())

        with get_session() as db:
            row = db.query(Unlock).filter_by(unlock_key="sprout").first()
            assert row is not None
            assert row.unlock_type == "companion"

    def test_old_theme_key_migrated(self):
        """Insert an old 'default' theme and verify it becomes 'midnight'."""
        with get_session() as db:
            db.add(Unlock(
                unlock_type="theme",
                unlock_key="default",
                is_equipped=True,
            ))
            db.commit()

        from focusquest.database.db import _get_engine, _run_migrations
        _run_migrations(_get_engine())

        with get_session() as db:
            row = db.query(Unlock).filter_by(
                unlock_type="theme", unlock_key="midnight",
            ).first()
            assert row is not None
            assert row.is_equipped is True
