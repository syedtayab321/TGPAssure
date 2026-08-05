from __future__ import annotations

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


def actions(*items: tuple[str, str, str, str | None]) -> list[RibbonAction]:
    return [RibbonAction(label, action_id, icon=icon, badge=badge) for label, action_id, icon, badge in items]


class StaticRibbonProvider(RibbonProvider):
    def __init__(self, tab_id: str, groups: list[RibbonGroup]) -> None:
        self._tab_id = tab_id
        self._groups = groups

    def ribbon_tab_id(self) -> str:
        return self._tab_id

    def build_ribbon_groups(self) -> list[RibbonGroup]:
        return self._groups


def standard_providers() -> list[RibbonProvider]:
    return [
        StaticRibbonProvider("view", [
            RibbonGroup("Layout", actions(("Reset", "reset_layout", "view-refresh", None), ("Save", "save_layout", "document-save", None), ("Load", "load_layout", "document-open", None))),
            RibbonGroup("Panels", actions(("Explorer", "toggle_explorer", "folder", None), ("Properties", "toggle_properties", "document-properties", None), ("Console", "toggle_console", "utilities-terminal", None))),
            RibbonGroup("Zoom", actions(("Fit", "zoom_fit", "zoom-fit-best", None),)),
        ]),
        StaticRibbonProvider("tools", [
            RibbonGroup("Geophysical Modules", actions(("2D/3D Viewer", "visualization_open", "view-3d", None), ("Magnetic QC", "magnetic_open", "office-chart-line", None), ("Gravity QC", "gravity_open", "view-statistics", None), ("Electrical QC", "electrical_open", "electrical", None))),
            RibbonGroup("Settings", actions(("Preferences", "preferences", "preferences-system", None), ("Shortcuts", "shortcuts", "input-keyboard", None), ("About", "about", "help-about", None))),
        ]),
        StaticRibbonProvider("help", [
            RibbonGroup("Support", actions(("Documentation", "documentation", "help-contents", None), ("Report Issue", "report_issue", "dialog-warning", None), ("About", "about", "help-about", None))),
        ]),
    ]
