from __future__ import annotations

import csv
import re
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass(slots=True)
class VapsRecord:
    vib: str = ""
    vp: str = ""
    time: str = ""
    drive_level_pct: float | None = None
    avg_phase_deg: float | None = None
    peak_phase_deg: float | None = None
    avg_distortion_pct: float | None = None
    peak_distortion_pct: float | None = None
    avg_force: float | None = None
    peak_force: float | None = None
    avg_viscosity: float | None = None
    avg_stiffness: float | None = None
    hdop: float | None = None
    status_code: str = ""
    mass_warning: bool = False
    plate_warning: bool = False
    force_overload: bool = False
    pressure_overload: bool = False
    mass_overload: bool = False
    valve_overload: bool = False
    excitation_overload: bool = False
    source_line: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class VapsQcLimits:
    drive_min_pct: float = 20.0
    drive_max_pct: float = 95.0
    avg_phase_abs_max_deg: float = 8.0
    peak_phase_abs_max_deg: float = 20.0
    avg_distortion_max_pct: float = 5.0
    peak_distortion_max_pct: float = 15.0
    hdop_max: float = 4.0


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).strip().lower()).strip("_")


def _float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text: return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text)
    if not m: return None
    try: return float(m.group(0))
    except ValueError: return None


def _bool(value: object) -> bool:
    text = str(value).strip().lower()
    if not text: return False
    if text in {"1", "true", "yes", "y", "warn", "warning", "overload", "bad", "fail"}: return True
    number = _float(text)
    return bool(number and number != 0)


_ALIASES: dict[str, tuple[str, ...]] = {
    "vib": ("vib", "vibrator", "vib_no", "vib_number", "fleet", "unit"),
    "vp": ("vp", "vpoint", "vibrator_point", "source_point", "shot", "station"),
    "time": ("time", "date", "datetime", "timestamp", "gps_time"),
    "drive_level_pct": ("drive", "drive_level", "drive_level_pct", "drive_pct", "dl"),
    "avg_phase_deg": ("avg_phase", "average_phase", "mean_phase", "phase_avg"),
    "peak_phase_deg": ("peak_phase", "max_phase", "phase_peak"),
    "avg_distortion_pct": ("avg_distortion", "average_distortion", "distortion_avg", "mean_distortion"),
    "peak_distortion_pct": ("peak_distortion", "max_distortion", "distortion_peak"),
    "avg_force": ("avg_force", "average_force", "mean_force", "force_avg"),
    "peak_force": ("peak_force", "max_force", "force_peak"),
    "avg_viscosity": ("avg_viscosity", "viscosity", "average_viscosity"),
    "avg_stiffness": ("avg_stiffness", "stiffness", "average_stiffness"),
    "hdop": ("hdop", "gps_hdop", "dop"),
    "status_code": ("status", "status_code", "vib_status"),
    "mass_warning": ("mass_warning", "mass_warn"),
    "plate_warning": ("plate_warning", "plate_warn", "baseplate_warning"),
    "force_overload": ("force_overload", "force_ol"),
    "pressure_overload": ("pressure_overload", "over_pressure", "hydraulic_pressure"),
    "mass_overload": ("mass_overload", "mass_ol"),
    "valve_overload": ("valve_overload", "valve_ol"),
    "excitation_overload": ("excitation_overload", "excitation_ol", "exciter_overload"),
}


