from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.seismic.segd_viewer.segd_reader import SegdReader


class HeaderViewer(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._reader: Optional[SegdReader] = None
        self._current_trace = 0
        self._show_hex = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tabs = QTabWidget(self)

        general_tab = QWidget(self.tabs)
        general_layout = QVBoxLayout(general_tab)
        general_layout.setContentsMargins(4, 4, 4, 4)
        self.general_tree = self._create_tree()
        general_layout.addWidget(self.general_tree)
        self.tabs.addTab(general_tab, "General Headers")

        trace_tab = QWidget(self.tabs)
        trace_layout = QVBoxLayout(trace_tab)
        trace_layout.setContentsMargins(4, 4, 4, 4)
        trace_layout.setSpacing(4)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Trace:"))
        self.trace_spin = QSpinBox()
        self.trace_spin.setMinimum(1)
        self.trace_spin.setMaximum(1)
        self.trace_spin.valueChanged.connect(self._on_trace_spin_changed)
        controls.addWidget(self.trace_spin)
        controls.addStretch(1)
        self.hex_toggle = QPushButton("Show Hex")
        self.hex_toggle.setCheckable(True)
        self.hex_toggle.toggled.connect(self._on_hex_toggled)
        controls.addWidget(self.hex_toggle)
        trace_layout.addLayout(controls)

        self.trace_tree = self._create_tree()
        trace_layout.addWidget(self.trace_tree)
        self.tabs.addTab(trace_tab, "Trace Headers")

        layout.addWidget(self.tabs)

    def _create_tree(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderLabels(["Field", "Value"])
        tree.setAlternatingRowColors(True)
        tree.setSelectionMode(QAbstractItemView.SingleSelection)
        tree.setUniformRowHeights(True)
        tree.setRootIsDecorated(True)
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        tree.header().setMinimumSectionSize(110)
        return tree

    def set_reader(self, reader: SegdReader) -> None:
        self._reader = reader
        blocker = QSignalBlocker(self.trace_spin)
        self.trace_spin.setMaximum(max(1, reader.get_trace_count()))
        self.trace_spin.setValue(1)
        del blocker
        self._current_trace = 0
        self._populate_general_headers()
        self._populate_trace_headers(0)

    def clear_reader(self) -> None:
        self._reader = None
        self._current_trace = 0
        self.general_tree.clear()
        self.trace_tree.clear()
        blocker = QSignalBlocker(self.trace_spin)
        self.trace_spin.setMaximum(1)
        self.trace_spin.setValue(1)
        del blocker

    def set_trace(self, trace_index: int) -> None:
        if self._reader is None:
            return
        trace_index = max(0, min(int(trace_index), self._reader.get_trace_count() - 1))
        if trace_index == self._current_trace and self.trace_tree.topLevelItemCount() > 0:
            return
        self._current_trace = trace_index
        blocker = QSignalBlocker(self.trace_spin)
        self.trace_spin.setValue(trace_index + 1)
        del blocker
        self._populate_trace_headers(trace_index)

    def _on_trace_spin_changed(self, value: int) -> None:
        self.set_trace(value - 1)

    def _on_hex_toggled(self, checked: bool) -> None:
        self._show_hex = bool(checked)
        self.hex_toggle.setText("Show Decimal" if checked else "Show Hex")
        self._populate_trace_headers(self._current_trace)

    def _add_item(self, parent: Optional[QTreeWidgetItem], tree: QTreeWidget, label: str, value) -> QTreeWidgetItem:
        text = self._format_value(value)
        item = QTreeWidgetItem([label, text])
        item.setToolTip(0, label)
        item.setToolTip(1, text)
        if parent is None:
            tree.addTopLevelItem(item)
        else:
            parent.addChild(item)
        return item

    def _format_value(self, value) -> str:
        if self._show_hex and isinstance(value, (int,)):
            return f"0x{int(value):X} ({int(value)})"
        return str(value)

    def _populate_general_headers(self) -> None:
        self.general_tree.clear()
        if self._reader is None:
            return

        gh1 = self._reader.general_header_1
        gh1_item = QTreeWidgetItem(["General Header 1", ""])
        self.general_tree.addTopLevelItem(gh1_item)
        for label, value in (
            ("File Number", gh1.file_number),
            ("General Header Length", gh1.general_header_length),
            ("Channel Set Descriptor Length", gh1.channel_set_descriptor_length),
            ("Extended Header Length", gh1.extended_header_length),
            ("Standard Headers Length", gh1.standard_headers_length),
            ("Channel Set Count", gh1.channel_set_count),
            ("Trace Count per Channel Set", gh1.trace_count_per_channel_set),
            ("Manufacturer Code", gh1.manufacturer_code),
            ("Revision", self._reader.get_revision()),
            ("Format Code", gh1.format_code),
            ("Time Base", gh1.time_base),
            ("Date", gh1.date),
            ("Time", gh1.time),
        ):
            self._add_item(gh1_item, self.general_tree, label, value)

        gh2 = self._reader.general_header_2
        gh2_item = QTreeWidgetItem(["General Header 2", ""])
        self.general_tree.addTopLevelItem(gh2_item)
        for label, value in (
            ("Maximum Traces", gh2.maximum_traces),
            ("Channel Sets Count", gh2.channel_sets_count),
            ("Year", gh2.year),
            ("Julian Day", gh2.day),
            ("Hour", gh2.hour),
            ("Minute", gh2.minute),
            ("Second", gh2.second),
            ("Millisecond", gh2.ms),
        ):
            self._add_item(gh2_item, self.general_tree, label, value)

        gh3 = self._reader.general_header_3
        gh3_item = QTreeWidgetItem(["General Header 3", ""])
        self.general_tree.addTopLevelItem(gh3_item)
        for label, value in (
            ("Expansion Length", gh3.expansion_length),
            ("Channel Set Descriptor Length", gh3.channel_set_descriptor_length),
            ("Standard Headers Length", gh3.standard_headers_length),
            ("Extended Headers Count", gh3.extended_headers_count),
        ):
            self._add_item(gh3_item, self.general_tree, label, value)

        descriptors_item = QTreeWidgetItem(["Channel Set Descriptors", ""])
        self.general_tree.addTopLevelItem(descriptors_item)
        for index, descriptor in enumerate(self._reader.channel_set_descriptors):
            descriptor_item = QTreeWidgetItem([f"Channel Set {index + 1}", ""])
            descriptors_item.addChild(descriptor_item)
            for label, value in (
                ("Channel Set ID", descriptor.channel_set_id),
                ("Channel Count", descriptor.channel_count),
                ("Sample Count", descriptor.sample_count),
                ("Sample Format", descriptor.sample_format),
                ("Sample Interval (ms)", descriptor.sample_interval),
                ("Start Time (ms)", descriptor.start_time_ms),
                ("End Time (ms)", descriptor.end_time_ms),
                ("Scan Type", descriptor.scan_type),
                ("Channel Type", descriptor.channel_type),
                ("Gain Type", descriptor.gain_type),
                ("Trace Header Extensions", descriptor.trace_header_extensions),
            ):
                self._add_item(descriptor_item, self.general_tree, label, value)

        summary_item = QTreeWidgetItem(["File Summary", ""])
        self.general_tree.addTopLevelItem(summary_item)
        for key, value in self._reader.metadata_summary().items():
            self._add_item(summary_item, self.general_tree, key.replace("_", " ").title(), value)

        self.general_tree.expandToDepth(1)

    def _populate_trace_headers(self, trace_index: int) -> None:
        self.trace_tree.clear()
        if self._reader is None:
            return

        header_item = QTreeWidgetItem([f"Trace {trace_index + 1}", ""])
        self.trace_tree.addTopLevelItem(header_item)
        try:
            headers = self._reader.read_trace_headers((trace_index, trace_index + 1))
            if len(headers) == 0:
                self._add_item(header_item, self.trace_tree, "Status", "No trace header data")
            else:
                header = headers[0]
                for field_name in header.dtype.names or ():
                    label = field_name.replace("_", " ").title()
                    value = header[field_name]
                    if hasattr(value, "item"):
                        value = value.item()
                    self._add_item(header_item, self.trace_tree, label, value)
        except Exception as error:
            self._add_item(header_item, self.trace_tree, "Error", str(error))

        try:
            info = self._reader.get_trace_info(trace_index)
            attributes_item = QTreeWidgetItem(["Decoded Trace Attributes", ""])
            self.trace_tree.addTopLevelItem(attributes_item)
            for label, value in (
                ("Physical Index", info.physical_index),
                ("File Number", info.file_number),
                ("Scan Type", info.scan_type),
                ("Channel Set", info.channel_set),
                ("Trace Number", info.trace_number),
                ("Receiver Line", info.receiver_line),
                ("Receiver Point", info.receiver_point),
                ("Receiver Index", info.receiver_index),
                ("Sensor Type", info.sensor_type),
                ("Channel Type", info.channel_type),
                ("Trace Edit Code", info.trace_edit),
                ("Sample Count", info.sample_count),
                ("Sample Interval (ms)", info.sample_interval_ms),
                ("Header Offset", info.header_offset),
                ("Data Offset", info.data_offset),
            ):
                self._add_item(attributes_item, self.trace_tree, label, value)
        except Exception:
            pass

        self.trace_tree.expandAll()