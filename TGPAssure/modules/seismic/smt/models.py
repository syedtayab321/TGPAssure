from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


MEASUREMENT_FIELDS: tuple[str, ...] = (
    "noise",
    "resistance",
    "frequency",
    "damping",
    "sensitivity",
    "temperature",
    "distortion",
    "impedance",
)

MEASUREMENT_LABELS: dict[str, str] = {
    "noise": "Noise",
    "resistance": "Resistance",
    "frequency": "Frequency",
    "damping": "Damping",
    "sensitivity": "Sensitivity",
    "temperature": "Temperature",
    "distortion": "Distortion",
    "impedance": "Impedance",
}


@dataclass(slots=True)
class SmtTestRecord:
    string_no: str = ""
    serial: str = ""
    tester: str = ""
    operator: str = ""
    tested_at: datetime | None = None
    original_tested_at: str = ""
    model: str = "SMT200"
    source_result: str = ""
    noise: float | None = None
    resistance: float | None = None
    frequency: float | None = None
    damping: float | None = None
    sensitivity: float | None = None
    temperature: float | None = None
    distortion: float | None = None
    impedance: float | None = None
    polarity: str = ""
    notes: str = ""
    source_file: str = ""
    source_hash: str = ""
    source_row: int = 0
    date_corrected: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def identity(self) -> str:
        return (self.string_no or self.serial).strip()


@dataclass(slots=True)
class MeasurementLimit:
    minimum: float | None = None
    nominal: float | None = None
    maximum: float | None = None
    color: str = "#1ED760"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None, default: "MeasurementLimit") -> "MeasurementLimit":
        source = data or {}
        return cls(
            minimum=_optional_float(source.get("minimum"), default.minimum),
            nominal=_optional_float(source.get("nominal"), default.nominal),
            maximum=_optional_float(source.get("maximum"), default.maximum),
            color=str(source.get("color") or default.color),
        )


