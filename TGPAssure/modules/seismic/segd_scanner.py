from __future__ import annotations

import csv
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(slots=True)
class SegdScanResult:
    file_path: str
    file_name: str
    size_bytes: int
    status: str
    format_code: str = ""
    manufacturer: str = ""
    sample_interval_ms: float | None = None
    sample_count: int | None = None
    trace_count: int | None = None
    channel_sets: int | None = None
    source_line: str = ""
    source_point: str = ""
    source_x: float | None = None
    source_y: float | None = None
    source_elevation: float | None = None
    timebreak_ms: float | None = None
    uphole_ms: float | None = None
    receiver_error_count: int = 0
    warning_count: int = 0
    details: str = ""

    # Legacy 408/428 selectable output fields.
    serial_number: str = ""
    line: str = ""
    point: str = ""
    northing: float | None = None
    easting: float | None = None
    elevation: float | None = None
    channel_type: str = ""
    control_unit_type: str = ""
    control_unit_sn: str = ""
    assembly_sn: str = ""
    assembly_location: str = ""
    fdu_unit_type: str = ""
    channel_set: str = ""
    gain_code: str = ""
    filter_type: str = ""
    edited: str = ""
    overscale: str = ""
    number_of_interpolation: str = ""
    conversion_factor: str = ""
    trace_max_value: float | None = None
    sensor_type: str = ""
    trace_channel_type: str = ""
    resistance: float | None = None
    capacitance: float | None = None
    leakage: float | None = None
    tilt: float | None = None
    resistance_error: str = ""
    capacitance_error: str = ""
    leakage_error: str = ""
    tilt_error: str = ""
    resistance_limits: str = ""
    capacitance_limits: str = ""
    leakage_limits: str = ""
    tilt_limits: str = ""

    # Header-output check boxes from the legacy UI.
    general_headers: str = ""
    channel_set_header: str = ""
    extended_header: str = ""
    external_header: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


FILE_HEADER_FIELDS: tuple[tuple[str, str], ...] = (
    ("general_headers", "General Headers"),
    ("channel_set_header", "Channel Set Header"),
    ("extended_header", "Extended Header"),
    ("external_header", "External Header"),
)

SELECTABLE_FIELDS: tuple[tuple[str, str], ...] = (
    ("serial_number", "Serial Number"),
    ("line", "Line"),
    ("point", "Point"),
    ("northing", "Northing"),
    ("easting", "Easting"),
    ("elevation", "Elevation"),
    ("channel_type", "Channel Type"),
    ("control_unit_type", "Control Unit Type"),
    ("control_unit_sn", "Control Unit S/N"),
    ("assembly_sn", "Assembly S/N"),
    ("assembly_location", "Assembly Location"),
    ("fdu_unit_type", "FDU Unit Type"),
    ("channel_set", "Channel Set"),
    ("gain_code", "Gain Code"),
    ("filter_type", "Filter Type"),
    ("edited", "Edited"),
    ("overscale", "Overscale"),
    ("number_of_interpolation", "Number Of Interpolation"),
    ("conversion_factor", "Conversion Factor"),
    ("trace_max_value", "Trace Max Value"),
    ("sensor_type", "Sensor Type"),
    ("trace_channel_type", "Channel Type"),
    ("resistance", "Resistance"),
    ("capacitance", "Capacitance"),
    ("leakage", "Leakage"),
    ("tilt", "Tilt"),
    ("resistance_error", "Resistance Error"),
    ("capacitance_error", "Capacitance Error"),
    ("leakage_error", "Leakage Error"),
    ("tilt_error", "Tilt Error"),
    ("resistance_limits", "Resistance Limits"),
    ("capacitance_limits", "Capacitance Limits"),
    ("leakage_limits", "Leakage Limits"),
    ("tilt_limits", "Tilt Limits"),
)

