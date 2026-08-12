# EnMag-style Magnetic Data QC

This package contains the non-Qt core used by the TGPAssure Magnetic Data QC screen.

## Structure

- `models.py` — `EnMagQcData`, source counters, validity masks, grid/color result types.
- `gridding.py` — vectorized Fast Grid, Nearest and KD-tree IDW interpolation plus robust/manual color ranges.
- `spatial.py` — vectorized polygon selection and KD-tree coordinate indexing for hover inspection.
- `../ui/enmag_qc_canvas.py` — cached raster canvas, north-up pan/zoom, cursor inspection and clipping-aware color bar.
- `../ui/spatial_filter_dialog.py` — raw point-cloud polygon filter dialog.
- `../ui/enmag_data_qc_screen.py` — complete EnMag-style screen and TGPAssure ribbon compatibility API.
- `../ui/magnetic_dashboard.py` — compatibility class preserving the existing application import path.

## Performance design

Interpolation is NumPy/SciPy based. `Fast Grid` bins samples with `numpy.bincount` and uses a vectorized distance transform for radius-limited fill. IDW and nearest interpolation use `scipy.spatial.cKDTree`. Polygon filtering uses `matplotlib.path.Path.contains_points`. The Qt canvas caches the colorized grid as a `QImage`; opacity, pan and zoom do not recompute the grid.

## Coordinate handling

Native EnMag event logs are WGS84 (`EPSG:4326`) and display latitude/longitude directly. `pyproj` is included as a dependency so projected datasets can also report cursor latitude/longitude without changing the source dataset CRS.
