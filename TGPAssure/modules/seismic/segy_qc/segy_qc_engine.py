from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from core.infrastructure.job import CancellationToken, Job, JobSpec
from modules.seismic.segy_qc.qc_models import SegyFinding, SegyRunSummary, SegyStageOutcome
from modules.seismic.segy_qc.qc_profiles import SegyQcProfile
from modules.seismic.segy_qc.qc_repository import SegyQcRepository
from modules.seismic.segy_qc.segy_reader import SegyReader, SegyTraceIndex
from core.domain.qc_engine import QCStageResult
from modules.seismic.segy_qc.stages.residual_statics_qc import ResidualStaticsQCStage
from modules.seismic.segy_qc.stages.velocity_qc import VelocityQCStage
from modules.seismic.segy_qc.stages.nmo_qc import NMOQCStage
from modules.seismic.segy_qc.stages.stack_qc import StackQCStage
from modules.seismic.segy_qc.stages.migration_qc import MigrationQCStage
from modules.seismic.segy_qc.stages.attribute_qc import AttributeQCStage
from modules.seismic.segy_qc.stages.repeatability_qc import RepeatabilityQCStage


STAGES: Tuple[Tuple[str, str], ...] = (
    ("file_integrity", "File Integrity"),
    ("textual_header", "Textual Header QC"),
    ("binary_header", "Binary Header QC"),
    ("trace_header", "Trace Header QC"),
    ("geometry", "Geometry QC"),
    ("coordinate", "Coordinate QC"),
    ("navigation", "Navigation QC"),
    ("trace_integrity", "Trace Integrity QC"),
    ("dead_zero", "Dead and Zero Trace QC"),
    ("noise", "Noisy Trace QC"),
    ("clipping_spike", "Clipping and Spike QC"),
    ("dc_amplitude", "DC Bias and Amplitude QC"),
    ("rms_energy", "RMS and Energy QC"),
    ("frequency", "Frequency and Bandwidth QC"),
    ("statics_timing", "Statics and Timing QC"),
    ("residual_statics", "Residual Statics QC"),
    ("velocity", "Velocity Analysis QC"),
    ("nmo", "NMO Correction QC"),
    ("stack", "Stack Quality QC"),
    ("migration", "Pre-Stack Time Migration QC"),
    ("attribute", "Post-Stack Attribute QC"),
    ("repeatability", "4D Repeatability QC"),
    ("summary", "Final Summary"),
)


@dataclass
class StageApprovalGate:
    enabled: bool = False

    def __post_init__(self) -> None:
        self._condition = threading.Condition()
        self._waiting_stage: Optional[str] = None
        self._approved_stage: Optional[str] = None
        self._cancelled = False

    def wait(self, stage_key: str, cancel_check: Callable[[], bool]) -> None:
        if not self.enabled:
            return
        with self._condition:
            self._waiting_stage = stage_key
            self._approved_stage = None
            while self._approved_stage != stage_key and not self._cancelled:
                if cancel_check():
                    self._cancelled = True
                    break
                self._condition.wait(timeout=0.25)
            self._waiting_stage = None
        if self._cancelled or cancel_check():
            raise InterruptedError("QC run cancelled while awaiting stage approval")

    def approve(self, stage_key: Optional[str] = None) -> None:
        with self._condition:
            target = stage_key or self._waiting_stage
            if target:
                self._approved_stage = target
                self._condition.notify_all()

    def cancel(self) -> None:
        with self._condition:
            self._cancelled = True
            self._condition.notify_all()


