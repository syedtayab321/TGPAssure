from __future__ import annotations

import json
import numpy as np
from typing import Dict, Any

try:
    from scipy.signal import welch, find_peaks
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

from core.domain.qc_engine import QCStage, QCStageResult, QCStatus, QCSeverity, QCFinding


class FrequencyQCStage(QCStage):
    def __init__(self, min_bandwidth: float = 10.0, sample_count_for_psd: int = 1024) -> None:
        self.min_bandwidth = min_bandwidth
        self.sample_count_for_psd = sample_count_for_psd

    def run(self, context: Dict[str, Any]) -> QCStageResult:
        findings = []
        reader = context.get("reader")
        if reader is None:
            return QCStageResult(
                stage_name="FrequencyQC",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": "No SEG-Y reader available"})
            )

        if not SCIPY_AVAILABLE:
            return QCStageResult(
                stage_name="FrequencyQC",
                status=QCStatus.WARN,
                summary_json=json.dumps({"warning": "SciPy not available, skipping spectral analysis"}),
                findings=[
                    QCFinding(
                        rule_id="frequency_scipy_missing",
                        severity=QCSeverity.WARNING,
                        message="SciPy not available for spectral analysis",
                        suggested_action="Install scipy for full frequency analysis"
                    )
                ]
            )

        try:
            trace_count = reader.get_trace_count()
            sample_count = reader.get_sample_count()
            sample_interval_ms = reader.get_sample_interval()

            if trace_count == 0:
                return QCStageResult(
                    stage_name="FrequencyQC",
                    status=QCStatus.FAIL,
                    summary_json=json.dumps({"error": "No traces to analyze"})
                )

            fs = 1000.0 / sample_interval_ms if sample_interval_ms > 0 else 500.0
            psd_samples = min(self.sample_count_for_psd, sample_count)
            psd_samples = psd_samples - (psd_samples % 2)

            if psd_samples < 16:
                return QCStageResult(
                    stage_name="FrequencyQC",
                    status=QCStatus.WARN,
                    summary_json=json.dumps({"warning": "Too few samples for spectral analysis"})
                )

            test_traces = min(10, trace_count)
            data = reader.read_trace_window((0, test_traces), (0, psd_samples))

            bandwidths = []
            for i in range(data.shape[0]):
                trace_data = data[i, :]
                freqs, psd = welch(trace_data, fs=fs, nperseg=min(256, len(trace_data)))

                half_idx = len(freqs) // 2
                freqs_half = freqs[:half_idx]
                psd_half = psd[:half_idx]

                if len(psd_half) > 0:
                    max_idx = np.argmax(psd_half)
                    peak_freq = freqs_half[max_idx]

                    threshold = 0.5 * np.max(psd_half)
                    above_threshold = psd_half > threshold

                    if np.sum(above_threshold) > 1:
                        freq_indices = np.where(above_threshold)[0]
                        bandwidth = freqs_half[freq_indices[-1]] - freqs_half[freq_indices[0]]
                        bandwidths.append(float(bandwidth))

            if bandwidths:
                avg_bandwidth = np.mean(bandwidths)

                if avg_bandwidth < self.min_bandwidth:
                    findings.append(
                        QCFinding(
                            rule_id="frequency_low_bandwidth",
                            severity=QCSeverity.WARNING,
                            message=f"Low average bandwidth: {avg_bandwidth:.1f} Hz",
                            suggested_action="Check for low-frequency noise or data quality issues"
                        )
                    )

                context["avg_bandwidth"] = avg_bandwidth
                status = QCStatus.WARN if findings else QCStatus.PASS

                return QCStageResult(
                    stage_name="FrequencyQC",
                    status=status,
                    summary_json=json.dumps({
                        "avg_bandwidth_hz": float(avg_bandwidth),
                        "traces_analyzed": len(bandwidths),
                        "min_bandwidth_threshold": self.min_bandwidth
                    }),
                    findings=findings
                )

            return QCStageResult(
                stage_name="FrequencyQC",
                status=QCStatus.WARN,
                summary_json=json.dumps({"warning": "Could not compute bandwidth"}),
                findings=[
                    QCFinding(
                        rule_id="frequency_no_bandwidth",
                        severity=QCSeverity.WARNING,
                        message="Could not compute spectral bandwidth",
                        suggested_action="Check data quality and content"
                    )
                ]
            )

        except Exception as e:
            return QCStageResult(
                stage_name="FrequencyQC",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": str(e)}),
                findings=[
                    QCFinding(
                        rule_id="frequency_qc_exception",
                        severity=QCSeverity.ERROR,
                        message=f"Frequency QC failed: {str(e)}",
                        suggested_action="Check data format and scipy installation"
                    )
                ]
            )