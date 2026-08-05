from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from ui.icons import get_icon
from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup


class RibbonGroupWidget(QFrame):
    action_triggered = Signal(str)
    details_requested = Signal(str)

    def __init__(self, group: RibbonGroup, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ribbonGroup")
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._group = group
        self._mode = self._resolve_mode(parent)
        self._metrics = self._mode_metrics(self._mode)
        self._build_ui()

    @staticmethod
    def _resolve_mode(parent: QWidget | None) -> str:
        mode = getattr(parent, "_responsive_mode", "") if parent is not None else ""
        if mode in {"compact", "medium", "full"}:
            return mode
        width = parent.width() if parent is not None else 1600
        if width < 1100:
            return "compact"
        if width < 1450:
            return "medium"
        return "full"

    @staticmethod
    def _mode_metrics(mode: str) -> dict[str, int]:
        if mode == "compact":
            return {
                "large_icon": 20,
                "large_width": 52,
                "large_height": 58,
                "small_icon": 12,
                "small_height": 20,
                "small_width": 78,
                "caption_height": 14,
                "column_gap": 1,
                "large_font": 7,
                "small_font": 7,
                "caption_font": 7,
                "icon_size": 13,
                "icon_button": 22,
                "icon_column_width": 24,
            }
        if mode == "medium":
            return {
                "large_icon": 24,
                "large_width": 64,
                "large_height": 65,
                "small_icon": 14,
                "small_height": 22,
                "small_width": 104,
                "caption_height": 15,
                "column_gap": 2,
                "large_font": 8,
                "small_font": 8,
                "caption_font": 7,
                "icon_size": 13,
                "icon_button": 22,
                "icon_column_width": 24,
            }
        return {
            "large_icon": 27,
            "large_width": 70,
            "large_height": 70,
            "small_icon": 15,
            "small_height": 23,
            "small_width": 112,
            "caption_height": 16,
            "column_gap": 2,
            "large_font": 8,
            "small_font": 8,
            "caption_font": 8,
            "icon_size": 15,
            "icon_button": 25,
            "icon_column_width": 27,
        }

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 3, 4, 0)
        root.setSpacing(0)

        content = QWidget(self)
        content.setObjectName("ribbonGroupContent")
        row = QHBoxLayout(content)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(self._metrics["column_gap"])
        row.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        for actions in self._arranged_columns().values():
            if actions and all(action.presentation == "icon" for action in actions):
                row.addWidget(self._create_icon_column(actions), 0, Qt.AlignTop)
            elif len(actions) == 1 and actions[0].presentation not in {"small", "icon"}:
                row.addWidget(self._create_large_button(actions[0]), 0, Qt.AlignTop)
            else:
                row.addWidget(self._create_small_column(actions), 0, Qt.AlignTop)

        root.addWidget(content, 1)

        caption = QLabel(self._group.label, self)
        caption.setObjectName("ribbonGroupLabel")
        caption.setAlignment(Qt.AlignCenter)
        caption_font = caption.font()
        caption_font.setPointSize(self._metrics["caption_font"])
        caption.setFont(caption_font)
        caption.setFixedHeight(self._metrics["caption_height"])
        root.addWidget(caption)

    def _arranged_columns(self) -> OrderedDict[int, list[RibbonAction]]:
        actions = list(self._group.actions)
        if not actions:
            return OrderedDict()

        # Home already provides an explicit Office-style layout. Other ribbon
        # providers historically left every action as the default "large" item,
        # which made those tabs oversized and inconsistent. Apply the same
        # large-primary + stacked-secondary layout automatically to all such groups.
        has_explicit_layout = any(
            action.column is not None or (action.presentation or "large").lower() in {"small", "icon", "icon_only", "mini"}
            for action in actions
        )
        if not has_explicit_layout:
            columns: OrderedDict[int, list[RibbonAction]] = OrderedDict()
            actions[0].presentation = "large"
            columns[0] = [actions[0]]
            column = 1
            for index in range(1, len(actions), 3):
                stack = actions[index:index + 3]
                for action in stack:
                    action.presentation = "small"
                columns[column] = stack
                column += 1
            return columns

        columns = OrderedDict()
        next_column = 0
        auto_small_column: int | None = None
        for action in actions:
            presentation = (action.presentation or "large").lower()
            if presentation in {"icon", "icon_only", "mini"}:
                action.presentation = "icon"
            elif presentation == "small":
                action.presentation = "small"
            else:
                action.presentation = "large"

            if action.column is not None:
                column = action.column
            elif action.presentation in {"small", "icon"}:
                if auto_small_column is None or len(columns.get(auto_small_column, [])) >= 3:
                    while next_column in columns:
                        next_column += 1
                    auto_small_column = next_column
                    next_column += 1
                column = auto_small_column
            else:
                while next_column in columns:
                    next_column += 1
                column = next_column
                next_column += 1
            columns.setdefault(column, []).append(action)
        return OrderedDict(sorted(columns.items(), key=lambda item: item[0]))

    def _action_enabled(self, action: RibbonAction) -> bool:
        enabled = action.enabled_predicate() if action.enabled_predicate else True
        window = self.window()
        state_resolver = getattr(window, "is_ribbon_action_enabled", None)
        if callable(state_resolver):
            try:
                enabled = bool(enabled and state_resolver(action.action_id))
            except Exception:
                pass
        return enabled

    def _attach_context_menu(self, button: QToolButton, action: RibbonAction) -> None:
        button.setContextMenuPolicy(Qt.CustomContextMenu)
        def show_menu(pos):
            menu = QMenu(button)
            details = menu.addAction("Details…")
            selected = menu.exec(button.mapToGlobal(pos))
            if selected is details:
                self.details_requested.emit(action.action_id)
        button.customContextMenuRequested.connect(show_menu)

    def _create_large_button(self, action: RibbonAction) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName("ribbonLargeAction")
        button.setProperty("accent", action.accent)
        button.setProperty("hasMenu", action.has_menu)
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        button.setText(self._large_label(action.label))
        button.setToolTip(self._tooltip(action))
        button.setIcon(get_icon(action.icon, size=self._metrics["large_icon"]))
        button.setIconSize(QSize(self._metrics["large_icon"], self._metrics["large_icon"]))
        font = button.font()
        font.setPointSize(self._metrics["large_font"])
        button.setFont(font)
        button.setFixedSize(self._metrics["large_width"], self._metrics["large_height"])
        button.setCursor(Qt.PointingHandCursor)
        button.setCheckable(action.checkable)
        button.setChecked(action.checked)
        button.setEnabled(self._action_enabled(action))
        button.clicked.connect(
            lambda checked=False, action_id=action.action_id: self.action_triggered.emit(action_id)
        )
        self._attach_context_menu(button, action)
        self._attach_badge(button, action.badge)
        return button

    def _create_icon_column(self, actions: list[RibbonAction]) -> QWidget:
        """Create a very compact icon-only stack for dense technical ribbons.

        The full label remains available as the tooltip. This is used by the
        SEG-Y viewer ribbon so that display, scale, processing and picking
        controls do not overflow horizontally on normal laptop screens.
        """
        column_widget = QWidget(self)
        column_widget.setObjectName("ribbonIconColumn")
        column_widget.setFixedWidth(self._metrics["icon_column_width"])
        column_layout = QVBoxLayout(column_widget)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(0)
        column_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        for action in actions[:3]:
            button = QToolButton(column_widget)
            button.setObjectName("ribbonIconAction")
            button.setProperty("accent", action.accent)
            button.setProperty("hasMenu", action.has_menu)
            button.setToolButtonStyle(Qt.ToolButtonIconOnly)
            button.setText("")
            button.setToolTip(self._tooltip(action))
            button.setIcon(get_icon(action.icon, size=self._metrics["icon_size"]))
            button.setIconSize(QSize(self._metrics["icon_size"], self._metrics["icon_size"]))
            button.setFixedSize(self._metrics["icon_button"], self._metrics["icon_button"])
            button.setCursor(Qt.PointingHandCursor)
            button.setCheckable(action.checkable)
            button.setChecked(action.checked)
            button.setEnabled(self._action_enabled(action))
            button.clicked.connect(
                lambda checked=False, action_id=action.action_id: self.action_triggered.emit(action_id)
            )
            self._attach_context_menu(button, action)
            column_layout.addWidget(button, 0, Qt.AlignHCenter)
            self._attach_badge(button, action.badge, compact=True)

        column_layout.addStretch(1)
        return column_widget

    def _create_small_column(self, actions: list[RibbonAction]) -> QWidget:
        column_widget = QWidget(self)
        column_widget.setObjectName("ribbonSmallColumn")
        measure_font = column_widget.font()
        measure_font.setPointSize(self._metrics["small_font"])
        metrics = QFontMetrics(measure_font)
        longest = max(
            (metrics.horizontalAdvance(self._small_label(action.label)) for action in actions[:3]),
            default=0,
        )
        column_width = max(
            self._metrics["small_width"],
            longest + self._metrics["small_icon"] + 28,
        )
        column_widget.setFixedWidth(column_width)
        column_layout = QVBoxLayout(column_widget)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(0)
        column_layout.setAlignment(Qt.AlignTop)

        for action in actions[:3]:
            button = QToolButton(column_widget)
            button.setObjectName("ribbonSmallAction")
            button.setProperty("accent", action.accent)
            button.setProperty("hasMenu", action.has_menu)
            button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            button.setText(self._small_label(action.label))
            button.setToolTip(self._tooltip(action))
            button.setIcon(get_icon(action.icon, size=self._metrics["small_icon"]))
            button.setIconSize(QSize(self._metrics["small_icon"], self._metrics["small_icon"]))
            font = button.font()
            font.setPointSize(self._metrics["small_font"])
            button.setFont(font)
            button.setFixedHeight(self._metrics["small_height"])
            button.setMinimumWidth(column_width)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.setCursor(Qt.PointingHandCursor)
            button.setCheckable(action.checkable)
            button.setChecked(action.checked)
            button.setEnabled(self._action_enabled(action))
            button.clicked.connect(
                lambda checked=False, action_id=action.action_id: self.action_triggered.emit(action_id)
            )
            self._attach_context_menu(button, action)
            column_layout.addWidget(button)
            self._attach_badge(button, action.badge, compact=True)

        column_layout.addStretch(1)
        return column_widget

    @staticmethod
    def _tooltip(action: RibbonAction) -> str:
        return action.label if not action.badge else f"{action.label} ({action.badge})"

    def _large_label(self, label: str) -> str:
        known = {
            "Open SEG-D": "Open\nSEG-D", "Export Image": "Export\nImage",
            "Variable Density": "Variable\nDensity", "Variable Area": "Variable\nArea",
            "Trace Balance": "Trace\nBalance", "Fixed Gain": "Fixed\nGain",
            "Header QC": "Header\nQC", "Trace QC": "Trace\nQC", "Run QC": "Run\nQC",
            "Zoom In": "Zoom\nIn", "Zoom Out": "Zoom\nOut", "Batch Export": "Batch\nExport",
            "Batch Process": "Batch\nProcess", "Cross-Plot": "Cross-\nPlot",
            "Time Series": "Time\nSeries", "Report Issue": "Report\nIssue",
            "QC History": "QC\nHistory",
        }
        if label in known:
            return known[label]
        if len(label) > 10 and " " in label:
            words = label.split()
            best_index = 1
            best_delta = len(label)
            for index in range(1, len(words)):
                left = " ".join(words[:index])
                right = " ".join(words[index:])
                delta = abs(len(left) - len(right))
                if delta < best_delta:
                    best_delta = delta
                    best_index = index
            return " ".join(words[:best_index]) + "\n" + " ".join(words[best_index:])
        return label

    def _small_label(self, label: str) -> str:
        if self._mode == "compact":
            replacements = {
                "Properties": "Props",
                "Variable Density": "Var Density",
                "Variable Area": "Var Area",
                "Trace Balance": "Trace Bal.",
                "Documentation": "Docs",
            }
            return replacements.get(label, label)
        return label

    @staticmethod
    def _attach_badge(button: QToolButton, text: str | None, compact: bool = False) -> None:
        if not text:
            return
        badge = QLabel(text, button)
        badge.setObjectName("featureBadge")
        badge.adjustSize()
        x = max(1, button.width() - badge.width() - 2)
        y = 1 if not compact else max(1, (button.height() - badge.height()) // 2)
        badge.move(x, y)
        badge.show()