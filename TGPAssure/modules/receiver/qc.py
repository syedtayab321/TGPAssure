from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean

from .smt_reader import SmtRecord


@dataclass(slots=True)
class ReceiverQcLimits:
    resistance_min: float = 250.0
    resistance_max: float = 650.0
    noise_max: float = 20.0
    distortion_max: float = 0.2
    frequency_min: float = 8.0
    frequency_max: float = 14.0
    damping_min: float = 0.35
    damping_max: float = 0.85
    sensitivity_min: float = 0.0
    impedance_min: float = 0.0
    polarity_fail_words: tuple[str, ...] = ("reverse", "reversed", "bad", "fail", "negative")


@dataclass(slots=True)
class ReceiverQcResult:
    record: SmtRecord
    status: str
    findings: list[str] = field(default_factory=list)

    @property
    def fail_count(self) -> int:
        return sum(1 for f in self.findings if f.startswith("FAIL"))

    @property
    def warn_count(self) -> int:
        return sum(1 for f in self.findings if f.startswith("WARN"))


class ReceiverQcEngine:
    def __init__(self, limits: ReceiverQcLimits | None = None) -> None:
        self.limits = limits or ReceiverQcLimits()

    def evaluate(self, records: list[SmtRecord]) -> list[ReceiverQcResult]:
        return [self._evaluate_one(record) for record in records]

    def _evaluate_one(self, record: SmtRecord) -> ReceiverQcResult:
        l = self.limits
        findings: list[str] = []
        def check_range(label: str, value: float | None, lo: float | None, hi: float | None) -> None:
            if value is None:
                findings.append(f"WARN missing {label}")
                return
            if lo is not None and value < lo:
                findings.append(f"FAIL {label} below limit ({value:g} < {lo:g})")
            if hi is not None and value > hi:
                findings.append(f"FAIL {label} above limit ({value:g} > {hi:g})")
        check_range("resistance", record.resistance, l.resistance_min, l.resistance_max)
        check_range("noise", record.noise, None, l.noise_max)
        check_range("distortion", record.distortion, None, l.distortion_max)
        check_range("frequency", record.frequency, l.frequency_min, l.frequency_max)
        check_range("damping", record.damping, l.damping_min, l.damping_max)
        if record.sensitivity is not None and record.sensitivity < l.sensitivity_min:
            findings.append(f"FAIL sensitivity below limit ({record.sensitivity:g} < {l.sensitivity_min:g})")
        if record.impedance is not None and record.impedance < l.impedance_min:
            findings.append(f"FAIL impedance below limit ({record.impedance:g} < {l.impedance_min:g})")
        if record.polarity and any(word in record.polarity.strip().lower() for word in l.polarity_fail_words):
            findings.append(f"FAIL polarity marked {record.polarity}")
        if any(f.startswith("FAIL") for f in findings):
            status = "FAIL"
        elif any(f.startswith("WARN") for f in findings):
            status = "WARN"
        else:
            status = "PASS"
        return ReceiverQcResult(record=record, status=status, findings=findings)

    @staticmethod
    def summarize(results: list[ReceiverQcResult]) -> dict[str, object]:
        total = len(results)
        passed = sum(1 for r in results if r.status == "PASS")
        warned = sum(1 for r in results if r.status == "WARN")
        failed = sum(1 for r in results if r.status == "FAIL")
        category_counts: dict[str, int] = {}
        for result in results:
            for finding in result.findings:
                key = finding.split(" ", 2)[1] if " " in finding else finding
                category_counts[key] = category_counts.get(key, 0) + 1
        serials = [r.record.serial or r.record.string_id for r in results if r.record.serial or r.record.string_id]
        duplicates = len(serials) - len(set(serials))
        return {
            "total": total,
            "pass": passed,
            "warn": warned,
            "fail": failed,
            "score": round((passed / total) * 100.0, 2) if total else 0.0,
            "duplicates": duplicates,
            "categories": category_counts,
        }
