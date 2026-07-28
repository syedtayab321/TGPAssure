from pathlib import Path
from modules.gravity.reader import GravityReader


def test_csv_reader_normalizes_land_gravity(tmp_path: Path):
    path = tmp_path / "gravity.csv"
    path.write_text("station,timestamp,latitude,longitude,elevation_m,gravity,tide\nS1,2026-01-01 10:00:00,33.7,73.0,600,978000.1,0.02\n", encoding="utf-8")
    dataset = GravityReader().read_observations(path)
    assert dataset.record_count == 1
    assert dataset.channel("observed_gravity_mgal")[0] == 978000.1
    assert dataset.channel("tide_correction_mgal")[0] == 0.02
