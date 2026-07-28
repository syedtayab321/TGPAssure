from __future__ import annotations

from modules.magnetic.constants import BASE_TOTAL_FIELD, RAW_TOTAL_FIELD
from modules.magnetic.models import MagneticDataRole, MagneticSurveyType
from modules.magnetic.reader import MagneticReader


def test_reader_normalizes_rover_and_base(magnetic_files):
    rover_path, base_path = magnetic_files
    reader = MagneticReader()
    rover = reader.read_rover(rover_path, crs="EPSG:32643")
    base = reader.read_base(base_path, crs="EPSG:32643")

    assert rover.record_count == 240
    assert base.record_count == 240
    assert rover.role is MagneticDataRole.ROVER
    assert base.role is MagneticDataRole.BASE
    assert base.survey_type is MagneticSurveyType.BASE_STATION
    assert RAW_TOTAL_FIELD in rover.channels
    assert BASE_TOTAL_FIELD in base.channels
    assert rover.line_groups().keys() == {"L001", "L002"}
    assert rover.crs == "EPSG:32643"


def test_reader_inspection_returns_detected_mapping(magnetic_files):
    rover_path, _ = magnetic_files
    inspection = MagneticReader().inspect(rover_path)
    assert inspection["mapping"]["total_field"] == "total_field"
    assert inspection["mapping"]["x"] == "easting"
    assert inspection["mapping"]["y"] == "northing"
    assert not inspection["required_missing"]


def test_reader_accepts_variable_whitespace_base_station_file(tmp_path):
    path = tmp_path / "base_station.txt"
    path.write_text(
        "timestamp    total_field\n"
        "2026-07-17T00:00:00      49123.25\n"
        "2026-07-17T00:00:01   49123.75\n",
        encoding="utf-8",
    )
    dataset = MagneticReader().read_base(path)
    assert dataset.record_count == 2
    assert dataset.role is MagneticDataRole.BASE
    assert BASE_TOTAL_FIELD in dataset.channels
    assert dataset.channels[BASE_TOTAL_FIELD].tolist() == [49123.25, 49123.75]