class SegyQcJob(Job):
    def __init__(
        self,
        run_uuid: str,
        file_path: str | Path,
        profile: SegyQcProfile,
        repository: SegyQcRepository,
        callbacks: Any,
        approval_gate: Optional[StageApprovalGate] = None,
        repeatability_base_path: Optional[str | Path] = None,
    ) -> None:
        spec = JobSpec(
            job_type="segy_qc",
            module="segy",
            priority=20,
            payload_json=json.dumps(
                {
                    "run_uuid": run_uuid,
                    "file_path": str(Path(file_path).expanduser().resolve()),
                    "profile": profile.key,
                    "repeatability_base_path": str(Path(repeatability_base_path).expanduser().resolve()) if repeatability_base_path else None,
                }
            ),
        )
        super().__init__(spec)
        self.run_uuid = run_uuid
        self.file_path = Path(file_path).expanduser().resolve()
        self.profile = profile
        self.repository = repository
        self.callbacks = callbacks
        self.approval_gate = approval_gate or StageApprovalGate(False)
        self.repeatability_base_path = (
            Path(repeatability_base_path).expanduser().resolve()
            if repeatability_base_path
            else None
        )
        self._outcomes: List[SegyStageOutcome] = []
        self._stage_index = 0
        self._stage_count = len(STAGES)
        self._cancel_token: Optional[CancellationToken] = None

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _cancelled(self) -> bool:
        return bool(self._cancel_token and self._cancel_token.is_cancelled())

    def _report_progress(self, stage_fraction: float, message: str) -> None:
        stage_fraction = max(0.0, min(1.0, float(stage_fraction)))
        overall = (self._stage_index + stage_fraction) / max(1, self._stage_count)
        job_id = self.get_job_id() or 0
        self.callbacks.qc_job_progress(job_id, overall, STAGES[self._stage_index][0], stage_fraction, message)

    def run(self, context: Any, cancel_token: CancellationToken) -> Dict[str, Any]:
        self._cancel_token = cancel_token
        started = datetime.now(timezone.utc)
        try:
            reader = SegyReader(self.file_path)
            state: Dict[str, Any] = {
                "reader": reader,
                "profile": self.profile,
                "thresholds": self.profile.thresholds,
                "outcomes": self._outcomes,
            }
            if self.repeatability_base_path is not None:
                try:
                    state["base_reader"] = SegyReader(self.repeatability_base_path)
                    state["base_file_path"] = str(self.repeatability_base_path)
                except Exception as exc:
                    state["base_reader_error"] = str(exc)
                    state["base_file_path"] = str(self.repeatability_base_path)
            methods = (
                self._file_integrity,
                self._textual_header,
                self._binary_header,
                self._trace_header,
                self._geometry,
                self._coordinate,
                self._navigation,
                self._trace_integrity,
                self._dead_zero,
                self._noise,
                self._clipping_spike,
                self._dc_amplitude,
                self._rms_energy,
                self._frequency,
                self._statics_timing,
                self._residual_statics,
                self._velocity,
                self._nmo,
                self._stack,
                self._migration,
                self._attribute,
                self._repeatability,
                self._summary,
            )

            for order, ((stage_key, stage_name), method) in enumerate(zip(STAGES, methods)):
                self._stage_index = order
                if self._cancelled():
                    raise InterruptedError("QC run cancelled")
                self.repository.start_stage(self.run_uuid, stage_key, stage_name, order)
                self.callbacks.qc_stage_started(self.run_uuid, stage_key, stage_name, order)
                stage_started = time.perf_counter()
                self._report_progress(0.0, f"Starting {stage_name}")
                outcome = method(state)
                outcome.key = stage_key
                outcome.name = stage_name
                outcome.duration_ms = int((time.perf_counter() - stage_started) * 1000)
                self.repository.complete_stage(self.run_uuid, outcome)
                self._outcomes.append(outcome)
                self.callbacks.qc_stage_completed(self.run_uuid, outcome.to_dict())
                self._report_progress(1.0, f"Completed {stage_name}")

                if self.approval_gate.enabled and order < len(STAGES) - 1:
                    self.callbacks.qc_stage_approval_required(self.run_uuid, stage_key, stage_name)
                    self.approval_gate.wait(stage_key, self._cancelled)

            completed = datetime.now(timezone.utc)
            summary = self._build_run_summary(state, started, completed)
            self.repository.complete_run(summary)
            self.callbacks.qc_run_ready(self.run_uuid, summary.to_dict())
            return summary.to_dict()
        except InterruptedError:
            self.repository.cancel_run(self.run_uuid)
            self.callbacks.qc_run_cancelled_from_worker(self.run_uuid)
            return {"run_uuid": self.run_uuid, "cancelled": True}
        except Exception as exc:
            self.repository.fail_run(self.run_uuid, str(exc))
            raise

    def _threshold(self, key: str) -> float:
        return float(self.profile.thresholds[key])

    @staticmethod
    def _pct(count: int, total: int) -> float:
        return 100.0 * float(count) / max(1, int(total))

    @staticmethod
    def _finite(values: np.ndarray) -> np.ndarray:
        values = np.asarray(values, dtype=np.float64)
        return values[np.isfinite(values)]

    @staticmethod
    def _robust_center_scale(values: np.ndarray) -> Tuple[float, float]:
        finite = SegyQcJob._finite(values)
        if finite.size == 0:
            return 0.0, 0.0
        median = float(np.median(finite))
        mad = float(np.median(np.abs(finite - median)))
        robust_sigma = 1.4826 * mad
        return median, robust_sigma

    @staticmethod
    def _status_and_score(findings: Sequence[SegyFinding]) -> Tuple[str, float]:
        weights = {"critical": 30.0, "error": 18.0, "warning": 6.0, "info": 1.0}
        score = 100.0 - sum(weights.get(item.severity, 3.0) for item in findings)
        if any(item.severity in {"critical", "error"} for item in findings):
            status = "fail"
        elif any(item.severity == "warning" for item in findings):
            status = "warn"
        else:
            status = "pass"
        return status, max(0.0, round(score, 2))

    def _outcome(
        self,
        metrics: Dict[str, Any],
        findings: Optional[List[SegyFinding]] = None,
        message: str = "",
    ) -> SegyStageOutcome:
        findings = findings or []
        status, score = self._status_and_score(findings)
        return SegyStageOutcome("", "", status, score, metrics, findings, message)

    def _stage_result_outcome(self, result: QCStageResult) -> SegyStageOutcome:
        try:
            metrics = json.loads(result.summary_json or "{}")
            if not isinstance(metrics, dict):
                metrics = {"result": metrics}
        except (TypeError, json.JSONDecodeError):
            metrics = {"summary": str(result.summary_json)}

        findings: List[SegyFinding] = []
        for item in result.findings:
            try:
                metadata = json.loads(item.metadata_json or "{}")
                if not isinstance(metadata, dict):
                    metadata = {}
            except (TypeError, json.JSONDecodeError):
                metadata = {}
            context_data = metadata.get("context")
            if not isinstance(context_data, dict):
                context_data = {}
            trace_index = None
            affected = context_data.get("affected_trace_indices")
            if isinstance(affected, list) and affected:
                try:
                    trace_index = int(affected[0])
                except (TypeError, ValueError):
                    trace_index = None
            findings.append(
                SegyFinding(
                    code=str(item.rule_id),
                    severity=str(item.severity.value),
                    category=str(metadata.get("category") or "processing"),
                    title=str(metadata.get("title") or item.rule_id.replace("_", " ").title()),
                    description=str(item.message),
                    metric_name=metadata.get("metric_name"),
                    observed_value=metadata.get("observed_value"),
                    expected_min=metadata.get("expected_min"),
                    expected_max=metadata.get("expected_max"),
                    unit=metadata.get("unit"),
                    trace_index=trace_index,
                    suggested_action=item.suggested_action,
                    context={
                        **context_data,
                        **({"location_ref": item.location_ref} if item.location_ref else {}),
                    },
                )
            )
        message = metrics.get("message") if isinstance(metrics.get("message"), str) else ""
        return self._outcome(metrics, findings, message)

    def _trace_context(self, indices: np.ndarray) -> Dict[str, Any]:
        maximum = int(self._threshold("max_context_trace_indices"))
        values = [int(value) + 1 for value in np.asarray(indices, dtype=np.int64)[:maximum]]
        return {
            "affected_trace_indices": values,
            "affected_trace_count": int(np.asarray(indices).size),
            "truncated_trace_list": int(np.asarray(indices).size) > maximum,
        }

    def _rate_finding(
        self,
        code: str,
        category: str,
        title: str,
        description: str,
        count: int,
        total: int,
        maximum_pct: float,
        indices: Optional[np.ndarray] = None,
        suggested_action: str = "Review the affected traces and confirm whether re-acquisition or reprocessing is required.",
    ) -> Optional[SegyFinding]:
        if count <= 0:
            return None
        observed = self._pct(count, total)
        severity = "error" if observed > maximum_pct else "warning"
        context = self._trace_context(indices) if indices is not None else {"affected_count": count}
        first_trace = int(indices[0]) + 1 if indices is not None and indices.size else None
        return SegyFinding(
            code=code,
            severity=severity,
            category=category,
            title=title,
            description=f"{description} Affected: {count:,} of {total:,} traces ({observed:.3f}%).",
            metric_name=f"{code}_pct",
            observed_value=observed,
            expected_max=maximum_pct,
            unit="%",
            trace_index=first_trace,
            suggested_action=suggested_action,
            context=context,
        )

    def _file_integrity(self, state: Dict[str, Any]) -> SegyStageOutcome:
        reader: SegyReader = state["reader"]
        findings: List[SegyFinding] = []
        suffix = reader.file_path.suffix.lower()
        if suffix not in {".sgy", ".segy"}:
            findings.append(
                SegyFinding(
                    "FILE_EXTENSION",
                    "warning",
                    "integrity",
                    "Unexpected file extension",
                    f"The selected file uses extension '{suffix or '(none)'}' rather than .sgy or .segy.",
                    suggested_action="Confirm that the file is a SEG-Y file and rename it only after verification.",
                )
            )
        if reader.file_size <= reader.trace_data_start:
            findings.append(
                SegyFinding(
                    "NO_TRACE_PAYLOAD",
                    "critical",
                    "integrity",
                    "No trace payload",
                    "The file contains headers but no trace payload.",
                    suggested_action="Obtain a complete SEG-Y export from the source system.",
                )
            )
        if reader.extended_header_count_unknown:
            findings.append(
                SegyFinding(
                    "UNKNOWN_EXTENDED_HEADERS",
                    "warning",
                    "integrity",
                    "Unknown extended textual-header count",
                    "The binary header uses -1 for the extended textual-header count; automatic trace start may require manual confirmation.",
                    suggested_action="Confirm the trace-data start and extended textual-header termination marker.",
                )
            )
        metrics = reader.file_info()
        metrics["readable"] = True
        return self._outcome(metrics, findings, f"Validated {reader.file_size:,} bytes")

    def _textual_header(self, state: Dict[str, Any]) -> SegyStageOutcome:
        reader: SegyReader = state["reader"]
        lines = reader.text_header.lines
        blank_count = sum(not line.strip() for line in lines)
        blank_pct = self._pct(blank_count, len(lines))
        populated = " ".join(line.upper() for line in lines if line.strip())
        findings: List[SegyFinding] = []
        if blank_pct > self._threshold("blank_text_header_max_pct"):
            findings.append(
                SegyFinding(
                    "TEXT_HEADER_INCOMPLETE",
                    "warning",
                    "header",
                    "Textual header is sparsely populated",
                    f"{blank_count} of 40 textual-header lines are blank ({blank_pct:.1f}%).",
                    "blank_line_pct",
                    blank_pct,
                    expected_max=self._threshold("blank_text_header_max_pct"),
                    unit="%",
                    suggested_action="Populate client, survey, acquisition, processing and coordinate-reference metadata.",
                )
            )
        if not any(term in populated for term in ("SEG-Y", "SEGY", "CLIENT", "LINE", "SURVEY")):
            findings.append(
                SegyFinding(
                    "TEXT_HEADER_METADATA",
                    "info",
                    "header",
                    "Common survey metadata not detected",
                    "No common SEG-Y, client, survey or line labels were detected in the textual header.",
                    suggested_action="Review the textual header manually and confirm that survey metadata is documented.",
                )
            )
        metrics = {
            "encoding": reader.text_header.encoding,
            "line_count": len(lines),
            "blank_line_count": blank_count,
            "blank_line_pct": round(blank_pct, 3),
            "extended_text_header_count": len(reader.extended_text_headers),
            "text": reader.text_header.text,
        }
        return self._outcome(metrics, findings, f"Decoded textual header as {reader.text_header.encoding}")

    def _binary_header(self, state: Dict[str, Any]) -> SegyStageOutcome:
        reader: SegyReader = state["reader"]
        header = reader.binary_header
        findings: List[SegyFinding] = []
        dt = header.sample_interval_us
        ns = header.samples_per_trace
        if not self._threshold("sample_interval_min_us") <= dt <= self._threshold("sample_interval_max_us"):
            findings.append(
                SegyFinding(
                    "BINARY_SAMPLE_INTERVAL",
                    "error",
                    "header",
                    "Invalid binary-header sample interval",
                    f"Binary-header sample interval is {dt} µs.",
                    "sample_interval_us",
                    float(dt),
                    self._threshold("sample_interval_min_us"),
                    self._threshold("sample_interval_max_us"),
                    "µs",
                    suggested_action="Correct binary-header bytes 3217-3218 / extended bytes 3273-3280, or regenerate the SEG-Y deliverable.",
                )
            )
        if not self._threshold("samples_per_trace_min") <= ns <= self._threshold("samples_per_trace_max"):
            findings.append(
                SegyFinding(
                    "BINARY_SAMPLE_COUNT",
                    "error",
                    "header",
                    "Invalid binary-header sample count",
                    f"Binary-header samples per trace is {ns}.",
                    "samples_per_trace",
                    float(ns),
                    self._threshold("samples_per_trace_min"),
                    self._threshold("samples_per_trace_max"),
                    "samples",
                    suggested_action="Correct binary-header bytes 3221-3222 / extended bytes 3269-3272, or regenerate the SEG-Y deliverable.",
                )
            )
        if header.segy_revision_major not in {0, 1, 2}:
            findings.append(
                SegyFinding(
                    "SEGY_REVISION",
                    "warning",
                    "header",
                    "Unrecognized SEG-Y revision",
                    f"Binary header reports SEG-Y revision {header.revision}.",
                    suggested_action="Confirm the SEG-Y revision and byte mapping with the data provider.",
                )
            )
        if header.measurement_system not in {0, 1, 2}:
            findings.append(
                SegyFinding(
                    "MEASUREMENT_SYSTEM",
                    "warning",
                    "header",
                    "Invalid measurement-system code",
                    f"Measurement-system code is {header.measurement_system}.",
                    suggested_action="Set binary-header bytes 3255-3256 to 1 for metres or 2 for feet.",
                )
            )
        if header.fixed_length_trace_flag not in {0, 1}:
            findings.append(
                SegyFinding(
                    "FIXED_LENGTH_TRACE_FLAG",
                    "warning",
                    "header",
                    "Invalid fixed-length trace flag",
                    f"Binary-header fixed-length trace flag is {header.fixed_length_trace_flag}.",
                    suggested_action="Use 0 for variable-length traces or 1 when all traces have the same sample count and interval.",
                )
            )
        if header.segy_revision_major >= 2 and not header.byte_order_detection.startswith("rev2-sentinel-"):
            findings.append(
                SegyFinding(
                    "REV2_ENDIAN_SENTINEL",
                    "warning",
                    "header",
                    "SEG-Y Rev 2 byte-order sentinel is not authoritative",
                    "The file declares SEG-Y Rev 2.x but byte order had to be inferred rather than confirmed by the 0x01020304 endian sentinel.",
                    suggested_action="Populate binary-header bytes 3297-3300 with the Rev 2 endian sentinel during export.",
                )
            )
        computed_trace_start = reader.BASE_TRACE_OFFSET + reader.extended_header_count * reader.TEXT_HEADER_BYTES
        if header.first_trace_offset > 0 and header.first_trace_offset < computed_trace_start:
            findings.append(
                SegyFinding(
                    "FIRST_TRACE_OFFSET",
                    "error",
                    "header",
                    "Invalid first-trace byte offset",
                    f"Declared first trace offset {header.first_trace_offset:,} precedes the end of textual/extended headers at byte {computed_trace_start:,}.",
                    suggested_action="Correct the Rev 2 first-trace offset field or re-export the SEG-Y file.",
                )
            )
        if header.maximum_additional_trace_headers > 0 and header.segy_revision_major < 2:
            findings.append(
                SegyFinding(
                    "TRACE_EXTENSION_REVISION",
                    "warning",
                    "header",
                    "Trace-header extensions declared on pre-Rev-2 file",
                    f"Binary header declares {header.maximum_additional_trace_headers} additional trace header(s) while revision is {header.revision}.",
                    suggested_action="Confirm the intended SEG-Y revision and extension layout with the exporter.",
                )
            )
        metrics = reader.file_info()["binary_header"]
        metrics.update({
            "trace_data_start": reader.trace_data_start,
            "trace_data_start_source": reader.trace_data_start_source,
            "byte_order_detection": header.byte_order_detection,
        })
        return self._outcome(metrics, findings, f"SEG-Y {header.revision}; {reader.sample_format_name}")

    def _trace_header(self, state: Dict[str, Any]) -> SegyStageOutcome:
        reader: SegyReader = state["reader"]
        index = reader.scan_trace_headers(
            progress_callback=lambda fraction, message: self._report_progress(fraction, message),
            cancel_check=self._cancelled,
        )
        state["index"] = index
        n = index.trace_count
        findings: List[SegyFinding] = []
        if n == 0:
            findings.append(
                SegyFinding(
                    "NO_TRACES",
                    "critical",
                    "trace_header",
                    "No readable traces",
                    "No complete SEG-Y traces were found after the textual and binary headers.",
                    suggested_action="Check extended-header count, trace-data start, sample format and file completeness.",
                )
            )
            return self._outcome({"trace_count": 0}, findings)

        if index.truncated:
            findings.append(
                SegyFinding(
                    "TRUNCATED_TRACE",
                    "critical",
                    "integrity",
                    "Truncated final trace",
                    "The final trace header or sample payload extends beyond the file size.",
                    suggested_action="Recover or re-export the complete SEG-Y file.",
                )
            )
        elif index.trailing_bytes:
            expected_trailer_bytes = int(reader.binary_header.data_trailer_stanza_count) * reader.TEXT_HEADER_BYTES
            if expected_trailer_bytes <= 0 or index.trailing_bytes != expected_trailer_bytes:
                findings.append(
                    SegyFinding(
                        "TRAILING_BYTES",
                        "warning",
                        "integrity",
                        "Unparsed trailing bytes",
                        f"{index.trailing_bytes} bytes remain after the last complete trace; declared trailer size is {expected_trailer_bytes} bytes.",
                        "trailing_bytes",
                        float(index.trailing_bytes),
                        expected_max=float(expected_trailer_bytes),
                        unit="bytes",
                        suggested_action="Confirm Rev 2 data-trailer stanza count or remove unintended appended data.",
                    )
                )

        ns_bad = np.flatnonzero(index.sample_counts != reader.binary_header.samples_per_trace)
        item = self._rate_finding(
            "TRACE_NS_MISMATCH",
            "trace_header",
            "Trace sample-count mismatch",
            "Trace-header sample counts differ from the binary-header value.",
            int(ns_bad.size),
            n,
            self._threshold("trace_header_ns_mismatch_max_pct"),
            ns_bad,
            "Confirm variable-length trace usage or correct trace-header bytes 115-116.",
        )
        if item:
            findings.append(item)
        dt_bad = np.flatnonzero(index.sample_intervals_us != reader.binary_header.sample_interval_us)
        item = self._rate_finding(
            "TRACE_DT_MISMATCH",
            "trace_header",
            "Trace sample-interval mismatch",
            "Trace-header sample intervals differ from the binary-header value.",
            int(dt_bad.size),
            n,
            self._threshold("trace_header_dt_mismatch_max_pct"),
            dt_bad,
            "Correct trace-header bytes 117-118 or document intentional mixed sampling.",
        )
        if item:
            findings.append(item)

        sequence = index.trace_sequence_file
        sequence_nonzero = sequence[sequence != 0]
        duplicate_count = int(sequence_nonzero.size - np.unique(sequence_nonzero).size)
        duplicate_indices = np.flatnonzero(
            np.isin(sequence, np.unique(sequence_nonzero, return_counts=True)[0][
                np.unique(sequence_nonzero, return_counts=True)[1] > 1
            ])
        ) if sequence_nonzero.size else np.array([], dtype=np.int64)
        item = self._rate_finding(
            "DUPLICATE_TRACE_SEQUENCE",
            "trace_header",
            "Duplicate trace sequence numbers",
            "Trace sequence numbers within the file are duplicated.",
            duplicate_count,
            n,
            self._threshold("duplicate_trace_sequence_max_pct"),
            duplicate_indices,
            "Renumber traces sequentially or document the supplier-specific trace numbering scheme.",
        )
        if item:
            findings.append(item)

        invalid_id = np.flatnonzero((index.trace_identification < 0) | (index.trace_identification > 9))
        item = self._rate_finding(
            "INVALID_TRACE_ID",
            "trace_header",
            "Invalid trace identification code",
            "Trace identification codes fall outside the commonly defined SEG-Y range 0-9.",
            int(invalid_id.size),
            n,
            self._threshold("invalid_trace_id_max_pct"),
            invalid_id,
            "Correct trace-header bytes 29-30 according to the SEG-Y trace identification table.",
        )
        if item:
            findings.append(item)

        declared_trace_count = int(reader.binary_header.declared_trace_count)
        if declared_trace_count > 0 and declared_trace_count != n:
            findings.append(
                SegyFinding(
                    "DECLARED_TRACE_COUNT_MISMATCH",
                    "error",
                    "trace_header",
                    "Declared trace count does not match indexed traces",
                    f"Rev 2 binary header declares {declared_trace_count:,} traces but {n:,} complete traces were indexed.",
                    suggested_action="Correct binary-header bytes 3513-3520 or regenerate the file after verifying completeness.",
                )
            )
        fixed_length_violation_count = 0
        if reader.binary_header.fixed_length_trace_flag == 1:
            fixed_length_violation_count = int(
                np.count_nonzero(index.sample_counts != index.sample_counts[0])
                + np.count_nonzero(index.sample_intervals_us != index.sample_intervals_us[0])
            )
            if fixed_length_violation_count:
                findings.append(
                    SegyFinding(
                        "FIXED_LENGTH_CONTRADICTION",
                        "error",
                        "trace_header",
                        "Fixed-length flag contradicts trace timing",
                        "The binary header declares fixed-length traces, but trace sample counts and/or sample intervals vary.",
                        suggested_action="Correct the fixed-length flag or normalize trace timing before delivery.",
                    )
                )
        extension_count_max = int(index.trace_extension_counts.max()) if index.trace_extension_counts.size else 0
        declared_extension_max = int(reader.binary_header.maximum_additional_trace_headers)
        if extension_count_max > declared_extension_max:
            findings.append(
                SegyFinding(
                    "TRACE_EXTENSION_COUNT",
                    "error",
                    "trace_header",
                    "Per-trace extension count exceeds binary-header maximum",
                    f"Maximum per-trace extension count is {extension_count_max}; binary header declares {declared_extension_max}.",
                    suggested_action="Correct Rev 2 binary/trace extension counts so random trace access is deterministic.",
                )
            )
        if declared_extension_max > 0 and not np.all(index.trace_extension_1_present):
            missing = int(np.count_nonzero(~index.trace_extension_1_present))
            findings.append(
                SegyFinding(
                    "SEG00001_EXTENSION_SIGNATURE",
                    "warning",
                    "trace_header",
                    "Standard Trace Header Extension 1 signature not found on all traces",
                    f"{missing:,} of {n:,} traces do not expose the standardized SEG00001 extension signature.",
                    suggested_action="Verify whether proprietary trace extensions are in use and document their byte layout.",
                )
            )

        metrics = {
            "trace_count": n,
            "declared_trace_count": declared_trace_count,
            "trace_data_start": reader.trace_data_start,
            "trace_header_size_min": int(index.header_sizes.min()),
            "trace_header_size_max": int(index.header_sizes.max()),
            "trace_extension_count_max": extension_count_max,
            "standard_extension_1_count": int(np.count_nonzero(index.trace_extension_1_present)),
            "fixed_length_violation_count": fixed_length_violation_count,
            "sample_count_min": int(index.sample_counts.min()),
            "sample_count_max": int(index.sample_counts.max()),
            "sample_interval_min_us": float(index.sample_intervals_us.min()),
            "sample_interval_max_us": float(index.sample_intervals_us.max()),
            "ns_mismatch_count": int(ns_bad.size),
            "dt_mismatch_count": int(dt_bad.size),
            "duplicate_sequence_count": duplicate_count,
            "invalid_trace_id_count": int(invalid_id.size),
            "trailing_bytes": index.trailing_bytes,
            "truncated": index.truncated,
        }
        return self._outcome(metrics, findings, f"Indexed {n:,} traces")

    def _geometry(self, state: Dict[str, Any]) -> SegyStageOutcome:
        index: SegyTraceIndex = state["index"]
        n = index.trace_count
        findings: List[SegyFinding] = []
        cdp = index.cdp[index.cdp != 0]
        if cdp.size:
            unique_cdp, fold = np.unique(cdp, return_counts=True)
            mean_fold = float(np.mean(fold))
            fold_cv = float(np.std(fold) / mean_fold) if mean_fold else 0.0
            if fold_cv > self._threshold("fold_cv_max"):
                findings.append(
                    SegyFinding(
                        "FOLD_VARIATION",
                        "warning",
                        "geometry",
                        "Large fold variation",
                        f"CDP fold coefficient of variation is {fold_cv:.3f}.",
                        "fold_cv",
                        fold_cv,
                        expected_max=self._threshold("fold_cv_max"),
                        suggested_action="Review missing traces, geometry merges and CDP assignment.",
                    )
                )
            metrics = {
                "unique_cdp_count": int(unique_cdp.size),
                "fold_min": int(fold.min()),
                "fold_max": int(fold.max()),
                "fold_mean": round(mean_fold, 3),
                "fold_median": float(np.median(fold)),
                "fold_cv": round(fold_cv, 5),
                "offset_min": float(index.offsets.min()) if n else 0.0,
                "offset_max": float(index.offsets.max()) if n else 0.0,
                "offset_median": float(np.median(index.offsets)) if n else 0.0,
            }
        else:
            findings.append(
                SegyFinding(
                    "MISSING_CDP",
                    "warning",
                    "geometry",
                    "CDP numbers are not populated",
                    "All CDP/ensemble numbers are zero, so fold distribution cannot be evaluated.",
                    suggested_action="Populate trace-header bytes 21-24 for processed CDP data or document the sorting convention.",
                )
            )
            metrics = {
                "unique_cdp_count": 0,
                "fold_min": 0,
                "fold_max": 0,
                "fold_mean": 0.0,
                "fold_median": 0.0,
                "fold_cv": 0.0,
                "offset_min": float(index.offsets.min()) if n else 0.0,
                "offset_max": float(index.offsets.max()) if n else 0.0,
                "offset_median": float(np.median(index.offsets)) if n else 0.0,
            }
        duplicate_keys = np.column_stack((index.field_record, index.trace_number)) if n else np.empty((0, 2))
        duplicate_pair_count = n - np.unique(duplicate_keys, axis=0).shape[0] if n else 0
        if duplicate_pair_count:
            findings.append(
                SegyFinding(
                    "DUPLICATE_GEOMETRY_KEYS",
                    "warning",
                    "geometry",
                    "Duplicate field-record/trace-number pairs",
                    f"{duplicate_pair_count:,} duplicate field-record and trace-number pairs were detected.",
                    "duplicate_geometry_key_count",
                    float(duplicate_pair_count),
                    expected_max=0.0,
                    unit="traces",
                    suggested_action="Review merge keys and trace renumbering before loading the dataset into interpretation software.",
                )
            )
        metrics["duplicate_geometry_key_count"] = int(duplicate_pair_count)

        valid_3d = (index.inline_3d != 0) & (index.crossline_3d != 0)
        metrics["trace_3d_geometry_count"] = int(np.count_nonzero(valid_3d))
        if np.any(valid_3d):
            geometry_pairs = np.column_stack((index.inline_3d[valid_3d], index.crossline_3d[valid_3d]))
            unique_pairs, pair_counts = np.unique(geometry_pairs, axis=0, return_counts=True)
            duplicate_bin_count = int(np.sum(np.maximum(pair_counts - 1, 0)))
            unique_inline = np.unique(index.inline_3d[valid_3d])
            unique_crossline = np.unique(index.crossline_3d[valid_3d])
            rectangular_capacity = int(unique_inline.size * unique_crossline.size)
            occupancy = float(unique_pairs.shape[0] / rectangular_capacity) if rectangular_capacity else 0.0
            metrics.update(
                {
                    "unique_3d_bin_count": int(unique_pairs.shape[0]),
                    "duplicate_3d_bin_trace_count": duplicate_bin_count,
                    "inline_count": int(unique_inline.size),
                    "crossline_count": int(unique_crossline.size),
                    "rectangular_grid_occupancy": occupancy,
                }
            )
            # Duplicate IL/XL keys are expected in prestack gathers but suspicious
            # in post-stack volumes. Use offset population to distinguish the cases
            # instead of applying a universal false-positive rule.
            zero_offset_fraction = float(np.mean(index.offsets[valid_3d] == 0))
            metrics["zero_offset_fraction_3d"] = zero_offset_fraction
            if duplicate_bin_count and zero_offset_fraction >= 0.95:
                findings.append(
                    SegyFinding(
                        "DUPLICATE_POSTSTACK_3D_BINS",
                        "warning",
                        "geometry",
                        "Duplicate inline/crossline bins in post-stack-like data",
                        f"{duplicate_bin_count:,} additional traces share an existing inline/crossline key while "
                        f"{zero_offset_fraction * 100.0:.1f}% of 3D traces have zero offset.",
                        "duplicate_3d_bin_trace_count",
                        float(duplicate_bin_count),
                        expected_max=0.0,
                        unit="traces",
                        suggested_action=(
                            "Resolve duplicate IL/XL keys before volume realization; do not silently average or overwrite "
                            "traces unless the processing rule is explicitly documented."
                        ),
                    )
                )
        else:
            metrics.update(
                {
                    "unique_3d_bin_count": 0,
                    "duplicate_3d_bin_trace_count": 0,
                    "inline_count": 0,
                    "crossline_count": 0,
                    "rectangular_grid_occupancy": 0.0,
                    "zero_offset_fraction_3d": 0.0,
                }
            )
        return self._outcome(metrics, findings)

    def _coordinate(self, state: Dict[str, Any]) -> SegyStageOutcome:
        index: SegyTraceIndex = state["index"]
        n = index.trace_count
        findings: List[SegyFinding] = []
        missing = np.flatnonzero(
            ((index.source_x == 0) & (index.source_y == 0))
            | ((index.receiver_x == 0) & (index.receiver_y == 0))
            | ~np.isfinite(index.source_x)
            | ~np.isfinite(index.source_y)
            | ~np.isfinite(index.receiver_x)
            | ~np.isfinite(index.receiver_y)
        )
        item = self._rate_finding(
            "MISSING_COORDINATES",
            "coordinate",
            "Missing source or receiver coordinates",
            "One or more source/receiver coordinate pairs are zero or non-finite.",
            int(missing.size),
            n,
            self._threshold("missing_coordinate_max_pct"),
            missing,
            "Populate and verify source/receiver coordinates and coordinate scalar fields.",
        )
        if item:
            findings.append(item)

        valid = np.flatnonzero(~np.isin(np.arange(n), missing))
        duplicate_count = 0
        if valid.size:
            receiver_pairs = np.column_stack((index.receiver_x[valid], index.receiver_y[valid]))
            duplicate_count = int(valid.size - np.unique(receiver_pairs, axis=0).shape[0])
            if self._pct(duplicate_count, valid.size) > self._threshold("duplicate_coordinate_max_pct"):
                findings.append(
                    SegyFinding(
                        "DUPLICATE_RECEIVER_COORDINATES",
                        "warning",
                        "coordinate",
                        "High duplicate receiver-coordinate rate",
                        f"{duplicate_count:,} receiver coordinate pairs are duplicated ({self._pct(duplicate_count, valid.size):.3f}%).",
                        "duplicate_receiver_coordinate_pct",
                        self._pct(duplicate_count, valid.size),
                        expected_max=self._threshold("duplicate_coordinate_max_pct"),
                        unit="%",
                        suggested_action="Confirm whether repeated locations are expected for stacked/processed data.",
                    )
                )

        coord_units = {int(value): int(count) for value, count in zip(*np.unique(index.coordinate_units, return_counts=True))}
        invalid_units = int(np.sum(~np.isin(index.coordinate_units, [0, 1, 2, 3, 4])))
        if invalid_units:
            findings.append(
                SegyFinding(
                    "INVALID_COORDINATE_UNITS",
                    "warning",
                    "coordinate",
                    "Invalid coordinate-unit code",
                    f"{invalid_units:,} traces contain coordinate-unit codes outside 0-4.",
                    suggested_action="Correct trace-header bytes 89-90 and document the coordinate reference system.",
                )
            )

        metrics = {
            "missing_coordinate_count": int(missing.size),
            "missing_coordinate_pct": round(self._pct(missing.size, n), 5),
            "duplicate_receiver_coordinate_count": duplicate_count,
            "coordinate_unit_counts": coord_units,
            "source_x_min": float(np.nanmin(index.source_x)) if n else 0.0,
            "source_x_max": float(np.nanmax(index.source_x)) if n else 0.0,
            "source_y_min": float(np.nanmin(index.source_y)) if n else 0.0,
            "source_y_max": float(np.nanmax(index.source_y)) if n else 0.0,
            "receiver_x_min": float(np.nanmin(index.receiver_x)) if n else 0.0,
            "receiver_x_max": float(np.nanmax(index.receiver_x)) if n else 0.0,
            "receiver_y_min": float(np.nanmin(index.receiver_y)) if n else 0.0,
            "receiver_y_max": float(np.nanmax(index.receiver_y)) if n else 0.0,
        }
        return self._outcome(metrics, findings)

    def _navigation(self, state: Dict[str, Any]) -> SegyStageOutcome:
        index: SegyTraceIndex = state["index"]
        n = index.trace_count
        findings: List[SegyFinding] = []
        if n < 2:
            return self._outcome({"step_count": 0}, findings)

        dx = np.diff(index.receiver_x)
        dy = np.diff(index.receiver_y)
        steps = np.hypot(dx, dy)
        finite_steps = steps[np.isfinite(steps)]
        center, sigma = self._robust_center_scale(finite_steps)
        threshold = center + self._threshold("navigation_step_mad_factor") * max(sigma, np.finfo(float).eps)
        jump_indices = np.flatnonzero(steps > threshold) + 1 if finite_steps.size else np.array([], dtype=np.int64)
        if jump_indices.size:
            findings.append(
                SegyFinding(
                    "NAVIGATION_JUMPS",
                    "warning",
                    "navigation",
                    "Abrupt receiver-coordinate jumps",
                    f"{jump_indices.size:,} receiver steps exceed the robust navigation threshold of {threshold:.3f} coordinate units.",
                    "navigation_jump_count",
                    float(jump_indices.size),
                    expected_max=0.0,
                    unit="steps",
                    trace_index=int(jump_indices[0]) + 1,
                    suggested_action="Review coordinate scalars, line breaks, sorting order and navigation merges.",
                    context=self._trace_context(jump_indices),
                )
            )
        duplicate_steps = np.flatnonzero(steps == 0) + 1
        item = self._rate_finding(
            "DUPLICATE_NAVIGATION_POINTS",
            "navigation",
            "Repeated consecutive receiver positions",
            "Consecutive traces use identical receiver coordinates.",
            int(duplicate_steps.size),
            max(1, n - 1),
            self._threshold("navigation_duplicate_max_pct"),
            duplicate_steps,
            "Confirm whether repeated receiver positions are expected for the trace sorting and processing stage.",
        )
        if item:
            findings.append(item)

        valid_time = (
            ((index.year == 0) | ((index.year >= 1900) & (index.year <= 2200)))
            & ((index.day_of_year == 0) | ((index.day_of_year >= 1) & (index.day_of_year <= 366)))
            & (index.hour <= 23)
            & (index.minute <= 59)
            & (index.second <= 60)
        )
        invalid_time = np.flatnonzero(~valid_time)
        if invalid_time.size:
            findings.append(
                SegyFinding(
                    "INVALID_TRACE_TIME",
                    "warning",
                    "navigation",
                    "Invalid trace date/time fields",
                    f"{invalid_time.size:,} traces contain invalid year/day/time values.",
                    trace_index=int(invalid_time[0]) + 1,
                    suggested_action="Correct trace-header bytes 157-166 or clear unused values to zero.",
                    context=self._trace_context(invalid_time),
                )
            )
        metrics = {
            "step_count": int(steps.size),
            "step_min": float(np.min(finite_steps)) if finite_steps.size else 0.0,
            "step_max": float(np.max(finite_steps)) if finite_steps.size else 0.0,
            "step_median": center,
            "step_robust_sigma": sigma,
            "jump_threshold": threshold,
            "jump_count": int(jump_indices.size),
            "duplicate_step_count": int(duplicate_steps.size),
            "invalid_time_count": int(invalid_time.size),
        }
        return self._outcome(metrics, findings)

    def _trace_integrity(self, state: Dict[str, Any]) -> SegyStageOutcome:
        reader: SegyReader = state["reader"]
        index: SegyTraceIndex = state["index"]
        n = index.trace_count
        rms = np.full(n, np.nan, dtype=np.float64)
        mean = np.full(n, np.nan, dtype=np.float64)
        std = np.full(n, np.nan, dtype=np.float64)
        energy = np.full(n, np.nan, dtype=np.float64)
        max_abs = np.full(n, np.nan, dtype=np.float64)
        zero_fraction = np.full(n, np.nan, dtype=np.float64)
        plateau_fraction = np.full(n, np.nan, dtype=np.float64)
        spike_score = np.full(n, np.nan, dtype=np.float64)
        noise_ratio = np.full(n, np.nan, dtype=np.float64)
        dc_bias_ratio = np.full(n, np.nan, dtype=np.float64)
        nonfinite_count = np.zeros(n, dtype=np.int32)

        frequency_limit = min(n, int(self._threshold("max_frequency_traces")))
        frequency_indices = set(
            int(value) for value in np.linspace(0, max(0, n - 1), frequency_limit, dtype=int)
        ) if frequency_limit else set()
        dominant_frequency: Dict[int, float] = {}
        bandwidth: Dict[int, float] = {}
        spectral_centroid: Dict[int, float] = {}
        spectral_entropy: Dict[int, float] = {}

        def trace_progress(fraction: float, message: str) -> None:
            self._report_progress(fraction, message)

        for trace_idx, data in reader.iter_traces(
            index=index,
            progress_callback=trace_progress,
            cancel_check=self._cancelled,
        ):
            values = np.asarray(data, dtype=np.float64)
            finite_mask = np.isfinite(values)
            nonfinite_count[trace_idx] = int(values.size - np.count_nonzero(finite_mask))
            values = values[finite_mask]
            if values.size == 0:
                continue
            abs_values = np.abs(values)
            trace_mean = float(np.mean(values))
            trace_rms = float(np.sqrt(np.mean(np.square(values))))
            trace_std = float(np.std(values))
            trace_max = float(np.max(abs_values))
            trace_energy = float(np.mean(np.square(values)))
            eps = max(np.finfo(float).eps, trace_rms * 1e-12)
            trace_min_value = float(np.min(values))
            trace_max_value = float(np.max(values))
            atol = max(eps, trace_max * 1e-6)
            plateau = max(
                int(np.count_nonzero(np.isclose(values, trace_min_value, rtol=0.0, atol=atol))),
                int(np.count_nonzero(np.isclose(values, trace_max_value, rtol=0.0, atol=atol))),
            )
            median_abs = float(np.median(abs_values))
            diff_rms = float(np.sqrt(np.mean(np.square(np.diff(values))))) if values.size > 1 else 0.0

            rms[trace_idx] = trace_rms
            mean[trace_idx] = trace_mean
            std[trace_idx] = trace_std
            energy[trace_idx] = trace_energy
            max_abs[trace_idx] = trace_max
            zero_fraction[trace_idx] = float(np.count_nonzero(values == 0.0) / values.size)
            plateau_fraction[trace_idx] = float(plateau / values.size)
            spike_score[trace_idx] = trace_max / max(median_abs, eps)
            noise_ratio[trace_idx] = diff_rms / max(trace_rms, eps)
            dc_bias_ratio[trace_idx] = abs(trace_mean) / max(trace_rms, eps)

            if trace_idx in frequency_indices and values.size >= 8 and index.sample_intervals_us[trace_idx] > 0:
                centred = values - trace_mean
                window = np.hanning(values.size)
                tapered = centred * window
                spectrum = np.abs(np.fft.rfft(tapered)) ** 2
                frequencies = np.fft.rfftfreq(
                    values.size, d=float(index.sample_intervals_us[trace_idx]) / 1_000_000.0
                )
                if spectrum.size > 1:
                    spectrum[0] = 0.0
                    total_power = float(np.sum(spectrum))
                    if total_power > 0:
                        peak_idx = int(np.argmax(spectrum))
                        peak_frequency = float(frequencies[peak_idx])
                        if 0 < peak_idx < spectrum.size - 1 and frequencies.size > 1:
                            left, centre_power, right = (
                                float(spectrum[peak_idx - 1]),
                                float(spectrum[peak_idx]),
                                float(spectrum[peak_idx + 1]),
                            )
                            denominator = left - 2.0 * centre_power + right
                            if abs(denominator) > np.finfo(float).eps:
                                delta = float(np.clip(0.5 * (left - right) / denominator, -0.5, 0.5))
                                peak_frequency += delta * float(frequencies[1] - frequencies[0])
                        dominant_frequency[trace_idx] = peak_frequency
                        cumulative = np.cumsum(spectrum) / total_power
                        low_idx = int(np.searchsorted(cumulative, 0.05))
                        high_idx = int(np.searchsorted(cumulative, 0.95))
                        high_idx = min(high_idx, frequencies.size - 1)
                        low_idx = min(low_idx, high_idx)
                        bandwidth[trace_idx] = float(frequencies[high_idx] - frequencies[low_idx])
                        spectral_centroid[trace_idx] = float(np.sum(frequencies * spectrum) / total_power)
                        probabilities = spectrum[spectrum > 0] / total_power
                        if probabilities.size > 1:
                            spectral_entropy[trace_idx] = float(
                                -np.sum(probabilities * np.log(probabilities)) / np.log(probabilities.size)
                            )
                        else:
                            spectral_entropy[trace_idx] = 0.0

        metrics = {
            "rms": rms,
            "mean": mean,
            "std": std,
            "energy": energy,
            "max_abs": max_abs,
            "zero_fraction": zero_fraction,
            "plateau_fraction": plateau_fraction,
            "spike_score": spike_score,
            "noise_ratio": noise_ratio,
            "dc_bias_ratio": dc_bias_ratio,
            "nonfinite_count": nonfinite_count,
            "dominant_frequency": dominant_frequency,
            "bandwidth": bandwidth,
            "spectral_centroid": spectral_centroid,
            "spectral_entropy": spectral_entropy,
            "frequency_trace_count": len(dominant_frequency),
        }
        state["trace_metrics"] = metrics
        nonfinite_traces = np.flatnonzero(nonfinite_count > 0)
        findings: List[SegyFinding] = []
        if nonfinite_traces.size:
            findings.append(
                SegyFinding(
                    "NONFINITE_SAMPLES",
                    "error",
                    "trace_integrity",
                    "Non-finite trace samples",
                    f"{nonfinite_traces.size:,} traces contain NaN or infinite sample values.",
                    trace_index=int(nonfinite_traces[0]) + 1,
                    suggested_action="Replace invalid samples from a trusted source or regenerate the SEG-Y export.",
                    context=self._trace_context(nonfinite_traces),
                )
            )
        summary_metrics = {
            "trace_count": n,
            "nonfinite_trace_count": int(nonfinite_traces.size),
            "nonfinite_sample_count": int(np.sum(nonfinite_count)),
            "rms_median": float(np.nanmedian(rms)) if n else 0.0,
            "rms_min": float(np.nanmin(rms)) if np.any(np.isfinite(rms)) else 0.0,
            "rms_max": float(np.nanmax(rms)) if np.any(np.isfinite(rms)) else 0.0,
            "frequency_trace_count": len(dominant_frequency),
        }
        return self._outcome(summary_metrics, findings, f"Analysed {n:,} complete traces")

    def _dead_zero(self, state: Dict[str, Any]) -> SegyStageOutcome:
        metrics = state["trace_metrics"]
        rms = metrics["rms"]
        zero_fraction = metrics["zero_fraction"]
        n = rms.size
        finite_rms = rms[np.isfinite(rms)]
        median_rms = float(np.median(finite_rms)) if finite_rms.size else 0.0
        zero_indices = np.flatnonzero((zero_fraction >= 0.999999) | (rms == 0.0))
        dead_threshold = median_rms * self._threshold("dead_rms_ratio")
        dead_indices = np.flatnonzero(
            np.isfinite(rms) & (rms > 0.0) & (rms <= dead_threshold) & ~np.isin(np.arange(n), zero_indices)
        )
        findings: List[SegyFinding] = []
        item = self._rate_finding(
            "ZERO_TRACES", "trace", "Zero traces", "Traces contain only zero-valued samples.",
            int(zero_indices.size), n, self._threshold("zero_trace_max_pct"), zero_indices,
            "Verify muted/dead channels and replace or remove zero traces according to delivery requirements.",
        )
        if item:
            findings.append(item)
        item = self._rate_finding(
            "DEAD_TRACES", "trace", "Dead or very-low-energy traces",
            f"Trace RMS is at or below {dead_threshold:.6g}, derived from the dataset median RMS.",
            int(dead_indices.size), n, self._threshold("dead_trace_max_pct"), dead_indices,
            "Review channel status, sensor coupling, gain and trace editing.",
        )
        if item:
            findings.append(item)
        return self._outcome(
            {
                "trace_count": n,
                "median_rms": median_rms,
                "dead_rms_threshold": dead_threshold,
                "zero_trace_count": int(zero_indices.size),
                "zero_trace_pct": round(self._pct(zero_indices.size, n), 5),
                "dead_trace_count": int(dead_indices.size),
                "dead_trace_pct": round(self._pct(dead_indices.size, n), 5),
            },
            findings,
        )

    def _noise(self, state: Dict[str, Any]) -> SegyStageOutcome:
        metrics = state["trace_metrics"]
        rms = metrics["rms"]
        noise_ratio = metrics["noise_ratio"]
        n = rms.size
        rms_median, rms_sigma = self._robust_center_scale(rms)
        rms_limit = rms_median + self._threshold("rms_outlier_mad_factor") * max(rms_sigma, np.finfo(float).eps)
        noisy_indices = np.flatnonzero(
            (noise_ratio > self._threshold("noise_ratio_max"))
            | (np.isfinite(rms) & (rms > rms_limit))
        )
        findings: List[SegyFinding] = []
        item = self._rate_finding(
            "NOISY_TRACES", "noise", "Noisy traces",
            "Trace roughness/noise ratio or robust RMS exceeds the selected profile threshold.",
            int(noisy_indices.size), n, self._threshold("noisy_trace_max_pct"), noisy_indices,
            "Inspect the affected traces for coupling, environmental, electrical or processing noise.",
        )
        if item:
            findings.append(item)
        return self._outcome(
            {
                "trace_count": n,
                "noisy_trace_count": int(noisy_indices.size),
                "noisy_trace_pct": round(self._pct(noisy_indices.size, n), 5),
                "noise_ratio_median": float(np.nanmedian(noise_ratio)) if n else 0.0,
                "noise_ratio_max": float(np.nanmax(noise_ratio)) if np.any(np.isfinite(noise_ratio)) else 0.0,
                "rms_robust_limit": rms_limit,
            },
            findings,
        )

    def _clipping_spike(self, state: Dict[str, Any]) -> SegyStageOutcome:
        metrics = state["trace_metrics"]
        plateau = metrics["plateau_fraction"]
        spike_score = metrics["spike_score"]
        n = plateau.size
        clipped_indices = np.flatnonzero(plateau * 100.0 >= self._threshold("clipping_plateau_min_pct"))
        spike_indices = np.flatnonzero(spike_score > self._threshold("spike_score_max"))
        findings: List[SegyFinding] = []
        item = self._rate_finding(
            "CLIPPED_TRACES", "amplitude", "Clipped traces",
            "A repeated plateau at the trace minimum or maximum indicates possible clipping.",
            int(clipped_indices.size), n, self._threshold("clipped_trace_max_pct"), clipped_indices,
            "Review recording/processing gain and obtain unclipped source data where available.",
        )
        if item:
            findings.append(item)
        item = self._rate_finding(
            "SPIKY_TRACES", "amplitude", "Spiky traces",
            "The maximum absolute sample is excessive relative to the median absolute amplitude.",
            int(spike_indices.size), n, self._threshold("spike_trace_max_pct"), spike_indices,
            "Inspect and edit isolated spikes only with an auditable processing workflow.",
        )
        if item:
            findings.append(item)
        return self._outcome(
            {
                "clipped_trace_count": int(clipped_indices.size),
                "clipped_trace_pct": round(self._pct(clipped_indices.size, n), 5),
                "spike_trace_count": int(spike_indices.size),
                "spike_trace_pct": round(self._pct(spike_indices.size, n), 5),
                "plateau_fraction_max_pct": float(np.nanmax(plateau) * 100.0) if np.any(np.isfinite(plateau)) else 0.0,
                "spike_score_max": float(np.nanmax(spike_score)) if np.any(np.isfinite(spike_score)) else 0.0,
            },
            findings,
        )

    def _dc_amplitude(self, state: Dict[str, Any]) -> SegyStageOutcome:
        metrics = state["trace_metrics"]
        dc_ratio = metrics["dc_bias_ratio"]
        max_abs = metrics["max_abs"]
        n = dc_ratio.size
        biased_indices = np.flatnonzero(dc_ratio > self._threshold("dc_bias_ratio_max"))
        findings: List[SegyFinding] = []
        item = self._rate_finding(
            "DC_BIAS_TRACES", "amplitude", "DC-biased traces",
            "Absolute trace mean is excessive relative to trace RMS.",
            int(biased_indices.size), n, self._threshold("dc_bias_trace_max_pct"), biased_indices,
            "Review instrument baseline, de-mean processing and trace editing.",
        )
        if item:
            findings.append(item)
        finite_peak = max_abs[np.isfinite(max_abs)]
        metrics_out = {
            "dc_bias_trace_count": int(biased_indices.size),
            "dc_bias_trace_pct": round(self._pct(biased_indices.size, n), 5),
            "dc_bias_ratio_median": float(np.nanmedian(dc_ratio)) if n else 0.0,
            "dc_bias_ratio_max": float(np.nanmax(dc_ratio)) if np.any(np.isfinite(dc_ratio)) else 0.0,
            "peak_amplitude_min": float(np.min(finite_peak)) if finite_peak.size else 0.0,
            "peak_amplitude_max": float(np.max(finite_peak)) if finite_peak.size else 0.0,
            "peak_amplitude_median": float(np.median(finite_peak)) if finite_peak.size else 0.0,
        }
        return self._outcome(metrics_out, findings)

    def _rms_energy(self, state: Dict[str, Any]) -> SegyStageOutcome:
        metrics = state["trace_metrics"]
        rms = metrics["rms"]
        energy = metrics["energy"]
        n = rms.size
        rms_center, rms_sigma = self._robust_center_scale(rms)
        energy_center, energy_sigma = self._robust_center_scale(energy)
        factor = self._threshold("energy_outlier_mad_factor")
        rms_outliers = np.flatnonzero(np.isfinite(rms) & (np.abs(rms - rms_center) > factor * max(rms_sigma, np.finfo(float).eps)))
        energy_outliers = np.flatnonzero(
            np.isfinite(energy) & (np.abs(energy - energy_center) > factor * max(energy_sigma, np.finfo(float).eps))
        )
        combined = np.unique(np.concatenate((rms_outliers, energy_outliers)))
        findings: List[SegyFinding] = []
        item = self._rate_finding(
            "ENERGY_OUTLIERS", "amplitude", "RMS or energy outlier traces",
            "Trace RMS or mean-square energy is outside the robust dataset distribution.",
            int(combined.size), n, self._threshold("energy_outlier_max_pct"), combined,
            "Review gain consistency, anomalous noise, dead channels and processing scaling.",
        )
        if item:
            findings.append(item)
        return self._outcome(
            {
                "rms_median": rms_center,
                "rms_robust_sigma": rms_sigma,
                "rms_outlier_count": int(rms_outliers.size),
                "energy_median": energy_center,
                "energy_robust_sigma": energy_sigma,
                "energy_outlier_count": int(energy_outliers.size),
                "combined_outlier_count": int(combined.size),
                "combined_outlier_pct": round(self._pct(combined.size, n), 5),
            },
            findings,
        )

    def _frequency(self, state: Dict[str, Any]) -> SegyStageOutcome:
        metrics = state["trace_metrics"]
        dominant_values = np.asarray(list(metrics["dominant_frequency"].values()), dtype=np.float64)
        bandwidth_values = np.asarray(list(metrics["bandwidth"].values()), dtype=np.float64)
        centroid_values = np.asarray(list(metrics.get("spectral_centroid", {}).values()), dtype=np.float64)
        entropy_values = np.asarray(list(metrics.get("spectral_entropy", {}).values()), dtype=np.float64)
        findings: List[SegyFinding] = []
        if dominant_values.size == 0:
            findings.append(
                SegyFinding(
                    "NO_SPECTRAL_ENERGY",
                    "warning",
                    "frequency",
                    "Spectral metrics unavailable",
                    "No representative trace contained sufficient non-zero spectral energy for frequency analysis.",
                    suggested_action="Review zero/dead traces and confirm sample interval values.",
                )
            )
            return self._outcome({"analysed_trace_count": 0}, findings)
        median_dom = float(np.median(dominant_values))
        median_bw = float(np.median(bandwidth_values)) if bandwidth_values.size else 0.0
        if not self._threshold("dominant_frequency_min_hz") <= median_dom <= self._threshold("dominant_frequency_max_hz"):
            findings.append(
                SegyFinding(
                    "DOMINANT_FREQUENCY_RANGE",
                    "warning",
                    "frequency",
                    "Dominant frequency outside profile range",
                    f"Median dominant frequency is {median_dom:.3f} Hz.",
                    "dominant_frequency_hz",
                    median_dom,
                    self._threshold("dominant_frequency_min_hz"),
                    self._threshold("dominant_frequency_max_hz"),
                    "Hz",
                    suggested_action="Confirm sample interval, anti-alias filtering, processing bandwidth and expected signal content.",
                )
            )
        if median_bw < self._threshold("bandwidth_min_hz"):
            findings.append(
                SegyFinding(
                    "LOW_BANDWIDTH",
                    "warning",
                    "frequency",
                    "Narrow spectral bandwidth",
                    f"Median 5-95% spectral bandwidth is {median_bw:.3f} Hz.",
                    "bandwidth_hz",
                    median_bw,
                    expected_min=self._threshold("bandwidth_min_hz"),
                    unit="Hz",
                    suggested_action="Review filtering, sampling, sensor response and processing flow.",
                )
            )
        return self._outcome(
            {
                "analysed_trace_count": int(dominant_values.size),
                "dominant_frequency_min_hz": float(np.min(dominant_values)),
                "dominant_frequency_max_hz": float(np.max(dominant_values)),
                "dominant_frequency_median_hz": median_dom,
                "bandwidth_min_hz": float(np.min(bandwidth_values)) if bandwidth_values.size else 0.0,
                "bandwidth_max_hz": float(np.max(bandwidth_values)) if bandwidth_values.size else 0.0,
                "bandwidth_median_hz": median_bw,
                "spectral_centroid_median_hz": float(np.median(centroid_values)) if centroid_values.size else 0.0,
                "spectral_entropy_median": float(np.median(entropy_values)) if entropy_values.size else 0.0,
                "spectral_estimator": "Hann-tapered power spectrum; 5-95% cumulative-power bandwidth; parabolic peak interpolation",
            },
            findings,
        )

    def _statics_timing(self, state: Dict[str, Any]) -> SegyStageOutcome:
        index: SegyTraceIndex = state["index"]
        n = index.trace_count
        static_indices = np.flatnonzero(np.abs(index.total_static_ms) > self._threshold("static_abs_max_ms"))
        delay_indices = np.flatnonzero(np.abs(index.delay_time_ms) > self._threshold("delay_time_abs_max_ms"))
        dt_indices = np.flatnonzero(index.sample_intervals_us != state["reader"].binary_header.sample_interval_us)
        findings: List[SegyFinding] = []
        item = self._rate_finding(
            "STATIC_OUTLIERS", "statics", "Excessive total statics",
            "Absolute total static correction exceeds the selected profile threshold.",
            int(static_indices.size), n, self._threshold("static_outlier_max_pct"), static_indices,
            "Review source/receiver statics, units and processing header mapping.",
        )
        if item:
            findings.append(item)
        if delay_indices.size:
            findings.append(
                SegyFinding(
                    "DELAY_TIME_OUTLIERS",
                    "warning",
                    "timing",
                    "Excessive delay recording time",
                    f"{delay_indices.size:,} traces exceed ±{self._threshold('delay_time_abs_max_ms'):.0f} ms delay time.",
                    trace_index=int(delay_indices[0]) + 1,
                    suggested_action="Confirm delay-time units and trace-header byte mapping.",
                    context=self._trace_context(delay_indices),
                )
            )
        return self._outcome(
            {
                "total_static_min_ms": int(index.total_static_ms.min()) if n else 0,
                "total_static_max_ms": int(index.total_static_ms.max()) if n else 0,
                "total_static_median_ms": float(np.median(index.total_static_ms)) if n else 0.0,
                "static_outlier_count": int(static_indices.size),
                "delay_time_min_ms": int(index.delay_time_ms.min()) if n else 0,
                "delay_time_max_ms": int(index.delay_time_ms.max()) if n else 0,
                "delay_outlier_count": int(delay_indices.size),
                "sample_interval_mismatch_count": int(dt_indices.size),
            },
            findings,
        )

    def _residual_statics(self, state: Dict[str, Any]) -> SegyStageOutcome:
        return self._stage_result_outcome(ResidualStaticsQCStage().run(state))

    def _velocity(self, state: Dict[str, Any]) -> SegyStageOutcome:
        return self._stage_result_outcome(VelocityQCStage().run(state))

    def _nmo(self, state: Dict[str, Any]) -> SegyStageOutcome:
        return self._stage_result_outcome(NMOQCStage().run(state))

    def _stack(self, state: Dict[str, Any]) -> SegyStageOutcome:
        return self._stage_result_outcome(StackQCStage().run(state))

    def _migration(self, state: Dict[str, Any]) -> SegyStageOutcome:
        return self._stage_result_outcome(MigrationQCStage().run(state))

    def _attribute(self, state: Dict[str, Any]) -> SegyStageOutcome:
        return self._stage_result_outcome(AttributeQCStage().run(state))

    def _repeatability(self, state: Dict[str, Any]) -> SegyStageOutcome:
        return self._stage_result_outcome(RepeatabilityQCStage().run(state))

    def _summary(self, state: Dict[str, Any]) -> SegyStageOutcome:
        prior = list(self._outcomes)
        severity_counts = {"critical": 0, "error": 0, "warning": 0, "info": 0}
        for outcome in prior:
            for finding in outcome.findings:
                severity_counts[finding.severity] = severity_counts.get(finding.severity, 0) + 1
        fail_count = sum(outcome.status == "fail" for outcome in prior)
        warn_count = sum(outcome.status == "warn" for outcome in prior)
        pass_count = sum(outcome.status == "pass" for outcome in prior)
        overall = "fail" if fail_count else "warn" if warn_count else "pass"
        score = float(np.mean([outcome.score for outcome in prior])) if prior else 100.0
        findings: List[SegyFinding] = []
        if overall == "fail":
            findings.append(
                SegyFinding(
                    "QC_RUN_FAILED",
                    "error",
                    "summary",
                    "QC acceptance failed",
                    f"{fail_count} QC stages failed. Resolve error/critical findings before accepting the file.",
                    suggested_action="Review failed stages, resolve findings and rerun QC after corrective action.",
                )
            )
        elif overall == "warn":
            findings.append(
                SegyFinding(
                    "QC_RUN_WARNING",
                    "warning",
                    "summary",
                    "QC completed with warnings",
                    f"{warn_count} QC stages completed with warnings.",
                    suggested_action="Review and disposition warning findings before delivery acceptance.",
                )
            )
        metrics = {
            "overall_result": overall,
            "overall_score_before_summary": round(score, 2),
            "stage_pass_count": pass_count,
            "stage_warn_count": warn_count,
            "stage_fail_count": fail_count,
            "finding_count": int(sum(severity_counts.values())),
            "severity_counts": severity_counts,
        }
        outcome = self._outcome(metrics, findings, f"Overall QC result: {overall.upper()}")
        outcome.score = round(score, 2)
        outcome.status = overall
        return outcome

    def _build_run_summary(
        self,
        state: Dict[str, Any],
        started: datetime,
        completed: datetime,
    ) -> SegyRunSummary:
        reader: SegyReader = state["reader"]
        index: SegyTraceIndex = state.get("index")
        severity_counts = {"critical": 0, "error": 0, "warning": 0, "info": 0}
        for outcome in self._outcomes:
            for finding in outcome.findings:
                severity_counts[finding.severity] = severity_counts.get(finding.severity, 0) + 1
        overall_result = "fail" if any(o.status == "fail" for o in self._outcomes) else (
            "warn" if any(o.status == "warn" for o in self._outcomes) else "pass"
        )
        score = float(np.mean([outcome.score for outcome in self._outcomes])) if self._outcomes else 0.0
        duration_ms = int((completed - started).total_seconds() * 1000)
        return SegyRunSummary(
            run_uuid=self.run_uuid,
            file_path=str(self.file_path),
            file_name=self.file_path.name,
            profile_key=self.profile.key,
            profile_name=self.profile.name,
            status="completed",
            overall_result=overall_result,
            score=round(score, 2),
            trace_count=index.trace_count if index is not None else 0,
            sample_count=reader.binary_header.samples_per_trace,
            sample_interval_us=reader.binary_header.sample_interval_us,
            stage_count=len(self._outcomes),
            finding_count=int(sum(severity_counts.values())),
            severity_counts=severity_counts,
            started_at=started.isoformat(),
            completed_at=completed.isoformat(),
            duration_ms=duration_ms,
            metadata={
                "sample_format_code": reader.binary_header.sample_format_code,
                "sample_format_name": reader.sample_format_name,
                "segy_revision": reader.binary_header.revision,
                "text_encoding": reader.text_header.encoding,
                "endian": "big" if reader.binary_header.endian == ">" else "little",
                "extended_text_header_count": reader.extended_header_count,
            },
        )
