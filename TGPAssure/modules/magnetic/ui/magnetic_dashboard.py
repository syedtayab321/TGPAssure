from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QWidget

from modules.magnetic.ui.enmag_data_qc_screen import EnMagDataQcScreen


class MagneticDashboard(EnMagDataQcScreen):
    """TGPAssure magnetic workspace using the EnMag Data QC interaction model.

    The class name/import path is retained for ribbon and workspace compatibility.
    All implementation now lives in the smaller self-contained EnMag QC screen
    and its gridding/filter/canvas support classes.
    """

    TAB_OVERVIEW = 0
    TAB_QC = 0
    TAB_PROCESSING = 0
    TAB_SPATIAL = 0
    TAB_REPORTS = 0

    def __init__(self, controller=None, parent: Optional[QWidget] = None) -> None:
        super().__init__(controller=controller, parent=parent)
