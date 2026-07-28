from __future__ import annotations

import json
import numpy as np
from typing import Dict, Any

try:
    from scipy.fft import fft, fftfreq
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

from core.domain.qc_engine import QCStage, QCStageResult, QCStatus, QCSeverity, QCFinding


class NoiseQCStage(QCStage):
    def __init__(self, spike_threshold: float = 10.0, sample_count_for_fft: int = 512) -> None:
        self.spike_threshold = spike_threshold
        self.sample_count_for_fft = sample_count_for_fft

    def run(self, context: Dict[str, Any]) -> QCStageResult:
        findings = []
        reader = context.get("reader")
        if reader is None:
            return QCStageResult(
                stage_name="NoiseQC",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": "No SEG-Y reader available"})
            )

        if not SCIPY_AVAILABLE:
            return QCStageResult(
                stage_name="NoiseQC",
                status=QCStatus.WARN,
                summary_json=json.dumps({"warning": "SciPy not available, skipping FFT analysis"}),
                findings=[
                    QCFinding(
                        rule_id="noise_scipy_missing",
                        severity=QCSeverity.WARNING,
                        message="SciPy not available for FFT analysis",
                        suggested_action="Install scipy for full noise analysis"
                    )
                ]
            )

        try:
            trace_count = reader.get_trace_count()
            sample_count = reader.get_sample_count()

            if trace_count == 0:
                return QCStageResult(
                    stage_name="NoiseQC",
                    status=QCStatus.FAIL,
                    summary_json=json.dumps({"error": "No traces to analyze"})
                )

            fft_samples = min(self.sample_count_for_fft, sample_count)
            fft_samples = fft_samples - (fft_samples % 2)

            if fft_samples < 4:
                return QCStageResult(
                    stage_name="NoiseQC",
                    status=QCStatus.WARN,
                    summary_json=json.dumps({"warning": "Too few samples for FFT"})
                )

            test_traces = min(10, trace_count)
            data = reader.read_trace_window((0, test_traces), (0, fft_samples))

            spike_counts = []
            for i in range(data.shape[0]):
                trace_data = data[i, :]
                fft_data = fft(trace_data)
                magnitudes = np.abs(fft_data)
                mean_mag = np.mean(magnitudes)
                std_mag = np.std(magnitudes)

                spike_count = np.sum((magnitudes - mean_mag) > (self.spike_threshold * std_mag))
                spike_counts.append(int(spike_count))

            context["spike_counts"] = spike_counts
            total_spikes = sum(spike_counts)
            avg_spikes = np.mean(spike_counts)

            if total_spikes > 0:
                findings.append(
                    QCFinding(
                        rule_id="noise_spikes_detected",
                        severity=QCSeverity.WARNING if avg_spikes < 5 else QCSeverity.ERROR,
                        message=f"Average {avg_spikes:.1f} spikes per trace detected",
                        suggested_action="Check for impulsive noise in data" if avg_spikes < 5 else "Investigate significant noise contamination"
                    )
                )

            status = QCStatus.WARN if findings else QCStatus.PASS

            return QCStageResult(
                stage_name="NoiseQC",
                status=status,
                summary_json=json.dumps({
                    "traces_analyzed": test_traces,
                    "total_spikes": total_spikes,
                    "average_spikes_per_trace": float(avg_spikes),
                    "spike_threshold": self.spike_threshold
                }),
                findings=findings
            )

        except Exception as e:
            return QCStageResult(
                stage_name="NoiseQC",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": str(e)}),
                findings=[
                    QCFinding(
                        rule_id="noise_qc_exception",
                        severity=QCSeverity.ERROR,
                        message=f"Noise QC failed: {str(e)}",
                        suggested_action="Check data format and scipy installation"
                    )
                ]
            )