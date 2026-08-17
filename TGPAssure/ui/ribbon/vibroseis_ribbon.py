from __future__ import annotations

from typing import Callable, List

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


DISPLAY_ATTRS: list[tuple[str, str]] = [
    ("drive_level_pct", "Drive Level"),
    ("peak_distortion_pct", "Peak Distortion"),
    ("avg_stiffness", "Average Stiffness"),
    ("force_overload", "Force Overload"),
    ("excitation_overload", "Excitation Overload"),
    ("avg_phase_deg", "Average Phase"),
    ("avg_force", "Average Force"),
    ("status_code", "Status Code"),
    ("pressure_overload", "Pressure Overload"),
    ("hdop", "Horizontal Accuracy"),
    ("peak_phase_deg", "Peak Phase"),
    ("peak_force", "Peak Force"),
    ("mass_warning", "Mass Warning"),
    ("mass_overload", "Mass Overload"),
    ("avg_distortion_pct", "Average Distortion"),
    ("avg_viscosity", "Average Viscosity"),
    ("plate_warning", "Plate Warning"),
    ("valve_overload", "Valve Overload"),
]


class VibroseisRibbonProvider(RibbonProvider):
    """Compact context-aware ribbon for Sweep, Manual QC and VAPS Analyser."""

    def __init__(self, context_getter: Callable[[], str] | None = None) -> None:
        self._context_getter = context_getter or (lambda: "vaps")

    def ribbon_tab_id(self) -> str:
        return "vibroseis"

    def _context(self) -> str:
        context = str(self._context_getter() or "vaps").lower()
        return context if context in {"sweep", "manual", "vaps"} else "vaps"

    @staticmethod
    def _nav_group(active: str) -> RibbonGroup:
        return RibbonGroup("Pages", [
            RibbonAction("Sweep", "vibroseis_page_sweep", icon="view-statistics", presentation="small", checkable=True, checked=active == "sweep"),
            RibbonAction("Manual", "vibroseis_page_manual", icon="edit-find", presentation="small", checkable=True, checked=active == "manual"),
            RibbonAction("VAPS", "vibroseis_page_vaps", icon="view-list-details", presentation="small", checkable=True, checked=active == "vaps", accent=True),
        ])

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        context = self._context()
        groups: list[RibbonGroup] = [self._nav_group(context)]
        if context == "sweep":
            groups.extend(self._sweep_groups())
        elif context == "manual":
            groups.extend(self._manual_groups())
        else:
            groups.extend(self._vaps_groups())
        return groups

    @staticmethod
    def _sweep_groups() -> list[RibbonGroup]:
        return [
            RibbonGroup("Sweep", [
                RibbonAction("Generate", "vibroseis_generate", icon="media-playback-start", accent=True),
                RibbonAction("Export", "vibroseis_export_pilot", icon="document-save", presentation="small"),
            ]),
        ]

    @staticmethod
    def _manual_groups() -> list[RibbonGroup]:
        return [
            RibbonGroup("Data", [
                RibbonAction("VAPS/H26", "vibroseis_load_vaps", icon="document-open", accent=True),
                RibbonAction("Telemetry", "vibroseis_open_telemetry", icon="document-open", presentation="small"),
            ]),
            RibbonGroup("Manual QC", [
                RibbonAction("Add", "vibroseis_manual_add", icon="list-add", accent=True),
                RibbonAction("Export", "vibroseis_manual_export", icon="document-save", presentation="small"),
                RibbonAction("Clear", "vibroseis_manual_clear", icon="edit-clear", presentation="small"),
            ]),
        ]

    @staticmethod
    def _vaps_groups() -> list[RibbonGroup]:
        # Only the operational controls stay as normal labelled buttons.
        # The VAPS attributes are checkable ribbon actions that replace the large
        # in-page radio-button panel, keeping the workspace clear and responsive.
        attr_actions = [
            RibbonAction(
                label,
                f"vibroseis_vaps_attr_{attr}",
                icon="office-chart-line",
                presentation="small",
                checkable=True,
                checked=(attr == "drive_level_pct"),
            )
            for attr, label in DISPLAY_ATTRS
        ]
        return [
            RibbonGroup("File", [
                RibbonAction("Open", "vibroseis_vaps_open", icon="document-open", accent=True),
                RibbonAction("Export", "vibroseis_vaps_bmp", icon="document-save", presentation="small"),
                RibbonAction("Print", "vibroseis_vaps_print", icon="document-print", presentation="small"),
                RibbonAction("Clear", "vibroseis_vaps_end", icon="edit-clear", presentation="small"),
            ]),
            RibbonGroup("Display", attr_actions[0:3]),
            RibbonGroup("Performance", attr_actions[3:6]),
            RibbonGroup("Force", attr_actions[6:9]),
            RibbonGroup("Warnings", attr_actions[9:12]),
            RibbonGroup("Mechanics", attr_actions[12:15]),
            RibbonGroup("Extra", attr_actions[15:18]),
            RibbonGroup("View", [
                RibbonAction("Raw", "vibroseis_vaps_mode_raw", icon="dialog-ok-apply", presentation="small", checkable=True, checked=True),
                RibbonAction("Filtered", "vibroseis_vaps_mode_filtered", icon="view-filter", presentation="small", checkable=True),
                RibbonAction("Connect", "vibroseis_vaps_connect", icon="draw-line", presentation="small", checkable=True),
            ]),
            RibbonGroup("Vibs", [
                RibbonAction("All", "vibroseis_vaps_all", icon="dialog-ok-apply", presentation="small"),
                RibbonAction("None", "vibroseis_vaps_none", icon="edit-clear", presentation="small"),
                RibbonAction("Reset", "vibroseis_vaps_reset", icon="view-refresh", presentation="small"),
            ]),
            RibbonGroup("QC", [
                RibbonAction("Stats", "vibroseis_vaps_stats", icon="view-statistics", presentation="small"),
                RibbonAction("QC", "vibroseis_vaps_qc", icon="view-statistics", accent=True),
            ]),
        ]
