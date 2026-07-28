from datetime import datetime, timedelta

import numpy as np
import pytest

from modules.acquisition.qc import TimingQC
from modules.em.qc import ImpedanceQC, PhaseQC
from modules.gravity.qc import BouguerCorrectionQC, FreeAirCorrectionQC
from modules.magnetic.qc import DiurnalCorrectionQC
from modules.seismic.processing_tools import AreaAnalyzer, FirstBreakAutoPicker, RefractionLayerAnalysis, TraceFilter


def test_magnetic_diurnal_correction() -> None:
    start = datetime(2026, 1, 1)
    result = DiurnalCorrectionQC().apply([{'timestamp': start, 'total_field': 50000.0, 'base_field': 100.0}, {'timestamp': start + timedelta(seconds=10), 'total_field': 50010.0, 'base_field': 110.0}])
    assert result['records'][1]['corrected_total_field'] == 50000.0


def test_gravity_and_em_qc() -> None:
    record = {'latitude': 30.0, 'elevation_m': 100.0, 'observed_gravity_mgal': 980000.0}
    assert FreeAirCorrectionQC().apply([record])['passed']
    assert 'bouguer_anomaly_mgal' in BouguerCorrectionQC().apply([record])['records'][0]
    em = {'frequency_hz': 1.0, 'impedance_real': 3.0, 'impedance_imag': 4.0}
    assert ImpedanceQC(maximum=5.0).apply([em])['passed']
    assert PhaseQC().apply([em])['passed']


def test_timing_and_seismic_processing() -> None:
    start = datetime(2026, 1, 1)
    assert TimingQC().apply([{'timestamp': start}, {'timestamp': start + timedelta(seconds=1)}])['passed']
    traces = np.zeros((2, 200))
    traces[:, 120:] = 10.0
    assert len(FirstBreakAutoPicker(5, 20, 2.0).pick(traces, 1.0)) == 2
    assert TraceFilter().apply(np.sin(np.linspace(0, 20, 200)), 1.0, 'lowpass', high_hz=50).shape == (200,)
    assert AreaAnalyzer().analyze(traces, 1.0)['rms'] > 0
    assert RefractionLayerAnalysis().fit([0, 100, 200], [0, 50, 100])['velocity_m_s'] == pytest.approx(2000.0)
