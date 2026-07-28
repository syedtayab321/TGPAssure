from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from modules.magnetic.reader import MagneticReader


@pytest.fixture
def magnetic_files(tmp_path: Path) -> tuple[Path, Path]:
    rover = tmp_path / "rover.csv"
    base = tmp_path / "base.csv"
    n = 240
    rover_lines = ["timestamp,easting,northing,elevation,total_field,line_id,station_id,line_type"]
    base_lines = ["timestamp,total_field"]
    for index in range(n):
        line = "L001" if index < 120 else "L002"
        along = index if index < 120 else index - 120
        northing = 0.0 if index < 120 else 100.0
        total_field = 50_000.0 + 20.0 * np.sin(index / 15.0)
        minute, second = divmod(index, 60)
        rover_lines.append(
            f"2026-07-17T00:{minute:02d}:{second:02d},{along * 25.0},{northing},100.0,{total_field:.6f},{line},S{index:04d},traverse"
        )
        base_field = 49_000.0 + 2.0 * np.sin(index / 50.0)
        base_lines.append(f"2026-07-17T00:{minute:02d}:{second:02d},{base_field:.6f}")
    rover.write_text("\n".join(rover_lines), encoding="utf-8")
    base.write_text("\n".join(base_lines), encoding="utf-8")
    return rover, base


@pytest.fixture
def magnetic_datasets(magnetic_files):
    rover_path, base_path = magnetic_files
    reader = MagneticReader()
    rover = reader.read_rover(
        rover_path,
        crs="EPSG:32643",
        metadata={
            "instrument_make": "Enerson",
            "instrument_model": "ENmag37",
            "sensor_serial_number": "ENM-001",
            "operator": "TGP",
            "project_name": "Magnetic Test",
        },
    )
    base = reader.read_base(base_path, crs="EPSG:32643")
    return rover, base
