"""Main application window for FocusQuest."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QIcon, QImage, QPainter, QColor, QPixmap, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTabWidget, QStatusBar, QMessageBox, QMenuBar,
    QProgressBar, QFrame, QPushButton, QSystemTrayIcon, QMenu,
)

from .timer.engine import TimerEngine, TimerState, SessionType
from .gamification.xp import (
    XPEngine, xp_for_level, xp_in_current_level, title_for_level,
)
from .gamification.unlockables import UnlockManager, REGISTRY
from .ui.timer_widget import TimerWidget
from .ui.stats_widget import StatsWidget
from .ui.collection_panel import CollectionPanel
from .ui.xp_toast import XPToast
from .ui.unlock_popup import UnlockPopup
from .ui.background_effects import BackgroundEffect
from .ui.styles import build_stylesheet, get_palette, get_ring_colors
from .ui.session_history import SessionHistoryWidget
from .ui.gentle_start import GentleStartWidget
from .database.db import get_session
from .database.models import UserProgress
from .settings import Settings, load_settings, save_settings
from .audio.sounds import SoundManager


# ── tray‑icon image generation ────────────────────────────────────────────


def _make_tray_icon(state: TimerState) -> QIcon:
    """Generate a 32×32 monochrome template icon for the macOS menu bar.

    - IDLE:        thin circle outline
    - WORKING:     filled circle
    - SHORT/LONG:  thin circle with small dot in centre
    - PAUSED:      two vertical pause bars
    """
    size = 64  # draw at 2× for Retina
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    colour = QColor(0, 0, 0, 220)  # template image: macOS tints automatically
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(colour)

    cx, cy, r = size // 2, size // 2, size // 2 - 4

    if state == TimerState.WORKING:
        # Filled circle
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)
    elif state == TimerState.PAUSED:
        # Two pause bars
        bar_w, bar_h = 8, 28
        gap = 6
        y = cy - bar_h // 2
        p.drawRoundedRect(cx - gap - bar_w, y, bar_w, bar_h, 3, 3)
        p.drawRoundedRect(cx + gap, y, bar_w, bar_h, 3, 3)
    elif state in (TimerState.SHORT_BREAK, TimerState.LONG_BREAK):
        # Circle outline + centre dot
        pen = p.pen()
        from PyQt6.QtGui import QPen
        p.setPen(QPen(colour, 4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)
        # Centre dot
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(colour)
        dot_r = 6
        p.drawEllipse(cx - dot_r, cy - dot_r, dot_r * 2, dot_r * 2)
    else:
        # IDLE: circle outline
        from PyQt6.QtGui import QPen
        p.setPen(QPen(colour, 4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)

    p.end()

    # macOS template images are auto-tinted to match light/dark appearance
    img.setDevicePixelRatio(2.0)
    pixmap = QPixmap.fromImage(img)
    icon = QIcon(pixmap)
    return icon


# ── helper: format seconds as mm:ss ──────────────────────────────────────

def _fmt_time(seconds: int) -> str:
    m, s = divmod(max(0, seconds), 60)
    return f"{m}:{s:02d}"


class FocusQuestApp(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FocusQuest")
        self.setMinimumSize(520, 720)
        self.resize(520, 800)

        # ── compact flag + geometry save timer ─────────────────────────
        self._compact = False
        self._geometry_save_timer = QTimer(self)
        self._geometry_save_timer.setSingleShot(True)
        self._geometry_save_timer.setInterval(500)
        self._geometry_save_timer.timeout.connect(self._save_geometry)

        # ── settings ──────────────────────────────────────────────────
        self._settings: Settings = load_settings()

        # ── engines ───────────────────────────────────────────────────
        self._xp_engine = XPEngine(parent=self)
        self._unlock_manager = UnlockManager()

        # Auto-advance: start breaks automatically when the previous
        # session finishes AND auto-start work after breaks.
        auto = self._settings.auto_start_breaks or self._settings.auto_start_work
        self._timer_engine = TimerEngine(
            self, db_enabled=True, auto_advance=auto,
        )

        # Apply saved durations
        self._timer_engine.set_duration(
            SessionType.WORK, self._settings.work_duration,
        )
        self._timer_engine.set_duration(
            SessionType.SHORT_BREAK, self._settings.short_break_duration,
        )
        self._timer_engine.set_duration(
            SessionType.LONG_BREAK, self._settings.long_break_duration,
        )

        # ── sound manager ─────────────────────────────────────────────
        self._sound_manager = SoundManager(parent=self)
        self._sound_manager.set_volume(self._settings.sound_volume)
        self._sound_manager.set_enabled(self._settings.sound_enabled)

        # ── seed default unlocks (theme + companion) ──────────────────
        self._unlock_manager.check_and_unlock(1, 0)
        theme_key = self._unlock_manager.get_equipped_theme()
        companion_key = self._unlock_manager.get_equipped_companion()

        # ── apply theme ───────────────────────────────────────────────
        self._current_theme_key = theme_key
        self._palette = get_palette(theme_key)
        self._ring_colors = get_ring_colors(theme_key)
        self.setStyleSheet(build_stylesheet(self._palette))

        # ── central widget ────────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(16, 12, 16, 12)
        root_layout.setSpacing(8)

        # ── background effect (behind everything) ─────────────────────
        theme_item = REGISTRY.get("theme", theme_key)
        bg_effect_type = (
            theme_item.definition.background_effect
            if theme_item else None
        )
        self._bg_effect = BackgroundEffect(bg_effect_type, central)
        self._bg_effect.lower()  # behind tab widget

        # ── top bar: title + level + XP bar + streak + gear ───────────
        self._top_bar = self._build_top_bar(central)
        root_layout.addWidget(self._top_bar)

        # ── tab widget ────────────────────────────────────────────────
        self._tabs = QTabWidget(central)
        root_layout.addWidget(self._tabs)

        # Focus tab — container wrapping gentle start + timer + history
        focus_container = QWidget(self._tabs)
        focus_layout = QVBoxLayout(focus_container)
        focus_layout.setContentsMargins(0, 0, 0, 0)
        focus_layout.setSpacing(0)

        # Gentle start overlay (visible initially)
        self._gentle_start = GentleStartWidget(focus_container)
        self._gentle_start.start_requested.connect(self._dismiss_gentle_start)
        focus_layout.addWidget(self._gentle_start)

        # Timer widget (hidden until gentle start dismissed)
        self._timer_widget = TimerWidget(self._timer_engine, focus_container)
        self._timer_widget.apply_palette(self._palette, self._ring_colors)
        self._timer_widget.set_companion(companion_key)
        self._timer_widget.setVisible(False)
        focus_layout.addWidget(self._timer_widget)

        # Session history (below timer, hidden until gentle start dismissed)
        self._session_history = SessionHistoryWidget(focus_container)
        self._session_history.label_clicked.connect(self._on_history_label_clicked)
        self._session_history.setVisible(False)
        focus_layout.addWidget(self._session_history)

        focus_layout.addStretch()
        self._tabs.addTab(focus_container, "Focus")

        # Stats tab
        self._stats_widget = StatsWidget(self._tabs)
        self._stats_widget.apply_palette(self._palette)
        self._tabs.addTab(self._stats_widget, "Stats")

        # Collection tab
        self._collection_panel = CollectionPanel(
            self._unlock_manager, self._tabs,
        )
        self._collection_panel.equip_requested.connect(
            self._on_equip_requested,
        )
        self._tabs.addTab(self._collection_panel, "Collection")

        # XP Toast (child of central so it overlays the tab content)
        self._xp_toast = XPToast(central)

        # Unlock popup (child of central)
        self._unlock_popup = UnlockPopup(central)

        # Status bar
        self._status_bar = QStatusBar(self)
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready to focus!")

        # ── system tray icon ──────────────────────────────────────────
        self._tray_icon = QSystemTrayIcon(self)
        self._tray_icon.setIcon(_make_tray_icon(TimerState.IDLE))
        self._tray_icon.setToolTip("FocusQuest — Ready")
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._build_tray_menu()
        self._tray_icon.show()

        # ── native menu bar ────────────────────────────────────────────
        self._build_menu_bar()

        # ── wire signals ──────────────────────────────────────────────
        self._timer_engine.state_changed.connect(self._on_state_changed)
        self._timer_engine.session_completed.connect(
            self._on_session_completed,
        )
        self._timer_engine.streak_updated.connect(self._on_streak_updated)
        self._timer_engine.tick.connect(self._on_tick)
        self._timer_engine.break_ending_soon.connect(self._on_break_warning)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # XP engine signals
        self._xp_engine.xp_awarded.connect(self._on_xp_awarded)
        self._xp_engine.level_up.connect(self._on_level_up)

        # macOS appearance change (for Minimal theme)
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app and app.styleHints():
                app.styleHints().colorSchemeChanged.connect(
                    self._on_system_appearance_changed,
                )
        except Exception:
            pass

        # ── restore window state ───────────────────────────────────────
        self._restore_geometry()
        if self._settings.always_on_top:
            self._apply_always_on_top(True)
        if self._settings.compact_mode:
            self._compact = True
            self._apply_compact_mode(True)

        # ── keyboard shortcuts ─────────────────────────────────────────
        self._setup_shortcuts()

    # ══════════════════════════════════════════════════════════════════
    #  TOP BAR
    # ══════════════════════════════════════════════════════════════════

    def _build_top_bar(self, parent: QWidget) -> QWidget:
        bar = QFrame(parent)
        bar.setObjectName("card")
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(8)

        # Row 1: title + gear + level badge + title label + streak
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        title = QLabel("FocusQuest", bar)
        title.setStyleSheet(
            f"font-size: 17px; font-weight: 700; "
            f"letter-spacing: 1px; color: {self._palette.get('text', '#E2E2F0')};"
        )

        # Gear button
        self._gear_btn = QPushButton("\u2699", bar)
        self._gear_btn.setObjectName("secondaryButton")
        self._gear_btn.setFixedSize(32, 32)
        self._gear_btn.setStyleSheet(
            "font-size: 18px; padding: 0; border-radius: 6px;"
        )
        self._gear_btn.setToolTip("Settings (Cmd+,)")
        self._gear_btn.clicked.connect(self._open_settings)

        self._level_badge = QLabel("Lv. 1", bar)
        self._level_badge.setObjectName("levelLabel")
        self._level_badge.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self._title_badge = QLabel("", bar)
        self._title_badge.setObjectName("xpLabel")
        self._title_badge.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self._streak_badge = QLabel("", bar)
        self._streak_badge.setObjectName("streakLabel")
        self._streak_badge.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        row1.addWidget(title)
        row1.addWidget(self._gear_btn)
        row1.addStretch()
        row1.addWidget(self._streak_badge)
        row1.addWidget(self._title_badge)
        row1.addWidget(self._level_badge)
        layout.addLayout(row1)

        # Row 2: XP progress bar with label
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        self._xp_bar = QProgressBar(bar)
        self._xp_bar.setRange(0, 100)
        self._xp_bar.setValue(0)
        self._xp_bar.setTextVisible(False)
        self._xp_bar.setFixedHeight(6)

        self._xp_label = QLabel("0 / 200 XP", bar)
        self._xp_label.setObjectName("xpLabel")
        self._xp_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        row2.addWidget(self._xp_bar, 1)
        row2.addWidget(self._xp_label)
        layout.addLayout(row2)

        # Populate with current data
        self._refresh_top_bar()

        return bar

    def _refresh_top_bar(self) -> None:
        """Pull current data from DB and update top bar."""
        with get_session() as db:
            progress = db.query(UserProgress).first()
            if not progress:
                return

            level = progress.current_level
            total_xp = progress.total_xp
            earned, needed = xp_in_current_level(total_xp)

            pct = int((earned / needed) * 100) if needed > 0 else 100

            self._level_badge.setText(f"Lv. {level}")
            self._title_badge.setText(title_for_level(level))
            self._xp_bar.setValue(pct)
            self._xp_label.setText(f"{earned} / {needed} XP")

            streak = progress.current_streak_days
            if streak > 0:
                self._streak_badge.setText(f"{streak} day streak")
            else:
                self._streak_badge.setText("")

    # ══════════════════════════════════════════════════════════════════
    #  SYSTEM TRAY
    # ══════════════════════════════════════════════════════════════════

    def _build_tray_menu(self) -> None:
        """Create the right-click context menu for the tray icon."""
        menu = QMenu(self)

        self._tray_start_action = menu.addAction("Start")
        self._tray_start_action.triggered.connect(self._tray_toggle_start)

        self._tray_skip_action = menu.addAction("Skip")
        self._tray_skip_action.triggered.connect(self._timer_engine.skip)

        menu.addSeparator()

        show_action = menu.addAction("Show FocusQuest")
        show_action.triggered.connect(self._show_window)

        menu.addSeparator()

        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self._quit_with_confirm)

        self._tray_icon.setContextMenu(menu)

    def _tray_toggle_start(self) -> None:
        """Start, pause, or resume based on current state."""
        state = self._timer_engine.state
        if state == TimerState.IDLE:
            self._timer_engine.start()
        elif state == TimerState.PAUSED:
            self._timer_engine.resume()
        elif self._timer_engine.is_running:
            self._timer_engine.pause()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Left-click on tray icon → toggle window visibility."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_window()

    def _show_window(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def _quit_app(self) -> None:
        """Actually quit (don't just minimize)."""
        self._tray_icon.hide()
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().quit()

    def _update_tray_state(self, state: TimerState) -> None:
        """Update tray icon image and menu label for current state."""
        self._tray_icon.setIcon(_make_tray_icon(state))

        # Update the Start/Pause label
        if state == TimerState.IDLE:
            self._tray_start_action.setText("Start")
        elif state == TimerState.PAUSED:
            self._tray_start_action.setText("Resume")
        else:
            self._tray_start_action.setText("Pause")

    # ══════════════════════════════════════════════════════════════════
    #  NATIVE MENU BAR
    # ══════════════════════════════════════════════════════════════════

    def _build_menu_bar(self) -> None:
        """Create a native macOS menu bar."""
        menu_bar = self.menuBar()

        # ── FocusQuest menu (About, Preferences, Quit — macOS roles) ─
        about_action = QAction("About FocusQuest", self)
        about_action.setMenuRole(QAction.MenuRole.AboutRole)
        about_action.triggered.connect(self._show_about)

        prefs_action = QAction("Preferences\u2026", self)
        prefs_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        prefs_action.setShortcut(QKeySequence("Ctrl+,"))
        prefs_action.triggered.connect(self._open_settings)

        quit_action = QAction("Quit FocusQuest", self)
        quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self._quit_with_confirm)

        # macOS auto-places role-tagged actions into the app menu
        app_menu = menu_bar.addMenu("FocusQuest")
        app_menu.addAction(about_action)
        app_menu.addAction(prefs_action)
        app_menu.addAction(quit_action)

        # ── View menu ────────────────────────────────────────────────
        view_menu = menu_bar.addMenu("View")

        self._compact_action = QAction("Compact Mode", self)
        self._compact_action.setCheckable(True)
        self._compact_action.setChecked(self._compact)
        self._compact_action.triggered.connect(self._toggle_compact_mode)
        view_menu.addAction(self._compact_action)

        self._aot_action = QAction("Always on Top", self)
        self._aot_action.setCheckable(True)
        self._aot_action.setChecked(self._settings.always_on_top)
        self._aot_action.triggered.connect(self._toggle_always_on_top)
        view_menu.addAction(self._aot_action)

        view_menu.addSeparator()

        stats_action = QAction("Stats", self)
        stats_action.setShortcut(QKeySequence("Ctrl+S"))
        stats_action.triggered.connect(
            lambda: self._tabs.setCurrentWidget(self._stats_widget)
        )
        view_menu.addAction(stats_action)

        # ── Window menu ──────────────────────────────────────────────
        window_menu = menu_bar.addMenu("Window")

        minimize_action = QAction("Minimize", self)
        minimize_action.setShortcut(QKeySequence("Ctrl+M"))
        minimize_action.triggered.connect(self.showMinimized)
        window_menu.addAction(minimize_action)

        close_action = QAction("Close Window", self)
        close_action.setShortcut(QKeySequence("Ctrl+W"))
        close_action.triggered.connect(self.close)
        window_menu.addAction(close_action)

    def _show_about(self) -> None:
        """Show the About dialog."""
        QMessageBox.about(
            self,
            "About FocusQuest",
            "<h3>FocusQuest</h3>"
            "<p>A gamified Pomodoro timer for macOS.</p>"
            "<p>Built with PyQt6. Designed with ADHD-friendly features: "
            "gentle start, positive-only messaging, and streak tracking "
            "that never guilt-trips.</p>",
        )

    # ══════════════════════════════════════════════════════════════════
    #  SOUND HELPERS
    # ══════════════════════════════════════════════════════════════════

    def _play_sound(self, name: str) -> None:
        """Play a sound, respecting DND mode."""
        if self._settings.do_not_disturb:
            return
        self._sound_manager.play(name)

    def _send_notification(self, title: str, body: str) -> None:
        """Show a macOS notification via the tray icon."""
        if not self._settings.notifications_enabled:
            return
        if self._settings.do_not_disturb:
            return
        self._tray_icon.showMessage(title, body)

    # ══════════════════════════════════════════════════════════════════
    #  TIMER SIGNALS
    # ══════════════════════════════════════════════════════════════════

    def _on_state_changed(self, state: TimerState) -> None:
        # Auto-dismiss gentle start when timer starts
        if state != TimerState.IDLE and self._gentle_start.isVisible():
            self._dismiss_gentle_start()

        messages = {
            TimerState.WORKING:     "Focusing...",
            TimerState.PAUSED:      "Paused \u2014 no rush, take your time",
            TimerState.SHORT_BREAK: "Short break \u2014 you've earned it!",
            TimerState.LONG_BREAK:  "Long break \u2014 recharge fully!",
            TimerState.IDLE:        "Ready when you are!",
        }
        self._status_bar.showMessage(messages.get(state, ""))

        # Update tray icon
        self._update_tray_state(state)

        # Play state-transition sounds
        if state == TimerState.WORKING:
            self._play_sound("session_start")
        elif state in (TimerState.SHORT_BREAK, TimerState.LONG_BREAK):
            self._play_sound("break_start")
            dur = self._timer_engine.remaining
            mins = dur // 60
            self._send_notification(
                "Nice work!",
                f"Take a {mins}-minute break.",
            )

    def _on_tick(self, remaining: int) -> None:
        """Update tray tooltip with remaining time."""
        state = self._timer_engine.state
        if state == TimerState.WORKING:
            self._tray_icon.setToolTip(
                f"FocusQuest \u2014 Focusing\u2026 {_fmt_time(remaining)}"
            )
        elif state in (TimerState.SHORT_BREAK, TimerState.LONG_BREAK):
            self._tray_icon.setToolTip(
                f"FocusQuest \u2014 Break {_fmt_time(remaining)}"
            )

    def _on_break_warning(self) -> None:
        """Play the gentle double-tap at 60 s remaining."""
        self._play_sound("break_warning")
        self._send_notification("Ready to focus?", "Break ends in 1 minute.")

    def _on_session_completed(self, data: dict) -> None:
        """Award XP, check unlocks, play sounds, send notifications."""
        session_type = data["session_type"]
        duration_seconds = data["duration_seconds"]

        # Award XP (the XP engine emits xp_awarded / level_up signals)
        result = self._xp_engine.award_session(
            session_type=session_type,
            duration_minutes=duration_seconds // 60,
            task_label=data.get("task_label", "") or "",
            round_number=data.get("round_number", 1),
            rounds_per_cycle=data.get("rounds_per_cycle", 4),
            was_micro=data.get("was_micro", False),
            session_date=data["end_time"].date(),
            db_session_id=data.get("db_session_id"),
        )

        if session_type == "work":
            xp = result["xp_earned"]
            msg = f"Session complete! +{xp} XP"
            if result["level_up"]:
                msg += f"  Level {result['new_level']}!"

            self._status_bar.showMessage(msg)

            # Sound + notification
            self._play_sound("session_complete")
            self._send_notification(
                "Pomodoro done!",
                f"+{xp} XP earned",
            )

            # Trigger companion celebration
            if self._timer_widget._companion_widget is not None:
                self._timer_widget._companion_widget.trigger_celebrate()

            # Check unlocks
            with get_session() as db:
                progress = db.query(UserProgress).first()
                if progress:
                    new_unlocks = self._unlock_manager.check_and_unlock(
                        progress.current_level,
                        progress.total_sessions_completed,
                    )
                    for unlock in new_unlocks:
                        item = REGISTRY.get(unlock["type"], unlock["key"])
                        if item:
                            QTimer.singleShot(
                                800,
                                lambda i=item: self._unlock_popup.show_unlock(i),
                            )
        else:
            self._status_bar.showMessage("Break over \u2014 let's go!")
            self._send_notification("Ready to focus?", "Let's go!")

        self._refresh_top_bar()

        # Update tray tooltip
        self._tray_icon.setToolTip("FocusQuest \u2014 Ready")

        # Refresh session history so the new session appears
        self._session_history.refresh()

        # Always refresh stats cache so it's warm when user switches tabs
        self._stats_widget.refresh()

    # ══════════════════════════════════════════════════════════════════
    #  XP ENGINE SIGNALS
    # ══════════════════════════════════════════════════════════════════

    def _on_xp_awarded(self, data: dict) -> None:
        """Show the floating XP toast."""
        self._xp_toast.show_award(data["amount"], data["bonuses"])

    def _on_level_up(self, data: dict) -> None:
        """Level-up celebration: toast + ring sparkles + fanfare + dialog."""
        new_level = data["new_level"]
        new_title = data["new_title"]

        # Play level-up fanfare
        self._play_sound("level_up")

        # Trigger celebration sparkles on the ring
        ring = self._timer_widget._ring
        ring.trigger_celebration()

        # Show level-up toast (delayed so XP toast appears first)
        QTimer.singleShot(
            600,
            lambda: self._xp_toast.show_level_up(new_level, new_title),
        )

        # Show level-up dialog (delayed so toasts can be seen)
        QTimer.singleShot(
            1200,
            lambda: self._show_level_up(new_level, new_title),
        )

    def _show_level_up(self, new_level: int, title: str) -> None:
        msg = QMessageBox(self)
        msg.setWindowTitle("Level Up!")
        msg.setText(
            f"You reached <b>Level {new_level}</b>!<br>"
            f"<i>{title}</i>"
        )
        msg.setInformativeText(
            "Check the Collection tab \u2014 new themes and companions may be unlocked!"
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    # ══════════════════════════════════════════════════════════════════
    #  SETTINGS
    # ══════════════════════════════════════════════════════════════════

    def _open_settings(self) -> None:
        """Open the settings dialog and apply any changes."""
        from .ui.settings_dialog import SettingsDialog

        def _preview_click():
            self._sound_manager.set_volume(self._settings.sound_volume)
            self._sound_manager.set_enabled(self._settings.sound_enabled)
            self._sound_manager.play("click")

        dlg = SettingsDialog(
            self._settings,
            parent=self,
            sound_preview_callback=_preview_click,
        )
        dlg.exec()

        # Apply changes from settings
        self._apply_settings()

    def _apply_settings(self) -> None:
        """Push current Settings into all subsystems."""
        s = self._settings

        # Timer durations (only when idle, so we don't disrupt a running session)
        if self._timer_engine.state == TimerState.IDLE:
            self._timer_engine.set_duration(SessionType.WORK, s.work_duration)
            self._timer_engine.set_duration(
                SessionType.SHORT_BREAK, s.short_break_duration,
            )
            self._timer_engine.set_duration(
                SessionType.LONG_BREAK, s.long_break_duration,
            )

        # Auto-advance
        self._timer_engine.auto_advance = (
            s.auto_start_breaks or s.auto_start_work
        )

        # Sound
        self._sound_manager.set_volume(s.sound_volume)
        self._sound_manager.set_enabled(s.sound_enabled)

    # ══════════════════════════════════════════════════════════════════
    #  COLLECTION / EQUIP
    # ══════════════════════════════════════════════════════════════════

    def _on_equip_requested(self, unlock_type: str, key: str) -> None:
        """Handle equip request from collection panel."""
        self._unlock_manager.equip(unlock_type, key)

        if unlock_type == "theme":
            self._apply_theme(key)
        elif unlock_type == "companion":
            self._timer_widget.set_companion(key)

        self._collection_panel.refresh()

    def _apply_theme(self, theme_key: str) -> None:
        """Instantly switch the entire app theme."""
        self._current_theme_key = theme_key
        self._palette = get_palette(theme_key)
        self._ring_colors = get_ring_colors(theme_key)

        # Global stylesheet
        self.setStyleSheet(build_stylesheet(self._palette))

        # Per-widget palette updates
        self._timer_widget.apply_palette(self._palette, self._ring_colors)
        self._stats_widget.apply_palette(self._palette)

        # Background effect
        theme_item = REGISTRY.get("theme", theme_key)
        bg_effect = (
            theme_item.definition.background_effect
            if theme_item else None
        )
        self._bg_effect.set_effect(bg_effect)

        # Refresh top bar (inline styles may reference palette)
        self._refresh_top_bar()

    # ══════════════════════════════════════════════════════════════════
    #  macOS APPEARANCE CHANGE
    # ══════════════════════════════════════════════════════════════════

    def _on_system_appearance_changed(self) -> None:
        """Re-apply theme if Minimal is currently equipped."""
        if self._current_theme_key == "minimal":
            self._apply_theme("minimal")

    # ══════════════════════════════════════════════════════════════════
    #  OTHER SIGNALS
    # ══════════════════════════════════════════════════════════════════

    def _dismiss_gentle_start(self) -> None:
        """Hide the gentle start overlay and show the timer + history."""
        self._gentle_start.setVisible(False)
        self._timer_widget.setVisible(True)
        if not self._compact:
            self._session_history.setVisible(True)
        self._session_history.refresh()

    def _on_history_label_clicked(self, label: str) -> None:
        """Auto-fill the task input when user clicks a session history label."""
        self._timer_widget._task_input.setText(label)

    def _on_streak_updated(self, current: int, longest: int) -> None:
        self._refresh_top_bar()

    def _on_tab_changed(self, index: int) -> None:
        widget = self._tabs.widget(index)
        if widget is self._stats_widget:
            self._stats_widget.refresh()
        elif widget is self._collection_panel:
            self._collection_panel.refresh()

    # ══════════════════════════════════════════════════════════════════
    #  WINDOW STATE (geometry, compact, always-on-top)
    # ══════════════════════════════════════════════════════════════════

    def _restore_geometry(self) -> None:
        """Restore window position and size from settings."""
        s = self._settings
        if s.window_x is not None and s.window_y is not None:
            self.move(s.window_x, s.window_y)
        if s.window_width and s.window_height:
            self.resize(s.window_width, s.window_height)

    def _save_geometry(self) -> None:
        """Persist current window geometry to settings."""
        if not self.isVisible():
            return
        pos = self.pos()
        size = self.size()
        self._settings.window_x = pos.x()
        self._settings.window_y = pos.y()
        self._settings.window_width = size.width()
        self._settings.window_height = size.height()
        save_settings(self._settings)

    def _schedule_geometry_save(self) -> None:
        """Debounce geometry saves — restart 500ms timer on each move/resize."""
        if hasattr(self, "_geometry_save_timer"):
            self._geometry_save_timer.start()

    def _toggle_always_on_top(self) -> None:
        """Toggle the always-on-top window flag."""
        new_val = not self._settings.always_on_top
        self._settings.always_on_top = new_val
        save_settings(self._settings)
        self._aot_action.setChecked(new_val)
        self._apply_always_on_top(new_val)

    def _apply_always_on_top(self, on_top: bool) -> None:
        """Apply or remove WindowStaysOnTopHint."""
        flags = self.windowFlags()
        if on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()  # Required: setWindowFlags hides the window

    def _toggle_compact_mode(self) -> None:
        """Toggle compact mode display."""
        self._compact = not self._compact
        self._settings.compact_mode = self._compact
        save_settings(self._settings)
        self._compact_action.setChecked(self._compact)
        self._apply_compact_mode(self._compact)

    def _apply_compact_mode(self, compact: bool) -> None:
        """Show/hide extras for compact mode."""
        self._top_bar.setVisible(not compact)
        self._tabs.tabBar().setVisible(not compact)
        self._status_bar.setVisible(not compact)
        self._session_history.setVisible(not compact)
        self._timer_widget.set_compact(compact)

    def _quit_with_confirm(self) -> None:
        """Quit, but ask first if a timer is running."""
        if (
            self._timer_engine.is_running
            or self._timer_engine.state == TimerState.PAUSED
        ):
            reply = QMessageBox.question(
                self,
                "Quit FocusQuest?",
                "A timer is still running. Quit anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self._save_geometry()
        self._quit_app()

    # ══════════════════════════════════════════════════════════════════
    #  KEYBOARD SHORTCUTS
    # ══════════════════════════════════════════════════════════════════

    def _setup_shortcuts(self) -> None:
        """Register Cmd+T for theme cycling (Space/Esc handled via keyPressEvent)."""
        cycle_theme = QAction("Cycle Theme", self)
        cycle_theme.setShortcut(QKeySequence("Ctrl+T"))
        cycle_theme.triggered.connect(self._cycle_theme)
        self.addAction(cycle_theme)

    def _on_space(self) -> None:
        """Start, pause, or resume the timer."""
        # No-op if the user is typing a task label
        if self._timer_widget._task_input.hasFocus():
            return
        state = self._timer_engine.state
        if state == TimerState.IDLE:
            self._timer_widget._task_input.clearFocus()
            self._timer_engine.task_label = (
                self._timer_widget._task_input.text().strip()
            )
            self._timer_engine.start()
        elif state == TimerState.PAUSED:
            self._timer_engine.resume()
        elif self._timer_engine.is_running:
            self._timer_engine.pause()

    def _on_escape(self) -> None:
        """Reset the timer (no-op when idle)."""
        if self._timer_engine.state != TimerState.IDLE:
            self._timer_engine.reset()

    def _cycle_theme(self) -> None:
        """Advance to the next unlocked theme."""
        from .gamification.unlockables import THEMES
        unlocked = self._unlock_manager.get_all_unlocked()
        unlocked_themes = [
            t.key for t in THEMES
            if ("theme", t.key) in unlocked
        ]
        if len(unlocked_themes) <= 1:
            return
        try:
            idx = unlocked_themes.index(self._current_theme_key)
        except ValueError:
            idx = -1
        next_idx = (idx + 1) % len(unlocked_themes)
        next_key = unlocked_themes[next_idx]
        self._unlock_manager.equip("theme", next_key)
        self._apply_theme(next_key)
        self._collection_panel.refresh()

    # ══════════════════════════════════════════════════════════════════
    #  WINDOW EVENTS
    # ══════════════════════════════════════════════════════════════════

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Minimize to tray instead of quitting (if enabled)."""
        self._save_geometry()
        if (
            self._settings.minimize_to_tray
            and self._tray_icon.isVisible()
        ):
            event.ignore()
            self.hide()
        else:
            self._tray_icon.hide()
            event.accept()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if hasattr(self, "_bg_effect"):
            central = self.centralWidget()
            if central:
                self._bg_effect.setGeometry(
                    0, 0, central.width(), central.height(),
                )
        self._schedule_geometry_save()

    def moveEvent(self, event) -> None:  # type: ignore[override]
        super().moveEvent(event)
        self._schedule_geometry_save()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        """Handle Space (start/pause) and Escape (stop) globally."""
        key = event.key()
        if key == Qt.Key.Key_Space and not event.modifiers():
            self._on_space()
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self._on_escape()
            event.accept()
            return
        super().keyPressEvent(event)