class VapsReader:
    """VAPS/H26 verbose vibrator attribute import and QC helper."""

    def read(self, file_path: str | Path) -> list[VapsRecord]:
        path = Path(file_path)
        if not path.is_file(): raise FileNotFoundError(path)
        raw = path.read_bytes()
        if b"\x00" in raw[:4096] and path.suffix.lower() not in {".h26"}:
            raise ValueError("Binary VAPS/H26 file detected. Export verbose vibrator attributes to CSV/TXT or use an ASCII H26 dump.")
        text = self._decode(raw)
        rows = self._rows(text)
        records = self._parse_table(rows)
        if not records:
            records = self._parse_fixed_text(text)
        if not records:
            raise ValueError("No VAPS/H26 vibrator-attribute records were recognized.")
        return records

    def _decode(self, raw: bytes) -> str:
        for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
            try: return raw.decode(enc)
            except UnicodeDecodeError: continue
        return raw.decode("latin-1", errors="replace")

    def _rows(self, text: str) -> list[list[str]]:
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines: return []
        try:
            delimiter = csv.Sniffer().sniff("\n".join(lines[:20]), delimiters=",;\t|").delimiter
            return list(csv.reader(lines, delimiter=delimiter))
        except Exception:
            if len(re.split(r"\s{2,}", lines[0])) >= 3:
                return [re.split(r"\s{2,}", line.strip()) for line in lines]
            return [line.split() for line in lines]

    def _parse_table(self, rows: list[list[str]]) -> list[VapsRecord]:
        if len(rows) < 2: return []
        header_idx = None; mapping = {}
        for i, row in enumerate(rows[:20]):
            headers = [_norm(c) for c in row]
            candidate = self._map(headers)
            if len(candidate) >= 3 and ("vib" in candidate or "drive_level_pct" in candidate or "avg_phase_deg" in candidate):
                header_idx = i; mapping = candidate; break
        if header_idx is None: return []
        headers = [_norm(c) for c in rows[header_idx]]
        output: list[VapsRecord] = []
        for line_no, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
            data = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
            rec = self._from_mapping(mapping, data); rec.source_line = line_no
            if rec.vib or rec.vp or any(getattr(rec, f) is not None for f in ("drive_level_pct", "avg_phase_deg", "avg_force")):
                output.append(rec)
        return output

    def _map(self, headers: list[str]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for field, aliases in _ALIASES.items():
            for h in headers:
                if h in aliases or any(alias in h for alias in aliases if len(alias) > 3):
                    mapping[field] = h; break
        return mapping

    def _from_mapping(self, mapping: dict[str, str], data: dict[str, str]) -> VapsRecord:
        def text(field: str) -> str: return str(data.get(mapping.get(field, ""), "")).strip()
        return VapsRecord(
            vib=text("vib"), vp=text("vp"), time=text("time"), drive_level_pct=_float(text("drive_level_pct")),
            avg_phase_deg=_float(text("avg_phase_deg")), peak_phase_deg=_float(text("peak_phase_deg")),
            avg_distortion_pct=_float(text("avg_distortion_pct")), peak_distortion_pct=_float(text("peak_distortion_pct")),
            avg_force=_float(text("avg_force")), peak_force=_float(text("peak_force")), avg_viscosity=_float(text("avg_viscosity")),
            avg_stiffness=_float(text("avg_stiffness")), hdop=_float(text("hdop")), status_code=text("status_code"),
            mass_warning=_bool(text("mass_warning")), plate_warning=_bool(text("plate_warning")), force_overload=_bool(text("force_overload")),
            pressure_overload=_bool(text("pressure_overload")), mass_overload=_bool(text("mass_overload")), valve_overload=_bool(text("valve_overload")),
            excitation_overload=_bool(text("excitation_overload")),
        )

    def _parse_fixed_text(self, text: str) -> list[VapsRecord]:
        records: list[VapsRecord] = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            low = line.lower()
            if not any(key in low for key in ("vib", "phase", "distortion", "drive", "force")):
                continue
            rec = VapsRecord(source_line=line_no)
            for field, patterns in {
                "vib": (r"vib(?:rator)?\s*[:=]?\s*([A-Za-z0-9_-]+)",),
                "vp": (r"vp\s*[:=]?\s*([A-Za-z0-9_.-]+)", r"source\s*point\s*[:=]?\s*([A-Za-z0-9_.-]+)"),
                "drive_level_pct": (r"drive(?:\s*level)?\s*[:=]?\s*([-+]?\d+(?:\.\d+)?)",),
                "avg_phase_deg": (r"avg(?:erage)?\s*phase\s*[:=]?\s*([-+]?\d+(?:\.\d+)?)",),
                "peak_phase_deg": (r"peak\s*phase\s*[:=]?\s*([-+]?\d+(?:\.\d+)?)",),
                "avg_distortion_pct": (r"avg(?:erage)?\s*distortion\s*[:=]?\s*([-+]?\d+(?:\.\d+)?)",),
                "peak_distortion_pct": (r"peak\s*distortion\s*[:=]?\s*([-+]?\d+(?:\.\d+)?)",),
                "hdop": (r"hdop\s*[:=]?\s*([-+]?\d+(?:\.\d+)?)",),
            }.items():
                for pattern in patterns:
                    m = re.search(pattern, line, re.I)
                    if m:
                        if field in {"vib", "vp"}: setattr(rec, field, m.group(1))
                        else: setattr(rec, field, _float(m.group(1)))
                        break
            rec.mass_warning = "mass warning" in low
            rec.plate_warning = "plate warning" in low
            rec.force_overload = "force overload" in low
            rec.pressure_overload = "pressure overload" in low or "over pressure" in low
            rec.mass_overload = "mass overload" in low
            rec.valve_overload = "valve overload" in low
            rec.excitation_overload = "excitation overload" in low
            if rec.vib or rec.vp or rec.drive_level_pct is not None or rec.avg_phase_deg is not None:
                records.append(rec)
        return records


class VapsQcEngine:
    def __init__(self, limits: VapsQcLimits | None = None) -> None:
        self.limits = limits or VapsQcLimits()

    def evaluate_record(self, record: VapsRecord) -> tuple[str, list[str]]:
        l = self.limits; findings: list[str] = []
        if record.drive_level_pct is not None and (record.drive_level_pct < l.drive_min_pct or record.drive_level_pct > l.drive_max_pct):
            findings.append(f"Drive level outside limit ({record.drive_level_pct:g}%)")
        if record.avg_phase_deg is not None and abs(record.avg_phase_deg) > l.avg_phase_abs_max_deg:
            findings.append(f"Average phase exceeds ±{l.avg_phase_abs_max_deg:g}°")
        if record.peak_phase_deg is not None and abs(record.peak_phase_deg) > l.peak_phase_abs_max_deg:
            findings.append(f"Peak phase exceeds ±{l.peak_phase_abs_max_deg:g}°")
        if record.avg_distortion_pct is not None and record.avg_distortion_pct > l.avg_distortion_max_pct:
            findings.append(f"Average distortion exceeds {l.avg_distortion_max_pct:g}%")
        if record.peak_distortion_pct is not None and record.peak_distortion_pct > l.peak_distortion_max_pct:
            findings.append(f"Peak distortion exceeds {l.peak_distortion_max_pct:g}%")
        if record.hdop is not None and record.hdop > l.hdop_max:
            findings.append(f"HDOP exceeds {l.hdop_max:g}")
        for label, flag in (("mass warning", record.mass_warning), ("plate warning", record.plate_warning), ("force overload", record.force_overload), ("pressure overload", record.pressure_overload), ("mass overload", record.mass_overload), ("valve overload", record.valve_overload), ("excitation overload", record.excitation_overload)):
            if flag: findings.append(label)
        return ("FAIL" if findings else "PASS", findings)

    def summarize(self, records: list[VapsRecord]) -> dict[str, object]:
        statuses = [self.evaluate_record(r) for r in records]
        failed = sum(1 for status, _ in statuses if status == "FAIL")
        vib_ids = sorted({r.vib for r in records if r.vib})
        warning_counts: dict[str, int] = {}
        for _status, findings in statuses:
            for finding in findings:
                key = finding.split("(")[0].strip()
                warning_counts[key] = warning_counts.get(key, 0) + 1
        return {"records": len(records), "vibs": len(vib_ids), "fail": failed, "pass": len(records) - failed, "warnings": warning_counts}
