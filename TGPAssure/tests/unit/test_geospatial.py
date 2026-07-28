from __future__ import annotations

import numpy as np
import pytest

from core.domain.geospatial import CoordinateTransformError, to_wgs84, utm_wgs84_to_lonlat


def test_wgs84_passthrough() -> None:
    result = to_wgs84([67.0, 67.1], [31.0, 31.1], crs="EPSG:4326")
    np.testing.assert_allclose(result.longitude, [67.0, 67.1])
    np.testing.assert_allclose(result.latitude, [31.0, 31.1])


def test_utm_zone_42n_inverse_matches_known_central_meridian() -> None:
    lon, lat = utm_wgs84_to_lonlat([500000.0], [0.0], zone=42, northern=True)
    assert lon[0] == pytest.approx(69.0, abs=1e-7)
    assert lat[0] == pytest.approx(0.0, abs=1e-7)


def test_unknown_projected_crs_is_not_guessed() -> None:
    with pytest.raises(CoordinateTransformError):
        to_wgs84([500000.0], [3400000.0], crs="EPSG:24342")
