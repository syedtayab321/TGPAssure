from __future__ import annotations

from typing import List

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


class ConverterRibbonProvider(RibbonProvider):
    def ribbon_tab_id(self) -> str:
        return "converter"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        return [
            RibbonGroup(
                "Input",
                [
                    RibbonAction("Open SEG-Y", "converter_open", icon="document-open", accent=True),
                    RibbonAction("Add Files", "converter_add", icon="folder-new"),
                    RibbonAction("Clear", "converter_clear", icon="edit-clear"),
                ],
            ),
            RibbonGroup(
                "Conversion",
                [
                    RibbonAction("Convert", "converter_run", icon="media-playback-start", accent=True),
                    RibbonAction("Cancel", "converter_cancel", icon="process-stop"),
                ],
            ),
            RibbonGroup(
                "Quality Assurance",
                [
                    RibbonAction("Inspect Source", "converter_inspect", icon="view-statistics"),
                    RibbonAction("Validate SEG-D", "converter_validate", icon="dialog-ok-apply"),
                    RibbonAction("Open Output", "converter_open_output", icon="document-open"),
                ],
            ),
        ]
