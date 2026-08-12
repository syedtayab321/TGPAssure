from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import math
import re
from typing import Iterable


@dataclass(slots=True)
class GeophonePoint:
    x: float
    y: float


@dataclass(slots=True)
class GeophoneArrayModel:
    file_name: str = "Untitled.GAR"
    x_size: float = 25.0
    y_size: float = 25.0
    points: list[GeophonePoint] = field(default_factory=list)

    @property
    def elements(self) -> int:
        return len(self.points)

    @property
    def array_length(self) -> float:
        if not self.points:
            return 0.0
        xs = [p.x for p in self.points]
        ys = [p.y for p in self.points]
        return max(max(xs) - min(xs), max(ys) - min(ys), 1.0)

    def clear(self) -> None:
        self.points.clear()

    def add_point(self, x: float, y: float) -> None:
        x = max(0.0, min(float(self.x_size), float(x)))
        y = max(0.0, min(float(self.y_size), float(y)))
        for p in self.points:
            if abs(p.x - x) < 1e-6 and abs(p.y - y) < 1e-6:
                return
        self.points.append(GeophonePoint(x, y))

    def remove_nearest(self, x: float, y: float, tolerance: float = 1.0) -> bool:
        if not self.points:
            return False
        best_i = -1
        best_d = float("inf")
        for i, p in enumerate(self.points):
            d = math.hypot(p.x - x, p.y - y)
            if d < best_d:
                best_i, best_d = i, d
        if best_i >= 0 and best_d <= tolerance:
            self.points.pop(best_i)
            return True
        return False

    def as_dict(self) -> dict:
        return {"file_name": self.file_name, "x_size": self.x_size, "y_size": self.y_size,
                "points": [[p.x, p.y] for p in self.points]}

    @classmethod
    def from_points(cls, points: Iterable[tuple[float, float]], file_name: str = "Untitled.GAR", x_size: float = 25.0, y_size: float = 25.0) -> "GeophoneArrayModel":
        model = cls(file_name=file_name, x_size=float(x_size), y_size=float(y_size))
        for x, y in points:
            model.add_point(float(x), float(y))
        return model


def _parse_number_pairs(text: str) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";", "//")):
            continue
        nums = re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", line)
        if len(nums) >= 2:
            try:
                pairs.append((float(nums[0]), float(nums[1])))
            except ValueError:
                pass
    return pairs


def load_gar_file(path: str | Path) -> GeophoneArrayModel:
    p = Path(path)
    raw = p.read_text(errors="ignore")
    stripped = raw.strip()
    if stripped.startswith("{"):
        data = json.loads(stripped)
        model = GeophoneArrayModel(
            file_name=str(data.get("file_name") or p.name),
            x_size=float(data.get("x_size") or data.get("x") or 25),
            y_size=float(data.get("y_size") or data.get("y") or 25),
        )
        for item in data.get("points", []):
            if isinstance(item, dict):
                model.add_point(float(item.get("x", 0)), float(item.get("y", 0)))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                model.add_point(float(item[0]), float(item[1]))
        return model
    x_size = y_size = 25.0
    for line in raw.splitlines():
        lower = line.lower()
        nums = re.findall(r"[-+]?\d+(?:\.\d+)?", line)
        if nums and ("x_size" in lower or "x size" in lower or lower.startswith("x=")):
            x_size = float(nums[0])
        if nums and ("y_size" in lower or "y size" in lower or lower.startswith("y=")):
            y_size = float(nums[0])
    pairs = _parse_number_pairs(raw)
    if pairs:
        max_x = max(x for x, _ in pairs)
        max_y = max(y for _, y in pairs)
        x_size = max(x_size, math.ceil(max_x / 5.0) * 5.0 if max_x > x_size else x_size)
        y_size = max(y_size, math.ceil(max_y / 5.0) * 5.0 if max_y > y_size else y_size)
    return GeophoneArrayModel.from_points(pairs, file_name=p.name, x_size=x_size, y_size=y_size)


def save_gar_file(path: str | Path, model: GeophoneArrayModel) -> None:
    p = Path(path)
    data = model.as_dict()
    data["file_name"] = p.name
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
