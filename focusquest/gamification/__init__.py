"""Gamification package."""

from .xp import (
    XPEngine,
    level_for_xp,
    xp_for_level,
    xp_to_next_level,
    xp_in_current_level,
    title_for_level,
    LEVEL_TITLES,
)
from .unlockables import (
    UnlockManager,
    UnlockRegistry,
    REGISTRY,
    THEMES,
    COMPANIONS,
    CHARACTERS,
    TITLES,
    ThemeDef,
    CompanionDef,
    TitleDef,
    UnlockableItem,
)

__all__ = [
    "XPEngine",
    "level_for_xp",
    "xp_for_level",
    "xp_to_next_level",
    "xp_in_current_level",
    "title_for_level",
    "LEVEL_TITLES",
    "UnlockManager",
    "UnlockRegistry",
    "REGISTRY",
    "THEMES",
    "COMPANIONS",
    "CHARACTERS",
    "TITLES",
    "ThemeDef",
    "CompanionDef",
    "TitleDef",
    "UnlockableItem",
]
