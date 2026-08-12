from __future__ import annotations

# Compatibility wrapper: the Magnetic QC screen now uses the rewritten dialog in
# enmag_spatial_filter_dialog.py.  Keep the old import path safe for any external
# references/ribbon reloads.
from modules.magnetic.ui.enmag_spatial_filter_dialog import EnMagSpatialFilterDialog

SpatialFilterDialog = EnMagSpatialFilterDialog
