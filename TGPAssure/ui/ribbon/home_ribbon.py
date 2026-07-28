from __future__ import annotations

from typing import List

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


class HomeRibbonProvider(RibbonProvider):
    def ribbon_tab_id(self) -> str:
        return "home"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        file_group = RibbonGroup(
            label="File",
            actions=[
                RibbonAction("New", "new_project", icon="document-new", presentation="large", column=0),
                RibbonAction("Open", "open_project", icon="document-open", presentation="small", column=1),
                RibbonAction("Save", "save_project", icon="document-save", presentation="small", column=1),
                RibbonAction("Import", "import_file", icon="document-import", presentation="small", column=1),
                RibbonAction(
                    "Export",
                    "export_data",
                    icon="document-export",
                    presentation="large",
                    column=2,
                ),
            ],
        )

        clipboard_group = RibbonGroup(
            label="Clipboard",
            actions=[
                RibbonAction("Paste", "paste", icon="edit-paste", presentation="large", column=0),
                RibbonAction("Copy", "copy", icon="edit-copy", presentation="small", column=1),
                RibbonAction("Cut", "cut", icon="edit-cut", presentation="small", column=1),
            ],
        )

        project_group = RibbonGroup(
            label="Project",
            actions=[
                RibbonAction(
                    "Explorer",
                    "toggle_explorer",
                    icon="project-explorer",
                    presentation="large",
                    column=0,
                ),
                RibbonAction(
                    "Properties",
                    "project_properties",
                    icon="document-properties",
                    presentation="small",
                    column=1,
                ),
                RibbonAction(
                    "Refresh",
                    "refresh_project",
                    icon="view-refresh",
                    presentation="small",
                    column=1,
                ),
                RibbonAction(
                    "QC History",
                    "qc_history",
                    icon="view-history",
                    presentation="large",
                    column=2,
                ),
            ],
        )

        workspace_group = RibbonGroup(
            label="Workspace",
            actions=[
                # RibbonAction("Reset Layout", "reset_layout", icon="view-refresh", presentation="small"),
                RibbonAction("Explorer", "toggle_explorer", icon="folder", presentation="small"),
                RibbonAction("Properties", "toggle_properties", icon="document-properties", presentation="small"),
                RibbonAction("Console", "toggle_console", icon="utilities-terminal", presentation="small"),
            ],
        )
        settings_group = RibbonGroup(
            label="Application",
            actions=[
                RibbonAction("Preferences", "preferences", icon="preferences-system", presentation="large", accent=True),
                RibbonAction("Documentation", "documentation", icon="help-contents", presentation="small"),
                RibbonAction("About", "about", icon="help-about", presentation="small"),
            ],
        )
        return [file_group, clipboard_group, project_group, workspace_group, settings_group]