DEFAULT_SUMMARY_FIELDS: tuple[tuple[str, str], ...] = (
    ("status", "Status"), ("file_name", "File"), ("size_bytes", "Bytes"),
    ("format_code", "Format"), ("manufacturer", "Manufacturer"),
    ("sample_interval_ms", "SI ms"), ("sample_count", "Samples"),
    ("trace_count", "Traces"), ("channel_sets", "Sets"),
    ("warning_count", "Warnings"), ("details", "Details"),
)

_MANUFACTURERS = {
    13: "Sercel",
    20: "Input/Output",
    21: "Geosource/Halliburton",
    22: "Geo-X",
    32: "Sercel / CGG family",
}

_CHANNEL_TYPE_NAMES = {
    0: "Unknown",
    1: "Seismic",
    2: "Time Break",
    3: "Uphole",
    4: "Water Break",
    5: "Time Counter",
    6: "External Data",
    7: "Other",
}


def _bcd_number(data: bytes) -> int | None:
    digits: list[str] = []
    for b in data:
        hi = (b >> 4) & 0xF; lo = b & 0xF
        if hi > 9 or lo > 9:
            return None
        digits.extend([str(hi), str(lo)])
    try:
        return int("".join(digits))
    except ValueError:
        return None


def _ascii_scan(data: bytes) -> str:
    text = data.decode("latin-1", errors="ignore")
    text = re.sub(r"[^\x20-\x7E\n\r\t]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _find_number(text: str, patterns: tuple[str, ...]) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except Exception:
                continue
    return None


def _finite(value: object) -> object:
    if value in (None, ""):
        return ""
    try:
        f = float(value)
        if abs(f) > 9.9e35:
            return ""
    except Exception:
        pass
    return value


def _limit_text(low: object = None, high: object = None, limit: object = None) -> str:
    low = _finite(low); high = _finite(high); limit = _finite(limit)
    if low != "" or high != "":
        return f"{low}–{high}".strip("–")
    if limit != "":
        return f"≤ {limit}"
    return ""


class SegdHeaderScanner:
    """Batch-oriented SEG-D/Sercel 408/428 header audit.

    This class exposes the same selectable output idea as the legacy 408 Header
    Scanner while using the platform SEG-D reader where possible. Unsupported
    records still produce a fallback row instead of being hidden from the audit.
    """

    def scan_path(self, path: str | Path) -> list[SegdScanResult]:
        p = Path(path)
        if p.is_dir():
            files = [f for f in sorted(p.rglob("*")) if f.is_file() and f.suffix.lower() in {".segd", ".sgd", ".d", ".dat", ".bin", ".raw", ".000"}]
        else:
            files = [p]
        if not files:
            raise ValueError("No SEG-D candidate files were found.")
        return [self.scan_file(f) for f in files]

    def scan_file(self, path: str | Path) -> SegdScanResult:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(p)
        try:
            return self._scan_with_native_reader(p)
        except Exception as native_error:
            return self._scan_fallback(p, str(native_error))

    def _scan_with_native_reader(self, path: Path) -> SegdScanResult:
        from modules.seismic.segd_viewer.segd_reader import SegdReader

        reader = SegdReader(path)
        gh1 = getattr(reader, "general_header_1", None)
        gh2 = getattr(reader, "general_header_2", None)
        gh3 = getattr(reader, "general_header_3", None)
        descriptors = getattr(reader, "channel_set_descriptors", []) or []
        traces = getattr(reader, "_trace_index", []) or []
        trace_count = int(getattr(reader, "_trace_count", len(traces)) or len(traces))
        sample_count = int(getattr(reader, "_sample_count", 0) or 0) or None
        sample_interval = float(getattr(reader, "_sample_interval", 0.0) or 0.0) or None
        format_code = str(getattr(gh1, "format_code", reader.get_format_code() if hasattr(reader, "get_format_code") else "8058"))
        manufacturer_code = getattr(gh1, "manufacturer_code", -1)
        manufacturer = _MANUFACTURERS.get(manufacturer_code, str(manufacturer_code) if manufacturer_code not in (None, -1) else "")

        first_trace = None
        if traces:
            try:
                first_trace = reader.get_trace_info(0, decode_extensions=True)
            except Exception:
                first_trace = traces[0]

        receiver_error_count = 0
        for trace in traces[:1000]:
            try:
                if hasattr(reader, "get_trace_info"):
                    trace = reader.get_trace_info(getattr(trace, "physical_index", 0), decode_extensions=True)
            except Exception:
                pass
            for attr in ("resistance", "capacitance", "leakage", "tilt"):
                value = getattr(trace, attr, None)
                if value is None:
                    continue
                low = getattr(trace, attr + "_low_limit", None)
                high = getattr(trace, attr + "_high_limit", None)
                limit = getattr(trace, attr + "_limit", None)
                if high is not None and value > high:
                    receiver_error_count += 1
                elif low is not None and value < low:
                    receiver_error_count += 1
                elif limit is not None and value > limit:
                    receiver_error_count += 1

        desc_text = "; ".join(
            f"set {getattr(d, 'channel_set_id', '')}: type={getattr(d, 'channel_type', '')}, channels={getattr(d, 'channel_count', '')}, si={getattr(d, 'sample_interval', '')} ms, samples={getattr(d, 'sample_count', '')}"
            for d in descriptors[:12]
        )
        if len(descriptors) > 12:
            desc_text += f"; +{len(descriptors)-12} more"

        general_text = (
            f"File={getattr(gh1, 'file_number', '')}; Format={format_code}; Manufacturer={manufacturer}; "
            f"Date={getattr(gh1, 'date', '')} {getattr(gh1, 'time', '')}; "
            f"ChannelSets={len(descriptors)}; MaxTraces={getattr(gh2, 'maximum_traces', '')}; "
            f"ExtendedHeaders={getattr(gh3, 'extended_headers_count', '')}"
        )
        warning_count = receiver_error_count
        status = "PASS" if warning_count == 0 else "WARN"
        kwargs = {}
        if first_trace is not None:
            ch_type = getattr(first_trace, "channel_type", "")
            ch_name = _CHANNEL_TYPE_NAMES.get(ch_type, str(ch_type)) if ch_type != "" else ""
            resistance_low = getattr(first_trace, "resistance_low_limit", None)
            resistance_high = getattr(first_trace, "resistance_high_limit", None)
            capacitance_low = getattr(first_trace, "capacitance_low_limit", None)
            capacitance_high = getattr(first_trace, "capacitance_high_limit", None)
            kwargs.update(
                line=str(_finite(getattr(first_trace, "receiver_line", ""))),
                point=str(_finite(getattr(first_trace, "receiver_point", ""))),
                northing=_finite(getattr(first_trace, "receiver_y", None)) or None,
                easting=_finite(getattr(first_trace, "receiver_x", None)) or None,
                elevation=_finite(getattr(first_trace, "receiver_elevation", None)) or None,
                channel_type=ch_name,
                trace_channel_type=ch_name,
                sensor_type=str(_finite(getattr(first_trace, "sensor_type", ""))),
                channel_set=str(_finite(getattr(first_trace, "channel_set", ""))),
                fdu_unit_type="FDU/DSU trace extension" if getattr(first_trace, "extensions_decoded", False) else "",
                edited=str(_finite(getattr(first_trace, "trace_edit", ""))),
                resistance=_finite(getattr(first_trace, "resistance", None)) or None,
                capacitance=_finite(getattr(first_trace, "capacitance", None)) or None,
                leakage=_finite(getattr(first_trace, "leakage", None)) or None,
                tilt=_finite(getattr(first_trace, "tilt", None)) or None,
                resistance_limits=_limit_text(resistance_low, resistance_high),
                capacitance_limits=_limit_text(capacitance_low, capacitance_high),
                leakage_limits=_limit_text(limit=getattr(first_trace, "leakage_limit", None)),
                tilt_limits=_limit_text(limit=getattr(first_trace, "tilt_limit", None)),
            )
            flags = set(getattr(first_trace, "qc_flags", ()) or ())
            kwargs.update(
                resistance_error="Yes" if "Resistance" in flags else "",
                capacitance_error="Yes" if "Capacitance" in flags else "",
                leakage_error="Yes" if "Leakage" in flags else "",
                tilt_error="Yes" if "Tilt" in flags else "",
            )

        return SegdScanResult(
            file_path=str(path), file_name=path.name, size_bytes=path.stat().st_size, status=status,
            format_code=format_code, manufacturer=manufacturer, sample_interval_ms=sample_interval,
            sample_count=sample_count, trace_count=trace_count, channel_sets=len(descriptors),
            receiver_error_count=receiver_error_count, warning_count=warning_count,
            serial_number=str(getattr(gh1, "file_number", "")),
            source_line=kwargs.get("line", ""), source_point=kwargs.get("point", ""),
            source_x=kwargs.get("easting") if isinstance(kwargs.get("easting"), (int, float)) else None,
            source_y=kwargs.get("northing") if isinstance(kwargs.get("northing"), (int, float)) else None,
            source_elevation=kwargs.get("elevation") if isinstance(kwargs.get("elevation"), (int, float)) else None,
            details="Native SEG-D index decoded; selectable 408/428 output fields available.",
            general_headers=general_text,
            channel_set_header=desc_text,
            extended_header=f"Trace extensions decoded for representative trace; extension count={getattr(first_trace, 'trace_header_extensions', '') if first_trace else ''}",
            external_header="No vendor external-header text block decoded by current reader." if getattr(gh3, "extended_headers_count", 0) else "",
            **kwargs,
        )

    def _scan_fallback(self, path: Path, native_error: str) -> SegdScanResult:
        size = path.stat().st_size
        data = path.read_bytes()[:131072]
        text = _ascii_scan(data)
        status = "WARN"
        warnings = 1
        details = f"Fallback scan used because native reader reported: {native_error}"
        format_code = ""
        if len(data) >= 8:
            for start in (2, 4, 8, 10, 16):
                number = _bcd_number(data[start:start+2]) if len(data) >= start + 2 else None
                if number and 1000 <= number <= 9999:
                    format_code = str(number); break
        ascii_fmt = re.search(r"(?:FORMAT|SEG\s*-?D)[^0-9]{0,20}(\d{4})", text, re.I)
        if ascii_fmt:
            format_code = ascii_fmt.group(1)
        sample_interval = _find_number(text, (r"SAMPLE\s*(?:INTERVAL|RATE)[^0-9]{0,20}(\d+(?:\.\d+)?)", r"SI[^0-9]{0,10}(\d+(?:\.\d+)?)"))
        sample_count = _find_number(text, (r"\bSAMPLES\b[^0-9]{0,20}(\d+)", r"NS[^0-9]{0,10}(\d+)"))
        trace_count = _find_number(text, (r"TRACES?[^0-9]{0,20}(\d+)", r"CHANNELS?[^0-9]{0,20}(\d+)"))
        source_x = _find_number(text, (r"SOURCE\s*(?:X|EASTING)[^0-9\-+]{0,20}([-+]?\d+(?:\.\d+)?)", r"SRC[_ ]?X[^0-9\-+]{0,20}([-+]?\d+(?:\.\d+)?)"))
        source_y = _find_number(text, (r"SOURCE\s*(?:Y|NORTHING)[^0-9\-+]{0,20}([-+]?\d+(?:\.\d+)?)", r"SRC[_ ]?Y[^0-9\-+]{0,20}([-+]?\d+(?:\.\d+)?)"))
        elevation = _find_number(text, (r"(?:SOURCE\s*)?ELEVATION[^0-9\-+]{0,20}([-+]?\d+(?:\.\d+)?)", r"ELEV[^0-9\-+]{0,10}([-+]?\d+(?:\.\d+)?)"))
        timebreak = _find_number(text, (r"TIMEBREAK[^0-9\-+]{0,20}([-+]?\d+(?:\.\d+)?)", r"TB[^0-9\-+]{0,10}([-+]?\d+(?:\.\d+)?)"))
        uphole = _find_number(text, (r"UPHOLE[^0-9\-+]{0,20}([-+]?\d+(?:\.\d+)?)", r"UH[^0-9\-+]{0,10}([-+]?\d+(?:\.\d+)?)"))
        line = _find_number(text, (r"\bLINE[^0-9\-+]{0,20}([-+]?\d+(?:\.\d+)?)", r"RECEIVER\s*LINE[^0-9\-+]{0,20}([-+]?\d+(?:\.\d+)?)"))
        point = _find_number(text, (r"\bPOINT[^0-9\-+]{0,20}([-+]?\d+(?:\.\d+)?)", r"RECEIVER\s*POINT[^0-9\-+]{0,20}([-+]?\d+(?:\.\d+)?)"))
        manufacturer = ""
        upper = text.upper().replace(" ", "")
        for word in ("SERCEL", "SN428", "CM428", "408", "428", "VQC", "FDU"):
            if word in upper:
                manufacturer = "Sercel/428 family"; break
        if format_code or sample_interval or trace_count:
            status = "REVIEW"; warnings = 1
        if not data:
            status = "FAIL"; warnings = 2; details = "Empty file."
        return SegdScanResult(
            file_path=str(path), file_name=path.name, size_bytes=size, status=status, format_code=format_code,
            manufacturer=manufacturer, sample_interval_ms=sample_interval, sample_count=int(sample_count) if sample_count else None,
            trace_count=int(trace_count) if trace_count else None, source_x=source_x, source_y=source_y,
            source_elevation=elevation, timebreak_ms=timebreak, uphole_ms=uphole, warning_count=warnings,
            details=details, line=str(line or ""), point=str(point or ""), easting=source_x, northing=source_y,
            elevation=elevation, general_headers=text[:1000], external_header="ASCII/header evidence detected by fallback scanner" if text else "",
        )

    @staticmethod
    def field_labels(keys: Sequence[str]) -> list[str]:
        labels = dict(DEFAULT_SUMMARY_FIELDS + FILE_HEADER_FIELDS + SELECTABLE_FIELDS)
        return [labels.get(k, k) for k in keys]

    @staticmethod
    def selected_field_keys(include_summary: bool = True, include_headers: Iterable[str] = (), include_fields: Iterable[str] = ()) -> list[str]:
        keys: list[str] = []
        if include_summary:
            keys.extend([k for k, _ in DEFAULT_SUMMARY_FIELDS])
        keys.extend([k for k in include_headers if k not in keys])
        keys.extend([k for k in include_fields if k not in keys])
        return keys

    @staticmethod
    def export_csv(results: list[SegdScanResult], path: str | Path, field_keys: Sequence[str] | None = None) -> None:
        keys = list(field_keys) if field_keys else list(SegdScanResult("", "", 0, "").to_dict().keys())
        p = Path(path)
        with p.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=keys)
            writer.writeheader()
            for result in results:
                row = result.to_dict()
                writer.writerow({key: row.get(key, "") for key in keys})

    @staticmethod
    def export_txt(results: list[SegdScanResult], path: str | Path, field_keys: Sequence[str]) -> None:
        labels = dict(DEFAULT_SUMMARY_FIELDS + FILE_HEADER_FIELDS + SELECTABLE_FIELDS)
        p = Path(path)
        lines: list[str] = []
        for result in results:
            row = result.to_dict()
            lines.append("=" * 92)
            lines.append(f"{result.file_name}  [{result.status}]")
            lines.append("-" * 92)
            for key in field_keys:
                lines.append(f"{labels.get(key, key):28s}: {row.get(key, '')}")
            lines.append("")
        p.write_text("\n".join(lines), encoding="utf-8")
