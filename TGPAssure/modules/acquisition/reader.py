from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


class AcquisitionReader:
    """Delimited acquisition-log reader with aliases and line-specific errors."""

    _ALIASES = {
        "timestamp": {"timestamp", "time", "datetime", "date_time", "utc_time"},
        "instrument_id": {"instrument_id", "instrument", "device_id", "unit_id", "serial"},
        "status": {"status", "state", "health", "instrument_status"},
    }

    def inspect(self, path: str | Path) -> dict[str, Any]:
        source = Path(path).expanduser().resolve()
        if not source.is_file(): return {"is_acquisition_candidate": False, "reason": "File does not exist"}
        try:
            with source.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream: sample = stream.read(16_384)
            dialect = self._sniff(sample); reader = csv.DictReader(sample.splitlines(), dialect=dialect)
            mapping = self._map_headers(reader.fieldnames or []); missing = sorted(set(self._ALIASES)-set(mapping))
            return {"is_acquisition_candidate": not missing, "missing_fields": missing, "column_mapping": mapping, "delimiter": dialect.delimiter}
        except Exception as exc: return {"is_acquisition_candidate": False, "reason": str(exc)}

    def read(self, path: str | Path) -> list[dict[str, Any]]:
        source = Path(path).expanduser().resolve()
        if not source.is_file(): raise FileNotFoundError(source)
        with source.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream:
            sample=stream.read(16_384); stream.seek(0); dialect=self._sniff(sample); reader=csv.DictReader(stream,dialect=dialect)
            mapping=self._map_headers(reader.fieldnames or []); missing=sorted(set(self._ALIASES)-set(mapping))
            if missing: raise ValueError(f"Acquisition input is missing required fields: {', '.join(missing)}")
            rows=[]
            for line_number, raw in enumerate(reader,start=2):
                if not raw or not any(str(v or '').strip() for v in raw.values()): continue
                try:
                    timestamp=self._parse_timestamp(str(raw.get(mapping['timestamp'],'')).strip())
                    instrument=str(raw.get(mapping['instrument_id'],'')).strip(); status=str(raw.get(mapping['status'],'')).strip()
                    if not instrument: raise ValueError("instrument_id is empty")
                    if not status: raise ValueError("status is empty")
                except ValueError as exc: raise ValueError(f"Invalid acquisition record at line {line_number}: {exc}") from exc
                rows.append({**raw,"timestamp":timestamp,"instrument_id":instrument,"status":status})
        if not rows: raise ValueError("Acquisition input contains no data records")
        return rows

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        if not value: raise ValueError("timestamp is empty")
        normalized=value.replace("Z","+00:00")
        try: return datetime.fromisoformat(normalized)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S","%Y/%m/%d %H:%M:%S","%d/%m/%Y %H:%M:%S"):
                try: return datetime.strptime(value,fmt)
                except ValueError: continue
        raise ValueError(f"unsupported timestamp '{value}'")

    @classmethod
    def _map_headers(cls, headers: Iterable[str]) -> dict[str,str]:
        normalized={str(h).strip().lower().replace(' ','_'):str(h) for h in headers if h}; out={}
        for canonical,aliases in cls._ALIASES.items():
            for alias in aliases:
                if alias in normalized: out[canonical]=normalized[alias]; break
        return out

    @staticmethod
    def _sniff(sample: str):
        try: return csv.Sniffer().sniff(sample,delimiters=",\t;|")
        except csv.Error: return csv.excel
