"""Collection tab — browse and equip unlocked themes, companions, and titles.

Layout (scrollable):
    - "Themes" header + 3‑column grid of theme cards
    - "Companions" header + 3‑column grid of companion cards
    - "Titles" header + 2‑column grid of title cards

Card states:
    locked    → dark silhouette, padlock icon, "Unlocks at Lv. X"
    unlocked  → mini preview, name, pointing‑hand cursor
    equipped  → accent border, green checkmark badge
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QPainterPath
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLabel,
    QScrollArea, QFrame, QSizePolicy,
)

from ..gamification.unlockables import (
    REGISTRY, UnlockManager, UnlockableItem,
    ThemeDef, CompanionDef,
)


# ── unlock card ─────────────────────────────────────────────────────────


class _UnlockCard(QFrame):
    """A single card in the collection grid."""

    clicked = pyqtSignal()

    def __init__(
        self,
        item: UnlockableItem,
        *,
        is_unlocked: bool,
        is_equipped: bool,
        accent: str = "#CBA6F7",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._item = item
        self._is_unlocked = is_unlocked
        self._is_equipped = is_equipped
        self._accent = accent

        self.setFixedSize(148, 100)
        self.setObjectName("")  # don't inherit #card styles

        if is_unlocked and not is_equipped:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif not is_unlocked:
            self.setCursor(Qt.CursorShape.ForbiddenCursor)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if self._is_unlocked and not self._is_equipped:
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        rect = QRectF(1, 1, w - 2, h - 2)

        if self._is_unlocked:
            self._paint_unlocked(painter, rect)
        else:
            self._paint_locked(painter, rect)

        painter.end()

    def _paint_unlocked(self, painter: QPainter, rect: QRectF) -> None:
        # Background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#232340"))
        painter.drawRoundedRect(rect, 10, 10)

        # Border (highlight if equipped)
        if self._is_equipped:
            painter.setPen(QPen(QColor(self._accent), 2))
        else:
            painter.setPen(QPen(QColor("#313154"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 10, 10)

        # Preview area
        item = self._item
        if isinstance(item.definition, ThemeDef):
            self._paint_theme_preview(painter, item.definition)
        elif isinstance(item.definition, CompanionDef):
            self._paint_companion_preview(painter)

        # Name
        font = QFont()
        font.setPixelSize(11)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor("#E2E2F0"))
        name_rect = QRectF(8, rect.height() - 22, rect.width() - 16, 18)
        painter.drawText(
            name_rect,
            Qt.AlignmentFlag.AlignCenter,
            item.name,
        )

        # Equipped badge
        if self._is_equipped:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#A6E3A1"))
            painter.drawEllipse(QPointF(rect.width() - 14, 14), 7, 7)
            # Checkmark
            painter.setPen(QPen(QColor("#1A1A2E"), 2))
            painter.drawLine(
                QPointF(rect.width() - 17, 14),
                QPointF(rect.width() - 14.5, 17),
            )
            painter.drawLine(
                QPointF(rect.width() - 14.5, 17),
                QPointF(rect.width() - 10, 11),
            )

    def _paint_theme_preview(
        self, painter: QPainter, theme: ThemeDef,
    ) -> None:
        # Colour swatch
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.palette.get("bg", "#1A1A2E")))
        painter.drawRoundedRect(QRectF(14, 12, 50, 30), 6, 6)

        # Mini ring preview
        ring_color = theme.ring_colors.get("working", ("#FF6B6B", "#FFA07A"))
        painter.setPen(QPen(QColor(ring_color[0]), 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(100, 30), 14, 14)

        # Accent dot
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.palette.get("accent", "#CBA6F7")))
        painter.drawEllipse(QPointF(75, 30), 5, 5)

    def _paint_companion_preview(self, painter: QPainter) -> None:
        # Simple silhouette icon
        cx, cy = 74, 35
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._accent))
        painter.setOpacity(0.6)
        painter.drawEllipse(QPointF(cx, cy), 12, 12)
        painter.setOpacity(1.0)

        # Tiny companion icon
        font = QFont()
        font.setPixelSize(16)
        painter.setFont(font)
        painter.setPen(QColor("#E2E2F0"))

        _icons = {
            "sprout": "\u2618",   # shamrock
            "ember":  "\u2668",   # hot springs / flame-like
            "ripple": "\u2248",   # approximately equal (waves)
            "pixel":  "\u2689",   # filled square
            "nova":   "\u2605",   # star
            "zen":    "\u2740",   # flower
        }
        icon = _icons.get(self._item.key, "\u2022")
        painter.drawText(
            QRectF(cx - 10, cy - 10, 20, 20),
            Qt.AlignmentFlag.AlignCenter,
            icon,
        )

    def _paint_locked(self, painter: QPainter, rect: QRectF) -> None:
        # Dark background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(26, 26, 46, 200))
        painter.drawRoundedRect(rect, 10, 10)

        # Subtle border
        painter.setPen(QPen(QColor("#232340"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 10, 10)

        # Padlock icon (drawn with paths)
        cx = rect.width() / 2
        cy = 32
        # Lock body
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#4A4A5E"))
        painter.drawRoundedRect(QRectF(cx - 8, cy, 16, 12), 2, 2)
        # Lock shackle
        painter.setPen(QPen(QColor("#4A4A5E"), 2.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(
            QRectF(cx - 5, cy - 9, 10, 12),
            0, 180 * 16,
        )

        # "Unlocks at Lv. X" text
        font = QFont()
        font.setPixelSize(10)
        painter.setFont(font)
        painter.setPen(QColor("#7A7A9A"))

        item = self._item
        if item.unlock_type == "title":
            text = f"{item.required_sessions} sessions"
        else:
            text = f"Unlocks at Lv. {item.required_level}"

        painter.drawText(
            QRectF(4, rect.height() - 32, rect.width() - 8, 14),
            Qt.AlignmentFlag.AlignCenter,
            text,
        )

        # Name (dimmed)
        font.setPixelSize(11)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor("#4A4A5E"))
        painter.drawText(
            QRectF(8, rect.height() - 20, rect.width() - 16, 18),
            Qt.AlignmentFlag.AlignCenter,
            item.name,
        )


# ── collection panel ────────────────────────────────────────────────────


class CollectionPanel(QWidget):
    """Browse and equip unlocked themes, companions, and titles."""

    equip_requested = pyqtSignal(str, str)   # (unlock_type, unlock_key)

    def __init__(
        self,
        unlock_manager: UnlockManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._unlock_manager = unlock_manager
        self._cards: list[_UnlockCard] = []

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._container = QWidget()
        scroll.setWidget(self._container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(20, 20, 20, 20)
        self._layout.setSpacing(16)

    def refresh(self) -> None:
        """Rebuild the card grid from current unlock state."""
        # Clear existing widgets
        self._cards.clear()
        while self._layout.count():
            child = self._layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                self._clear_layout(child.layout())

        unlocked = self._unlock_manager.get_all_unlocked()
        equipped_theme = self._unlock_manager.get_equipped_theme()
        equipped_companion = self._unlock_manager.get_equipped_companion()

        # Determine accent for card borders
        from .styles import get_palette
        palette = get_palette(equipped_theme)
        accent = palette.get("accent", "#CBA6F7")

        # ── Themes ──────────────────────────────────────────────────
        self._add_section("Themes", "theme", unlocked, equipped_theme, accent, cols=3)

        # ── Companions ──────────────────────────────────────────────
        self._add_section("Companions", "companion", unlocked, equipped_companion, accent, cols=3)

        # ── Titles ──────────────────────────────────────────────────
        self._add_section("Titles", "title", unlocked, None, accent, cols=2)

        # Teaser
        from ..gamification.unlockables import REGISTRY
        from ..database.db import get_session
        from ..database.models import UserProgress
        with get_session() as db:
            progress = db.query(UserProgress).first()
            level = progress.current_level if progress else 1

        next_up = REGISTRY.next_upcoming(level)
        if next_up:
            teaser = QLabel(
                f"Next unlock: {next_up.name} at Level {next_up.required_level}",
                self._container,
            )
            teaser.setAlignment(Qt.AlignmentFlag.AlignCenter)
            teaser.setStyleSheet("font-size: 12px; color: #7A7A9A; padding: 8px;")
            self._layout.addWidget(teaser)

        self._layout.addStretch()

    def _add_section(
        self,
        header_text: str,
        unlock_type: str,
        unlocked: set[tuple[str, str]],
        equipped_key: str | None,
        accent: str,
        cols: int,
    ) -> None:
        header = QLabel(header_text, self._container)
        header.setStyleSheet(
            "font-size: 15px; font-weight: 700; padding: 4px 0; color: #E2E2F0;"
        )
        self._layout.addWidget(header)

        grid = QGridLayout()
        grid.setSpacing(10)

        items = REGISTRY.items_by_type(unlock_type)
        items.sort(key=lambda i: i.required_level or i.required_sessions)

        for idx, item in enumerate(items):
            is_unlocked = (item.unlock_type, item.key) in unlocked
            is_equipped = is_unlocked and item.key == equipped_key

            card = _UnlockCard(
                item,
                is_unlocked=is_unlocked,
                is_equipped=is_equipped,
                accent=accent,
                parent=self._container,
            )
            card.clicked.connect(
                lambda ut=item.unlock_type, k=item.key: self.equip_requested.emit(ut, k)
            )

            row, col = divmod(idx, cols)
            grid.addWidget(card, row, col)
            self._cards.append(card)

        self._layout.addLayout(grid)

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                CollectionPanel._clear_layout(child.layout())
