from __future__ import annotations

from typing import List

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


def large(label: str, action_id: str, icon: str = "", *, accent: bool = False) -> RibbonAction:
    return RibbonAction(label, action_id, icon=icon, presentation="large", accent=accent)


def small(
    label: str,
    action_id: str,
    icon: str = "",
    *,
    checkable: bool = False,
    checked: bool = False,
) -> RibbonAction:
    return RibbonAction(
        label,
        action_id,
        icon=icon,
        presentation="small",
        checkable=checkable,
        checked=checked,
    )


def ico(
    label: str,
    action_id: str,
    icon: str = "",
    *,
    checkable: bool = False,
    checked: bool = False,
) -> RibbonAction:
    """Icon-only action. The full action name remains available in the tooltip."""
    return RibbonAction(
        label,
        action_id,
        icon=icon,
        presentation="icon",
        checkable=checkable,
        checked=checked,
    )


class SegyViewerRibbonProvider(RibbonProvider):
    def __init__(self) -> None:
        self._show_color_library = False

    def set_color_library_visible(self, visible: bool) -> None:
        self._show_color_library = bool(visible)

    """SEG-Y viewer-only ribbon with mixed text and compact icon controls.

    Main viewer commands keep readable text labels. Dense repeat actions such as
    trace/time zoom, gain +/- and canvas tools are icon-only to prevent ribbon
    overflow while preserving every command and tooltip.
    """

    def ribbon_tab_id(self) -> str:
        return "segy_viewer"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        return [
            RibbonGroup(
                "SEG-Y File",
                [
                    large("Open SEG-Y", "segy_open_file", icon="seg-y", accent=True),
                    small("Fit", "segy_viewer_fit", "zoom-fit-best"),
                    small("Copy", "segy_viewer_copy_view", "edit-copy"),
                    small("PNG", "segy_viewer_export_image", "image-x-generic"),
                    small("BMP", "segy_viewer_export_bmp", "document-save"),
                ],
            ),
            RibbonGroup(
                "Display",
                [
                    small("Wiggle", "segy_viewer_toggle_wiggle", "office-chart-line", checkable=True, checked=True),
                    small("Colour", "segy_viewer_toggle_color", "color-picker", checkable=True),
                    small("Normal", "segy_viewer_reset_normal", "view-refresh"),
                    *([small("Color Library", "segy_viewer_color_library", "color-picker")] if self._show_color_library else []),
                ],
            ),
            RibbonGroup(
                "Wiggle Fill",
                [
                    small("No Fill", "segy_viewer_fill_none", "view-list-details"),
                    small("Positive", "segy_viewer_fill_positive", "list-add"),
                    small("Negative", "segy_viewer_fill_negative", "draw-line"),
                    small("Var Area", "segy_viewer_va", "view-grid"),
                    small("Delay Hdr", "segy_viewer_delay_header", "document-properties", checkable=True),
                ],
            ),
            RibbonGroup(
                "Colours",
                [
                    small("Wiggle", "segy_viewer_color_wiggle", "color-picker"),
                    small("Fill", "segy_viewer_color_fill", "color"),
                    small("Selected", "segy_viewer_color_selected", "appearance"),
                ],
            ),
            RibbonGroup(
                "Scale",
                [
                    ico("Fewer Traces / Zoom In X", "segy_viewer_traces_minus", "zoom-in"),
                    ico("More Traces / Zoom Out X", "segy_viewer_traces_plus", "zoom-out"),
                    ico("Time Zoom In", "segy_viewer_time_minus", "zoom-in"),
                    ico("Time Zoom Out", "segy_viewer_time_plus", "zoom-out"),
                    ico("Wiggle Gain Down", "segy_viewer_gain_w_minus", "audio-volume-muted"),
                    ico("Wiggle Gain Up", "segy_viewer_gain_w_plus", "audio-volume-high"),
                    ico("Colour Gain Down", "segy_viewer_gain_c_minus", "audio-volume-muted"),
                    ico("Colour Gain Up", "segy_viewer_gain_c_plus", "audio-volume-high"),
                ],
            ),
            RibbonGroup(
                "Direction",
                [
                    small("Normal", "segy_viewer_direction_normal", "select"),
                    small("Reversed", "segy_viewer_direction_reversed", "reset-view"),
                ],
            ),
            RibbonGroup(
                "Processing",
                [
                    small("Invert", "segy_viewer_proc_inversion", "invert", checkable=True),
                    small("Filter", "segy_viewer_proc_filter", "view-filter", checkable=True),
                    small("AGC", "segy_viewer_proc_agc", "office-chart-line", checkable=True),
                    small("Normalize", "segy_viewer_proc_norm", "view-refresh", checkable=True),
                ],
            ),
            RibbonGroup(
                "Viewer Tools",
                [
                    ico("Zoom Box", "segy_viewer_tool_zoom", "zoom-original", checkable=True),
                    ico("Pan", "segy_viewer_tool_pan", "pan", checkable=True),
                    ico("Pick", "segy_viewer_tool_pick", "select", checkable=True),
                    ico("Measure", "segy_viewer_tool_measure", "measure", checkable=True),
                    ico("Clear Marks", "segy_viewer_clear_marks", "edit-clear"),
                    small("Manual QC", "segy_viewer_manual_qc", "edit-find"),
                    small("Headers", "segy_viewer_headers", "document-properties"),
                    small("Hardcopy", "segy_viewer_hardcopy", "document-export"),
                    ico("Help", "segy_viewer_help", "help-about"),
                ],
            ),
        ]
