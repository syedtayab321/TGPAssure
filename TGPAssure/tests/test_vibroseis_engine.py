import numpy as np

from modules.vibroseis import SweepParameters, VibroseisEngine


def test_linear_sweep_and_klauder_peak():
    e = VibroseisEngine()
    r = e.design_sweep(SweepParameters(5, 80, 8, 500, "linear", 0.2, 0.2))
    assert r.samples.size == 4000
    assert abs(r.klauder_wavelet.max() - 1.0) < 1e-8
    assert abs(r.autocorrelation_lag_s[np.argmax(r.klauder_wavelet)]) < 1e-12
    assert r.instantaneous_frequency_hz[0] == 5
    assert r.instantaneous_frequency_hz[-1] < 80.1


def test_signal_qc_recovers_known_delay_and_amplitude():
    e = VibroseisEngine()
    fs = 1000.0
    s = e.design_sweep(SweepParameters(10, 100, 2, fs, "linear", 0.1, 0.1)).samples
    delay = 17
    measured = np.concatenate([np.zeros(delay), 2.0 * s])
    ref = np.concatenate([s, np.zeros(delay)])
    q = e.signal_qc(ref, measured, fs, (10, 100))
    assert abs(abs(q.normalized_correlation) - 1.0) < 1e-5
    assert abs(q.lag_samples - delay) <= 1
    assert abs(q.amplitude_ratio_db - 6.0206) < 0.05


def test_ground_force_inertial_sum():
    e = VibroseisEngine()
    a1 = np.array([1.0, -1.0, 2.0])
    a2 = np.array([2.0, 1.0, -1.0])
    r = e.calculate_ground_force(a1, a2, 1000, 500, 100)
    np.testing.assert_allclose(r.ground_force_n, [2000, -500, 1500])


def test_productivity_cycle_equation():
    r = VibroseisEngine.productivity(12, 2, listen_time_s=4, pad_up_down_s=8, move_time_s=24)
    assert r.cycle_time_per_vp_s == 64
    assert abs(r.theoretical_vp_per_hour - 56.25) < 1e-12
    assert abs(r.active_sweep_fraction - 0.375) < 1e-12
