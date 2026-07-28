from __future__ import annotations

from typing import Optional, Dict, Any, List
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QSpinBox, QDoubleSpinBox, QGroupBox,
    QPushButton, QCheckBox, QSlider, QTabWidget,
    QListWidget, QListWidgetItem, QFormLayout
)

from modules.seismic.segd_viewer.gain_stage import GainStage
from modules.seismic.segd_viewer.rasterizer import Rasterizer
from core.domain.colormap_registry import ColormapRegistry


class ConfigurationPanel(QWidget):
    config_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._colormap_registry = ColormapRegistry()
        self._channel_count = 1
        self._selected_channels = [0]

        self.setup_ui()

    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        tabs = QTabWidget()
        tabs.setTabPosition(QTabWidget.West)

        display_tab = QWidget()
        display_layout = QVBoxLayout(display_tab)

        display_group = QGroupBox("Display")
        display_form = QFormLayout(display_group)

        self.display_mode_combo = QComboBox()
        self.display_mode_combo.addItems([
            Rasterizer.DISPLAY_VARIABLE_DENSITY.replace("_", " ").title(),
            Rasterizer.DISPLAY_WIGGLE.replace("_", " ").title(),
            Rasterizer.DISPLAY_VARIABLE_AREA.replace("_", " ").title()
        ])
        self.display_mode_combo.currentIndexChanged.connect(self._on_config_changed)
        display_form.addRow("Mode:", self.display_mode_combo)

        self.colormap_combo = QComboBox()
        for name in self._colormap_registry.list():
            self.colormap_combo.addItem(name)
        self.colormap_combo.currentIndexChanged.connect(self._on_config_changed)
        display_form.addRow("Colormap:", self.colormap_combo)

        self.clip_spin = QDoubleSpinBox()
        self.clip_spin.setRange(50.0, 100.0)
        self.clip_spin.setValue(99.0)
        self.clip_spin.setSuffix("%")
        self.clip_spin.valueChanged.connect(self._on_config_changed)
        display_form.addRow("Clip Percentile:", self.clip_spin)

        display_layout.addWidget(display_group)

        gain_group = QGroupBox("Gain")
        gain_form = QFormLayout(gain_group)

        self.gain_mode_combo = QComboBox()
        self.gain_mode_combo.addItems([
            GainStage.MODE_NONE,
            GainStage.MODE_FIXED,
            GainStage.MODE_AGC,
            GainStage.MODE_TRACE_BALANCE
        ])
        self.gain_mode_combo.currentIndexChanged.connect(self._on_config_changed)
        gain_form.addRow("Mode:", self.gain_mode_combo)

        self.gain_db_spin = QDoubleSpinBox()
        self.gain_db_spin.setRange(-60.0, 60.0)
        self.gain_db_spin.setValue(0.0)
        self.gain_db_spin.setSuffix(" dB")
        self.gain_db_spin.valueChanged.connect(self._on_config_changed)
        gain_form.addRow("Fixed Gain:", self.gain_db_spin)

        self.agc_window_spin = QSpinBox()
        self.agc_window_spin.setRange(10, 1000)
        self.agc_window_spin.setValue(100)
        self.agc_window_spin.setSuffix(" samples")
        self.agc_window_spin.valueChanged.connect(self._on_config_changed)
        gain_form.addRow("AGC Window:", self.agc_window_spin)

        display_layout.addWidget(gain_group)

        channel_group = QGroupBox("Channels")
        channel_layout = QVBoxLayout(channel_group)

        self.channel_list = QListWidget()
        self.channel_list.setSelectionMode(QListWidget.MultiSelection)
        self.channel_list.itemSelectionChanged.connect(self._on_channel_selection_changed)
        channel_layout.addWidget(self.channel_list)

        channel_buttons = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self._select_all_channels)
        clear_all_btn = QPushButton("Clear All")
        clear_all_btn.clicked.connect(self._clear_all_channels)
        channel_buttons.addWidget(select_all_btn)
        channel_buttons.addWidget(clear_all_btn)
        channel_layout.addLayout(channel_buttons)

        display_layout.addWidget(channel_group)
        display_layout.addStretch()

        tabs.addTab(display_tab, "Display")

        layout.addWidget(tabs)

    def set_channel_count(self, count: int) -> None:
        self._channel_count = count
        self.channel_list.clear()
        for i in range(count):
            item = QListWidgetItem(f"Channel {i+1}")
            item.setData(Qt.UserRole, i)
            self.channel_list.addItem(item)
        self._select_all_channels()

    def get_config(self) -> Dict[str, Any]:
        display_mode_text = self.display_mode_combo.currentText()
        display_mode_map = {
            "Variable Density": Rasterizer.DISPLAY_VARIABLE_DENSITY,
            "Wiggle": Rasterizer.DISPLAY_WIGGLE,
            "Variable Area": Rasterizer.DISPLAY_VARIABLE_AREA
        }
        display_mode = display_mode_map.get(display_mode_text, Rasterizer.DISPLAY_VARIABLE_DENSITY)

        colormap = self.colormap_combo.currentText()
        clip_percentile = self.clip_spin.value()
        gain_mode = self.gain_mode_combo.currentText()
        fixed_gain_db = self.gain_db_spin.value()
        agc_window = self.agc_window_spin.value()

        return {
            "display_mode": display_mode,
            "colormap": colormap,
            "clip_percentile": clip_percentile,
            "gain_mode": gain_mode,
            "gain_params": {
                "db": fixed_gain_db,
                "window_length": agc_window
            },
            "channels": self._selected_channels
        }

    def _on_config_changed(self) -> None:
        self.config_changed.emit()

    def _on_channel_selection_changed(self) -> None:
        self._selected_channels = []
        for item in self.channel_list.selectedItems():
            channel_id = item.data(Qt.UserRole)
            if channel_id is not None:
                self._selected_channels.append(channel_id)
        if not self._selected_channels:
            self._selected_channels = [0]
        self.config_changed.emit()

    def _select_all_channels(self) -> None:
        self.channel_list.selectAll()

    def _clear_all_channels(self) -> None:
        self.channel_list.clearSelection()