from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Optional

import numpy as np
from scipy import signal


_EPS = np.finfo(float).eps


@dataclass(frozen=True)
class SweepParameters:
    """Parameters defining a Vibroseis pilot sweep.

    Frequencies are in hertz, duration in seconds and sample_rate_hz in samples/s.
    ``sweep_type`` is ``linear`` or ``logarithmic``.  A half-cosine taper is
    applied independently at each end.  Tapers must not overlap.
    """

    start_frequency_hz: float = 5.0
    end_frequency_hz: float = 100.0
    duration_s: float = 12.0
    sample_rate_hz: float = 1000.0
    sweep_type: str = "linear"
    taper_in_s: float = 0.25
    taper_out_s: float = 0.25
    amplitude: float = 1.0
    phase_deg: float = 0.0


@dataclass(frozen=True)
class SweepResult:
    time_s: np.ndarray
    samples: np.ndarray
    instantaneous_frequency_hz: np.ndarray
    frequency_hz: np.ndarray
    amplitude_spectrum: np.ndarray
    autocorrelation_lag_s: np.ndarray
    klauder_wavelet: np.ndarray


@dataclass(frozen=True)
class SignalQcResult:
    normalized_correlation: float
    lag_samples: int
    lag_ms: float
    rms_reference: float
    rms_measured: float
    amplitude_ratio_db: float
    phase_error_rms_deg: float
    spectral_coherence_mean: float
    in_band_energy_fraction: float
    dominant_frequency_hz: float
    crest_factor: float


@dataclass(frozen=True)
class GroundForceResult:
    time_s: np.ndarray
    ground_force_n: np.ndarray
    peak_force_n: float
    rms_force_n: float
    impulse_ns: float


@dataclass(frozen=True)
class ProductivityResult:
    cycle_time_per_vp_s: float
    theoretical_vp_per_hour: float
    theoretical_sweeps_per_hour: float
    active_sweep_fraction: float


