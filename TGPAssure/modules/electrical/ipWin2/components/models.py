from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class VesRow:
    ab2: float = math.nan
    mn: float = math.nan
    sp: float = math.nan
    voltage: float = math.nan
    current: float = math.nan
    k: float = math.nan
    rhoa: float = math.nan


@dataclass
class ModelLayer:
    rho: float
    h: float


def parse_float(value: Any) -> float:
    try:
        if value is None:
            return math.nan
        text = str(value).strip().replace("Ω", "").replace("ohm", "").replace("--", "")
        if text in {"-", "+"}:
            return math.nan
        if text.lower() in {"", "nan", "none", "?"}:
            return math.nan
        return float(text)
    except Exception:
        return math.nan


def display_value(value: Any) -> str:
    try:
        v = float(value)
        if not np.isfinite(v):
            return ""
        if abs(v) >= 1000 or (0 < abs(v) < 0.01):
            return f"{v:.4g}"
        return f"{v:.3f}".rstrip("0").rstrip(".")
    except Exception:
        return str(value) if value is not None else ""


def complete_row(row: VesRow, array_type: str = "Schlumberger") -> VesRow:
    if not np.isfinite(row.mn) or row.mn <= 0:
        row.mn = 1.0
    if not np.isfinite(row.k) and np.isfinite(row.ab2):
        ab2 = row.ab2
        mn = max(row.mn, 1e-9)
        atype = (array_type or "").lower()
        if "wenner" in atype:
            row.k = 2.0 * math.pi * max(ab2, 1e-9)
        elif "pole" in atype:
            row.k = 2.0 * math.pi * max(ab2 * ab2 - (mn * 0.5) ** 2, 1e-9) / mn
        else:
            row.k = math.pi * max(ab2 * ab2 - (mn * 0.5) ** 2, 1e-9) / mn
    if (
        not np.isfinite(row.rhoa)
        and np.isfinite(row.voltage)
        and np.isfinite(row.current)
        and abs(row.current) > 1e-12
        and np.isfinite(row.k)
    ):
        row.rhoa = abs(row.k * row.voltage / row.current)
    return row
