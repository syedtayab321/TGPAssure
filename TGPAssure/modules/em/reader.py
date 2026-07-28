from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any, Iterable


class EmReader:
    """Robust delimited EM/MT impedance reader with conservative schema aliases."""

    _ALIASES = {
        "frequency_hz": {"frequency_hz", "frequency", "freq_hz", "freq", "hz"},
        "impedance_real": {"impedance_real", "z_real", "zreal", "real", "re_z"},
        "impedance_imag": {"impedance_imag", "z_imag", "zimag", "imag", "im_z", "imaginary"},
    }

    def inspect(self, path: str | Path) -> dict[str, Any]:
        source = Path(path).expanduser().resolve()
        if not source.is_file():
            return {"is_em_candidate": False, "reason": "File does not exist"}
        try:
            with source.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream:
                sample = stream.read(16_384)
            dialect = self._sniff(sample)
            reader = csv.DictReader(sample.splitlines(), dialect=dialect)
            mapping = self._map_headers(reader.fieldnames or [])
            missing = sorted(set(self._ALIASES) - set(mapping))
            return {
                "is_em_candidate": not missing,
                "missing_fields": missing,
                "column_mapping": mapping,
                "delimiter": dialect.delimiter,
            }
        except Exception as exc:
            return {"is_em_candidate": False, "reason": str(exc)}

    def read(self, path: str | Path) -> list[dict[str, Any]]:
        source = Path(path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        with source.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream:
            sample = stream.read(16_384)
            stream.seek(0)
            dialect = self._sniff(sample)
            reader = csv.DictReader(stream, dialect=dialect)
            mapping = self._map_headers(reader.fieldnames or [])
            missing = sorted(set(self._ALIASES) - set(mapping))
            if missing:
                raise ValueError(f"EM input is missing required fields: {', '.join(missing)}")
            rows: list[dict[str, Any]] = []
            for line_number, raw in enumerate(reader, start=2):
                if not raw or not any(str(v or "").strip() for v in raw.values()):
                    continue
                row = dict(raw)
                try:
                    for canonical, source_name in mapping.items():
                        value = float(str(raw.get(source_name, "")).strip())
                        if not math.isfinite(value):
                            raise ValueError(f"{canonical} is not finite")
                        row[canonical] = value
                    if row["frequency_hz"] <= 0:
                        raise ValueError("frequency_hz must be greater than zero")
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Invalid EM record at line {line_number}: {exc}") from exc
                rows.append(row)
        if not rows:
            raise ValueError("EM input contains no data records")
        return rows

    @classmethod
    def _map_headers(cls, headers: Iterable[str]) -> dict[str, str]:
        normalized = {str(header).strip().lower().replace(" ", "_"): str(header) for header in headers if header}
        mapping: dict[str, str] = {}
        for canonical, aliases in cls._ALIASES.items():
            for alias in aliases:
                if alias in normalized:
                    mapping[canonical] = normalized[alias]
                    break
        return mapping

    @staticmethod
    def _sniff(sample: str):
        try:
            return csv.Sniffer().sniff(sample, delimiters=",\t;|")
        except csv.Error:
            return csv.excel
