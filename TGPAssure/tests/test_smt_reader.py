from __future__ import annotations

from datetime import date
from pathlib import Path

from modules.seismic.smt import ImportOptions, SmtResultReader


def test_smt_reader_parses_csv_and_corrects_old_date(tmp_path: Path) -> None:
    source = tmp_path / "SMT300_results.csv"
    source.write_text(
        "String,Tester,Date,Model,Resistance,Frequency,Damping,Distortion,Result\n"
        "101,SMT-A,01/01/2000 08:30,SMT300,180,10.1,0.61,0.02,PASS\n"
        "102,SMT-B,04/08/2026 09:00,SGT-II,250,9.8,0.59,0.03,FAIL\n",
        encoding="utf-8",
    )
    reader = SmtResultReader()
    records, warnings = reader.read(
        source,
        ImportOptions(minimum_valid_year=2013, bad_date_mode="correct", replacement_date="file"),
    )
    assert len(records) == 2
    assert records[0].string_no == "101"
    assert records[0].date_corrected is True
    assert records[0].tested_at is not None
    assert records[0].tested_at.date() == date.fromtimestamp(source.stat().st_mtime)
    assert records[1].model == "SGT-II"
    assert records[1].resistance == 250.0
    assert warnings


def test_smt_reader_parses_key_value_blocks(tmp_path: Path) -> None:
    source = tmp_path / "tester.out"
    source.write_text(
        "String No: 8801\nTester: SMT-01\nTest Date: 2026-08-04 12:00\nResistance: 179.5 Ohm\nFrequency: 10.2 Hz\n\n"
        "String No: 8802\nTester: SMT-02\nTest Date: 2026-08-04 12:05\nResistance: 181.0 Ohm\nFrequency: 10.0 Hz\n",
        encoding="utf-8",
    )
    records, warnings = SmtResultReader().read(source, ImportOptions())
    assert not warnings
    assert [record.string_no for record in records] == ["8801", "8802"]
    assert records[1].frequency == 10.0
