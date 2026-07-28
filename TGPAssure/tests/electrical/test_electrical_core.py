from __future__ import annotations

from pathlib import Path

import numpy as np

from modules.electrical.constants import ElectricalMethod
from modules.electrical.processing import ElectricalProcessingEngine
from modules.electrical.qc_engine import ElectricalQcEngine
from modules.electrical.reader import ElectricalReader


def _write(path: Path, text: str) -> Path:
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def test_reader_detects_ert_and_true_reciprocal_pairs(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "ert.csv",
        """
A,B,M,N,Current_mA,Voltage_mV,Apparent_Resistivity
0,10,20,30,100,10,100
20,30,0,10,100,10.5,105
0,10,20,30,100,10.1,101
""",
    )
    reader = ElectricalReader()
    inspection = reader.inspect(path)
    assert inspection["is_electrical_candidate"] is True
    assert inspection["inferred_method"] == ElectricalMethod.ERT.value

    dataset = ElectricalProcessingEngine().derive_standard_fields(reader.read(path))
    assert dataset.method == ElectricalMethod.ERT
    assert dataset.metadata["reciprocal_pair_count"] == 1
    reciprocal = dataset.numeric("reciprocal_error_pct")
    assert np.count_nonzero(np.isfinite(reciprocal)) == 2
    assert dataset.has("array_type")


def test_duplicate_normal_readings_are_not_reciprocals(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "duplicates.csv",
        """
A,B,M,N,Apparent_Resistivity
0,10,20,30,100
0,10,20,30,102
""",
    )
    dataset = ElectricalProcessingEngine().derive_standard_fields(ElectricalReader().read(path))
    assert dataset.metadata.get("reciprocal_pair_count", 0) == 0
    assert not dataset.has("reciprocal_error_pct")


def test_ves_with_m_chargeability_is_not_misclassified_as_tdip(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "ves.csv",
        """
AB/2,MN/2,Rhoa,M,Q
1,0.5,100,3.1,1.2
2,0.5,110,3.0,1.0
4,1,125,2.9,1.1
8,1,140,2.8,1.3
16,2,155,2.7,1.4
""",
    )
    dataset = ElectricalReader().read(path)
    assert dataset.method == ElectricalMethod.VES
    assert dataset.has("chargeability_mv_v")
    result = ElectricalQcEngine().run(dataset)
    assert len(result.stages) == 7
    assert any(stage.stage_key == "method_specific" for stage in result.stages)


def test_tdip_decay_windows_are_preserved_and_checked(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "tdip.csv",
        """
A,B,M,N,Rhoa,Chargeability,M1,M2,M3
0,10,20,30,100,12,20,15,11
10,20,30,40,110,15,30,15,25
""",
    )
    dataset = ElectricalReader().read(path)
    assert dataset.method == ElectricalMethod.TDIP
    assert all(dataset.has(name) for name in ("window_01", "window_02", "window_03"))
    result = ElectricalQcEngine().run(dataset)
    stage = next(stage for stage in result.stages if stage.stage_key == "method_specific")
    assert stage.metrics["decay_window_count"] == 3


def test_sip_phase_degrees_are_normalized_to_milliradians(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "sip.csv",
        """
Station,Frequency_Hz,Phase_Deg,Amplitude
1,0.1,1.0,100
1,1,2.0,95
1,10,3.0,90
""",
    )
    dataset = ElectricalReader().read(path)
    assert dataset.method == ElectricalMethod.SIP
    assert dataset.has("phase_mrad")
    assert np.isclose(dataset.numeric("phase_mrad")[0], np.deg2rad(1.0) * 1000.0)


def test_sp_drift_correction_preserves_original(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "sp.csv",
        """
Station,SP_mV,is_base
0,10,1
1,15,0
2,20,0
3,14,1
""",
    )
    dataset = ElectricalReader().read(path)
    original = dataset.numeric("sp_mv").copy()
    corrected = ElectricalProcessingEngine.sp_drift_correct(dataset)
    assert np.array_equal(dataset.numeric("sp_mv"), original)
    assert corrected.has("sp_corrected_mv")
    assert corrected.has("sp_drift_mv")


def test_malm_requires_source_but_equipotential_does_not(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "potential.csv",
        """
Easting,Northing,Voltage_mV
500000,3700000,10
500010,3700000,12
500020,3700000,11
""",
    )
    reader = ElectricalReader()
    equip = reader.read(path, ElectricalMethod.EQUIPOTENTIAL)
    equip_result = ElectricalQcEngine().run(equip)
    equip_errors = [f.code for f in equip_result.findings if f.severity in {"error", "critical"}]
    assert "ELEC-MALM-SOURCE" not in equip_errors

    malm = reader.read(path, ElectricalMethod.MALM)
    malm_result = ElectricalQcEngine().run(malm)
    assert any(f.code == "ELEC-MALM-SOURCE" and f.severity == "error" for f in malm_result.findings)


