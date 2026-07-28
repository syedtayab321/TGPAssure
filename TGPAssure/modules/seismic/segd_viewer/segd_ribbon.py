# from __future__ import annotations

# from typing import List

# from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


# class SegdRibbonProvider(RibbonProvider):
#     def ribbon_tab_id(self) -> str:
#         return "segd"

#     def build_ribbon_groups(self) -> List[RibbonGroup]:
#         file_group = RibbonGroup(
#             label="SEG-D File",
#             actions=[
#                 RibbonAction("Open SEG-D", "segd_open_file"),
#                 RibbonAction("Reload", "segd_reload"),
#                 RibbonAction("Headers", "segd_headers"),
#             ],
#         )

#         display_group = RibbonGroup(
#             label="Display",
#             actions=[
#                 RibbonAction("Wiggle", "segd_display_wiggle"),
#                 RibbonAction("Variable Density", "segd_display_vd"),
#                 RibbonAction("Variable Area", "segd_display_va"),
#                 RibbonAction("Fit", "segd_zoom_fit"),
#             ],
#         )

#         gain_group = RibbonGroup(
#             label="Gain",
#             actions=[
#                 RibbonAction("No Gain", "segd_gain_none"),
#                 RibbonAction("AGC", "segd_gain_agc"),
#                 RibbonAction("Trace Balance", "segd_gain_trace_balance"),
#                 RibbonAction("Fixed Gain", "segd_gain_fixed"),
#             ],
#         )

#         tools_group = RibbonGroup(
#             label="Tools",
#             actions=[
#                 RibbonAction("Pan", "segd_pan"),
#                 RibbonAction("Pick", "segd_pick"),
#                 RibbonAction("Measure", "segd_measure"),
#             ],
#         )

#         qc_group = RibbonGroup(
#             label="QC",
#             actions=[
#                 RibbonAction("Run QC", "segd_run_qc"),
#                 RibbonAction("Header QC", "segd_header_qc"),
#                 RibbonAction("Trace QC", "segd_trace_qc"),
#             ],
#         )

#         return [file_group, display_group, gain_group, tools_group, qc_group]