@dataclass(slots=True)
class SmtConfiguration:
    contractor: str = ""
    client: str = ""
    crew: str = ""
    string_description: str = "SMT receiver string"
    string_min: int = 1
    string_max: int = 60000
    histogram_bins: int = 30
    minimum_valid_year: int = 2013
    reference_string_1: str = ""
    reference_string_2: str = ""
    logo_path: str = ""
    show_logo: bool = False
    special_sgt_support: bool = True
    supported_models: tuple[str, ...] = ("SMT200", "SMT300", "SMT400", "SGT-II")
    polarity_fail_words: tuple[str, ...] = ("reverse", "reversed", "negative", "bad", "fail")
    limits: dict[str, MeasurementLimit] = field(default_factory=dict)

    @classmethod
    def defaults(cls) -> "SmtConfiguration":
        return cls(
            limits={
                # Values and colours mirror the SMTAN2 configuration screen in the reference PDF.
                "noise": MeasurementLimit(0.0, 0.0, 5.0, "#0000FF"),
                "resistance": MeasurementLimit(1713.0, 1757.0, 1802.0, "#00FF00"),
                "frequency": MeasurementLimit(9.75, 10.0, 10.25, "#C0C0C0"),
                "damping": MeasurementLimit(0.60, 0.60, 0.63, "#FF00FF"),
                "sensitivity": MeasurementLimit(131.5, 134.9, 138.3, "#000000"),
                "temperature": MeasurementLimit(0.0, 0.0, 50.0, "#FF0000"),
                "distortion": MeasurementLimit(0.0, 0.0, 0.10, "#FFFF00"),
                "impedance": MeasurementLimit(3000.0, 0.0, 7000.0, "#FF0000"),
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contractor": self.contractor,
            "client": self.client,
            "crew": self.crew,
            "string_description": self.string_description,
            "string_min": self.string_min,
            "string_max": self.string_max,
            "histogram_bins": self.histogram_bins,
            "minimum_valid_year": self.minimum_valid_year,
            "reference_string_1": self.reference_string_1,
            "reference_string_2": self.reference_string_2,
            "logo_path": self.logo_path,
            "show_logo": self.show_logo,
            "special_sgt_support": self.special_sgt_support,
            "supported_models": list(self.supported_models),
            "polarity_fail_words": list(self.polarity_fail_words),
            "limits": {key: value.to_dict() for key, value in self.limits.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SmtConfiguration":
        defaults = cls.defaults()
        source = data or {}
        limits_source = source.get("limits") if isinstance(source.get("limits"), dict) else {}
        limits = {
            key: MeasurementLimit.from_dict(limits_source.get(key), defaults.limits[key])
            for key in MEASUREMENT_FIELDS
        }
        models = source.get("supported_models") or defaults.supported_models
        fail_words = source.get("polarity_fail_words") or defaults.polarity_fail_words
        return cls(
            contractor=str(source.get("contractor") or defaults.contractor),
            client=str(source.get("client") or defaults.client),
            crew=str(source.get("crew") or defaults.crew),
            string_description=str(source.get("string_description") or defaults.string_description),
            string_min=_safe_int(source.get("string_min"), defaults.string_min),
            string_max=_safe_int(source.get("string_max"), defaults.string_max),
            histogram_bins=max(5, min(200, _safe_int(source.get("histogram_bins"), defaults.histogram_bins))),
            minimum_valid_year=max(1900, min(2200, _safe_int(source.get("minimum_valid_year"), defaults.minimum_valid_year))),
            reference_string_1=str(source.get("reference_string_1") or ""),
            reference_string_2=str(source.get("reference_string_2") or ""),
            logo_path=str(source.get("logo_path") or ""),
            show_logo=bool(source.get("show_logo", False)),
            special_sgt_support=bool(source.get("special_sgt_support", True)),
            supported_models=tuple(str(item) for item in models),
            polarity_fail_words=tuple(str(item).lower() for item in fail_words),
            limits=limits,
        )


@dataclass(slots=True)
class ImportOptions:
    minimum_valid_year: int = 2013
    bad_date_mode: str = "warn"  # warn, accept, reject, correct
    replacement_date: str = "file"  # today, yesterday, file
    duplicate_mode: str = "skip"  # skip, replace, allow
    update_pending: str = "manual"  # manual, after_each, after_all


@dataclass(slots=True)
class ImportSummary:
    files: int = 0
    parsed: int = 0
    inserted: int = 0
    replaced: int = 0
    duplicates: int = 0
    rejected: int = 0
    corrected_dates: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SmtEvaluation:
    status: str
    failure_flags: tuple[str, ...]


def evaluate_record(record: SmtTestRecord, configuration: SmtConfiguration) -> SmtEvaluation:
    flags: list[str] = []
    source_status = record.source_result.strip().upper()
    if source_status in {"FAIL", "FAILED", "BAD", "NG", "REJECT", "REJECTED"}:
        flags.append("source_result")
    for field_name in MEASUREMENT_FIELDS:
        value = getattr(record, field_name)
        if value is None:
            continue
        limit = configuration.limits[field_name]
        if limit.minimum is not None and value < limit.minimum:
            flags.append(field_name)
        elif limit.maximum is not None and value > limit.maximum:
            flags.append(field_name)
    polarity = record.polarity.strip().lower()
    if polarity and any(word in polarity for word in configuration.polarity_fail_words):
        flags.append("polarity")
    if flags:
        return SmtEvaluation("FAIL", tuple(dict.fromkeys(flags)))
    if not record.identity():
        return SmtEvaluation("WARN", ("missing_string",))
    if all(getattr(record, field_name) is None for field_name in MEASUREMENT_FIELDS):
        return SmtEvaluation("WARN", ("missing_measurements",))
    return SmtEvaluation("PASS", ())


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _optional_float(value: Any, default: float | None) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