def test_telluric_electric_field_and_timestamp_qc(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "telluric.csv",
        """
Timestamp,Station,Electric_Field_mV_km
2026-01-01T00:00:00,1,12.1
2026-01-01T00:01:00,1,11.8
2026-01-01T00:02:00,1,12.0
""",
    )
    dataset = ElectricalReader().read(path, ElectricalMethod.TELLURIC)
    assert dataset.has("electric_field_mv_km")
    result = ElectricalQcEngine().run(dataset)
    assert not any(f.code == "ELEC-TELLURIC-TIME" for f in result.findings)


def test_all_supported_method_qc_runs_return_complete_stage_set(tmp_path: Path) -> None:
    fixtures = {
        ElectricalMethod.ERT: "A,B,M,N,Apparent_Resistivity\n0,10,20,30,100\n",
        ElectricalMethod.VES: "AB/2,MN/2,Rhoa\n1,0.5,100\n2,0.5,110\n",
        ElectricalMethod.PROFILING: "Station,Rhoa\n0,100\n10,110\n",
        ElectricalMethod.TDIP: "Station,Chargeability\n0,10\n10,11\n",
        ElectricalMethod.FDIP: "Station,Frequency_Hz,Chargeability\n0,1,10\n0,10,8\n",
        ElectricalMethod.SIP: "Station,Frequency_Hz,Phase_mrad\n0,0.1,10\n0,1,12\n0,10,15\n",
        ElectricalMethod.SP: "Station,SP_mV\n0,1\n10,2\n",
        ElectricalMethod.MALM: "Source_ID,Easting,Northing,Voltage_mV\nS1,1,1,10\nS1,2,1,12\n",
        ElectricalMethod.EQUIPOTENTIAL: "Easting,Northing,Voltage_mV\n1,1,10\n2,1,12\n",
        ElectricalMethod.TELLURIC: "Timestamp,Electric_Field_mV_km\n2026-01-01T00:00:00,10\n2026-01-01T00:01:00,11\n",
    }
    reader = ElectricalReader()
    for method, text in fixtures.items():
        path = _write(tmp_path / f"{method.value}.csv", text)
        dataset = reader.read(path, method)
        result = ElectricalQcEngine().run(dataset)
        assert len(result.stages) == 7, method
        assert {stage.stage_key for stage in result.stages} == {
            "schema", "geometry", "signal", "resistivity", "reciprocity", "method_specific", "summary"
        }


def test_qc_history_persists_electrical_run(tmp_path: Path) -> None:
    from core.data_access.db_engine import DatabaseEngine
    from core.data_access.qc_history_repository import QcHistoryRepository
    from modules.electrical.history import save_electrical_qc_run

    database = DatabaseEngine(tmp_path / "electrical_history.tgp-project")
    connection = database.get_write_connection()
    try:
        migration = Path(__file__).resolve().parents[2] / "migrations" / "0001_initial.sql"
        connection.executescript(migration.read_text(encoding="utf-8"))
        connection.commit()
    finally:
        connection.close()

    source = _write(tmp_path / "sp_history.csv", "Station,SP_mV,is_base\n0,10,1\n1,12,0\n2,11,1")
    result = ElectricalQcEngine().run(ElectricalReader().read(source))
    run_uuid = save_electrical_qc_run(database, result)
    runs = QcHistoryRepository(database).list_runs(module="electrical", limit=10)
    assert run_uuid
    assert len(runs) == 1
    assert runs[0]["module"] == "electrical"
    assert runs[0]["overall_result"] == result.status


def test_pdf_and_xlsx_reports_render_with_qc_graphs(tmp_path: Path) -> None:
    from modules.electrical.reporting import ElectricalReportBuilder

    source = _write(
        tmp_path / "report_ert.csv",
        "A,B,M,N,Apparent_Resistivity,Contact_Resistance,Q_pct\n"
        "0,10,20,30,100,1500,1\n"
        "20,30,0,10,103,1600,1.2\n",
    )
    result = ElectricalQcEngine().run(ElectricalReader().read(source))
    builder = ElectricalReportBuilder()
    pdf = builder.render(result, tmp_path / "electrical_qc.pdf", "pdf")
    xlsx = builder.render(result, tmp_path / "electrical_qc.xlsx", "xlsx")
    assert pdf.is_file() and pdf.stat().st_size > 5000
    assert xlsx.is_file() and xlsx.stat().st_size > 5000
