from __future__ import annotations

from dataclasses import dataclass

from .uphole_reader import UpholeShot


@dataclass(slots=True)
class UpholeLayer:
    top_depth_m: float
    base_depth_m: float
    top_time_ms: float
    base_time_ms: float
    interval_velocity_m_s: float


class UpholeInterpreter:
    @staticmethod
    def interpreted_time(record: UpholeShot) -> float | None:
        return record.corrected_ms if record.corrected_ms is not None else record.pick_ms

    def build_time_depth(self, records: list[UpholeShot]) -> list[UpholeShot]:
        valid = [r for r in records if r.depth_m is not None and self.interpreted_time(r) is not None]
        return sorted(valid, key=lambda r: (float(r.depth_m or 0.0), float(self.interpreted_time(r) or 0.0)))

    def layers(self, records: list[UpholeShot]) -> list[UpholeLayer]:
        td = self.build_time_depth(records)
        layers: list[UpholeLayer] = []
        for top, base in zip(td, td[1:]):
            t1 = self.interpreted_time(top); t2 = self.interpreted_time(base)
            z1 = top.depth_m; z2 = base.depth_m
            if t1 is None or t2 is None or z1 is None or z2 is None:
                continue
            dt_s = (t2 - t1) / 1000.0
            dz = z2 - z1
            if dt_s <= 0 or dz <= 0:
                continue
            layers.append(UpholeLayer(z1, z2, t1, t2, dz / dt_s))
        return layers

    def summary(self, records: list[UpholeShot]) -> dict[str, object]:
        td = self.build_time_depth(records)
        layers = self.layers(records)
        velocities = [l.interval_velocity_m_s for l in layers]
        return {
            "records": len(records),
            "usable_time_depth_points": len(td),
            "layers": len(layers),
            "min_velocity_m_s": round(min(velocities), 2) if velocities else None,
            "max_velocity_m_s": round(max(velocities), 2) if velocities else None,
            "average_velocity_m_s": round(sum(velocities) / len(velocities), 2) if velocities else None,
        }