class VibroseisEngine:
    """Numerical engine for Vibroseis sweep design and source QC.

    The implementation deliberately works with generic physical signals rather
    than proprietary VE464/shot-controller formats.  Manufacturer telemetry can
    be imported after export to CSV/text without fabricating undocumented fields.
    """

    @staticmethod
    def _validate_sweep(p: SweepParameters) -> None:
        if p.start_frequency_hz <= 0 or p.end_frequency_hz <= 0:
            raise ValueError("Sweep start/end frequencies must be greater than zero.")
        if p.start_frequency_hz == p.end_frequency_hz:
            raise ValueError("Sweep start and end frequencies must be different.")
        if p.duration_s <= 0:
            raise ValueError("Sweep duration must be greater than zero.")
        if p.sample_rate_hz <= 2.0 * max(p.start_frequency_hz, p.end_frequency_hz):
            raise ValueError("Sample rate must be greater than twice the highest sweep frequency (Nyquist).")
        if p.taper_in_s < 0 or p.taper_out_s < 0:
            raise ValueError("Taper lengths cannot be negative.")
        if p.taper_in_s + p.taper_out_s > p.duration_s:
            raise ValueError("The sum of the start/end tapers cannot exceed sweep duration.")
        if p.amplitude < 0:
            raise ValueError("Sweep amplitude cannot be negative.")
        if p.sweep_type.lower() not in {"linear", "logarithmic", "log"}:
            raise ValueError("Sweep type must be 'linear' or 'logarithmic'.")

    @staticmethod
    def _half_cosine_taper(n: int, n_in: int, n_out: int) -> np.ndarray:
        window = np.ones(n, dtype=np.float64)
        if n_in > 0:
            # 0 -> 1 smoothly; endpoint=False avoids duplicating the plateau sample.
            x = np.arange(n_in, dtype=np.float64) / max(1, n_in)
            window[:n_in] = 0.5 * (1.0 - np.cos(np.pi * x))
        if n_out > 0:
            x = np.arange(n_out, dtype=np.float64) / max(1, n_out)
            window[-n_out:] = 0.5 * (1.0 + np.cos(np.pi * x))
        return window

    def design_sweep(self, parameters: SweepParameters) -> SweepResult:
        self._validate_sweep(parameters)
        p = parameters
        n = max(2, int(round(p.duration_s * p.sample_rate_hz)))
        t = np.arange(n, dtype=np.float64) / p.sample_rate_hz
        method = "logarithmic" if p.sweep_type.lower() in {"logarithmic", "log"} else "linear"
        sweep = signal.chirp(
            t,
            f0=p.start_frequency_hz,
            f1=p.end_frequency_hz,
            t1=p.duration_s,
            method=method,
            phi=p.phase_deg,
        ).astype(np.float64, copy=False)

        n_in = min(n, int(round(p.taper_in_s * p.sample_rate_hz)))
        n_out = min(n - n_in, int(round(p.taper_out_s * p.sample_rate_hz)))
        sweep *= self._half_cosine_taper(n, n_in, n_out)
        sweep *= p.amplitude

        if method == "linear":
            inst_f = p.start_frequency_hz + (p.end_frequency_hz - p.start_frequency_hz) * (t / p.duration_s)
        else:
            ratio = p.end_frequency_hz / p.start_frequency_hz
            inst_f = p.start_frequency_hz * np.power(ratio, t / p.duration_s)

        freq = np.fft.rfftfreq(n, d=1.0 / p.sample_rate_hz)
        spec = np.abs(np.fft.rfft(sweep))
        if spec.size and spec.max() > 0:
            spec = spec / spec.max()

        auto = signal.correlate(sweep, sweep, mode="full", method="fft")
        norm = float(np.dot(sweep, sweep))
        if norm > 0:
            auto = auto / norm
        lag_samples = signal.correlation_lags(n, n, mode="full")
        lag_s = lag_samples / p.sample_rate_hz
        return SweepResult(t, sweep, inst_f, freq, spec, lag_s, auto)

    @staticmethod
    def correlate_trace(trace: Iterable[float], pilot: Iterable[float], sample_rate_hz: float) -> tuple[np.ndarray, np.ndarray]:
        x = np.asarray(trace, dtype=np.float64).reshape(-1)
        s = np.asarray(pilot, dtype=np.float64).reshape(-1)
        if x.size == 0 or s.size == 0:
            raise ValueError("Trace and pilot must contain samples.")
        if sample_rate_hz <= 0:
            raise ValueError("Sample rate must be greater than zero.")
        x = np.nan_to_num(x - np.nanmean(x), copy=False)
        s = np.nan_to_num(s - np.nanmean(s), copy=False)
        corr = signal.correlate(x, s, mode="full", method="fft")
        energy = np.sqrt(float(np.dot(x, x)) * float(np.dot(s, s)))
        if energy > 0:
            corr = corr / energy
        lags = signal.correlation_lags(x.size, s.size, mode="full") / sample_rate_hz
        return lags, corr

    @staticmethod
    def _aligned_pair(reference: np.ndarray, measured: np.ndarray, lag: int) -> tuple[np.ndarray, np.ndarray]:
        if lag > 0:
            m = measured[lag:]
            r = reference[: m.size]
        elif lag < 0:
            r = reference[-lag:]
            m = measured[: r.size]
        else:
            n = min(reference.size, measured.size)
            r, m = reference[:n], measured[:n]
        n = min(r.size, m.size)
        return r[:n], m[:n]

    def signal_qc(
        self,
        reference: Iterable[float],
        measured: Iterable[float],
        sample_rate_hz: float,
        band_hz: Optional[tuple[float, float]] = None,
    ) -> SignalQcResult:
        """Compare a measured pilot/reference/ground-force signal to a reference.

        Lag is estimated from normalized cross-correlation.  Phase error is the
        RMS unwrapped cross-spectral phase within bins carrying at least 5% of
        reference peak spectral energy.  Mean magnitude-squared coherence is
        evaluated across the requested sweep band (or all positive frequencies).
        """
        ref = np.nan_to_num(np.asarray(reference, dtype=np.float64).reshape(-1))
        mea = np.nan_to_num(np.asarray(measured, dtype=np.float64).reshape(-1))
        if ref.size < 8 or mea.size < 8:
            raise ValueError("At least 8 samples are required for Vibroseis signal QC.")
        if sample_rate_hz <= 0:
            raise ValueError("Sample rate must be greater than zero.")
        ref = ref - np.mean(ref)
        mea = mea - np.mean(mea)
        corr = signal.correlate(mea, ref, mode="full", method="fft")
        denom = np.sqrt(np.dot(ref, ref) * np.dot(mea, mea))
        corr_norm = corr / denom if denom > 0 else np.zeros_like(corr)
        lag_axis = signal.correlation_lags(mea.size, ref.size, mode="full")
        peak_i = int(np.argmax(np.abs(corr_norm)))
        lag = int(lag_axis[peak_i])
        peak_corr = float(corr_norm[peak_i])
        r, m = self._aligned_pair(ref, mea, lag)
        if r.size < 8:
            raise ValueError("Signals have insufficient overlap after lag alignment.")

        rms_r = float(np.sqrt(np.mean(r * r)))
        rms_m = float(np.sqrt(np.mean(m * m)))
        amp_db = float(20.0 * np.log10(max(rms_m, _EPS) / max(rms_r, _EPS)))
        crest = float(np.max(np.abs(m)) / max(rms_m, _EPS))

        nfft = int(2 ** np.ceil(np.log2(r.size)))
        R = np.fft.rfft(r * np.hanning(r.size), n=nfft)
        M = np.fft.rfft(m * np.hanning(m.size), n=nfft)
        f = np.fft.rfftfreq(nfft, d=1.0 / sample_rate_hz)
        ref_power = np.abs(R) ** 2
        cross_phase = np.angle(M * np.conj(R))
        valid = ref_power >= (0.05 * ref_power.max() if ref_power.size else np.inf)
        if band_hz is not None:
            lo, hi = sorted(map(float, band_hz))
            valid &= (f >= lo) & (f <= hi)
        valid &= f > 0
        phase_deg = np.rad2deg(cross_phase[valid]) if np.any(valid) else np.array([np.nan])
        phase_rms = float(np.sqrt(np.nanmean(phase_deg ** 2)))

        nperseg = min(1024, max(32, 2 ** int(np.floor(np.log2(r.size)))))
        if nperseg > r.size:
            nperseg = r.size
        fc, coh = signal.coherence(r, m, fs=sample_rate_hz, window="hann", nperseg=nperseg)
        coh_mask = fc > 0
        if band_hz is not None:
            lo, hi = sorted(map(float, band_hz))
            coh_mask &= (fc >= lo) & (fc <= hi)
        coherence_mean = float(np.nanmean(coh[coh_mask])) if np.any(coh_mask) else float("nan")

        ps = np.abs(np.fft.rfft(m * np.hanning(m.size))) ** 2
        ff = np.fft.rfftfreq(m.size, d=1.0 / sample_rate_hz)
        positive = ff > 0
        dom = float(ff[np.argmax(np.where(positive, ps, -np.inf))]) if np.any(positive) else 0.0
        if band_hz is not None:
            lo, hi = sorted(map(float, band_hz))
            in_band = (ff >= lo) & (ff <= hi)
            in_band_fraction = float(ps[in_band].sum() / max(ps.sum(), _EPS))
        else:
            in_band_fraction = 1.0

        return SignalQcResult(
            normalized_correlation=peak_corr,
            lag_samples=lag,
            lag_ms=1000.0 * lag / sample_rate_hz,
            rms_reference=rms_r,
            rms_measured=rms_m,
            amplitude_ratio_db=amp_db,
            phase_error_rms_deg=phase_rms,
            spectral_coherence_mean=coherence_mean,
            in_band_energy_fraction=in_band_fraction,
            dominant_frequency_hz=dom,
            crest_factor=crest,
        )

    @staticmethod
    def calculate_ground_force(
        reaction_mass_accel_m_s2: Iterable[float],
        baseplate_accel_m_s2: Iterable[float],
        reaction_mass_kg: float,
        baseplate_mass_kg: float,
        sample_rate_hz: float,
        reaction_sign: float = 1.0,
        baseplate_sign: float = 1.0,
    ) -> GroundForceResult:
        """Compute estimated ground force from inertial-force summation.

        F(t) = s_r M_r a_r(t) + s_b M_b a_b(t)

        Sensor polarity depends on the vibrator/controller wiring, so signs are
        explicit inputs and must be verified against the equipment convention.
        """
        ar = np.nan_to_num(np.asarray(reaction_mass_accel_m_s2, dtype=np.float64).reshape(-1))
        ab = np.nan_to_num(np.asarray(baseplate_accel_m_s2, dtype=np.float64).reshape(-1))
        if reaction_mass_kg <= 0 or baseplate_mass_kg <= 0:
            raise ValueError("Reaction-mass and baseplate masses must be greater than zero.")
        if sample_rate_hz <= 0:
            raise ValueError("Sample rate must be greater than zero.")
        n = min(ar.size, ab.size)
        if n == 0:
            raise ValueError("Acceleration arrays cannot be empty.")
        force = reaction_sign * reaction_mass_kg * ar[:n] + baseplate_sign * baseplate_mass_kg * ab[:n]
        t = np.arange(n, dtype=np.float64) / sample_rate_hz
        peak = float(np.max(np.abs(force)))
        rms = float(np.sqrt(np.mean(force * force)))
        impulse = float(np.trapezoid(force, dx=1.0 / sample_rate_hz))
        return GroundForceResult(t, force, peak, rms, impulse)

    @staticmethod
    def productivity(
        sweep_length_s: float,
        sweeps_per_vp: int,
        listen_time_s: float = 0.0,
        pad_up_down_s: float = 0.0,
        move_time_s: float = 0.0,
    ) -> ProductivityResult:
        if sweep_length_s <= 0 or sweeps_per_vp <= 0:
            raise ValueError("Sweep length and sweeps per VP must be greater than zero.")
        if min(listen_time_s, pad_up_down_s, move_time_s) < 0:
            raise ValueError("Cycle-time components cannot be negative.")
        per_sweep = sweep_length_s + listen_time_s
        cycle = sweeps_per_vp * per_sweep + pad_up_down_s + move_time_s
        vp_h = 3600.0 / cycle
        sweeps_h = vp_h * sweeps_per_vp
        active = (sweeps_per_vp * sweep_length_s) / cycle
        return ProductivityResult(cycle, vp_h, sweeps_h, active)

    @staticmethod
    def load_numeric_table(path: str | Path) -> tuple[list[str], np.ndarray]:
        """Load generic CSV/TXT Vibroseis telemetry exported as a numeric table.

        A header row is optional.  Comma, tab, semicolon and whitespace-delimited
        text are supported.  Non-numeric rows after the header are rejected.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(p)
        first = p.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        if not first:
            raise ValueError("Input telemetry file is empty.")
        line0 = first[0].strip()
        if "," in line0:
            delim = ","
        elif "\t" in line0:
            delim = "\t"
        elif ";" in line0:
            delim = ";"
        else:
            delim = None
        tokens = line0.split(delim) if delim else line0.split()
        has_header = any(not VibroseisEngine._is_float(tok.strip()) for tok in tokens)
        names = [tok.strip() or f"Column {i+1}" for i, tok in enumerate(tokens)] if has_header else []
        data = np.genfromtxt(p, delimiter=delim, skip_header=1 if has_header else 0, dtype=float)
        if data.ndim == 1:
            data = data[:, None]
        if data.size == 0 or data.shape[0] == 0:
            raise ValueError("No numeric telemetry rows were found.")
        if not names:
            names = [f"Column {i+1}" for i in range(data.shape[1])]
        if len(names) != data.shape[1]:
            names = [f"Column {i+1}" for i in range(data.shape[1])]
        return names, data

    @staticmethod
    def _is_float(value: str) -> bool:
        try:
            float(value)
            return True
        except ValueError:
            return False
