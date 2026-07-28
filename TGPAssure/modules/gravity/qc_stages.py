from __future__ import annotations

import json
import time
from typing import Any

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.gravity.constants import (
    COMPLETE_BOUGUER_ANOMALY, FREE_AIR_CORRECTION, NORMAL_GRAVITY, RAW_GRAVITY,
    SIMPLE_BOUGUER_ANOMALY, TERRAIN_CORRECTION, TIDE_CORRECTION,
)
from modules.gravity.context import GravityQcContext
from modules.gravity.gravity_processing_engine import GravityProcessingEngine
from modules.gravity.models import GravityStageOutcome


def _finding(rule: str, message: str, severity: QCSeverity = QCSeverity.WARNING, action: str | None = None, **metadata: Any) -> QCFinding:
    return QCFinding(rule, severity, message, suggested_action=action, metadata_json=json.dumps(metadata, default=str))


def _status(findings: list[QCFinding]) -> QCStatus:
    if any(f.severity in {QCSeverity.ERROR, QCSeverity.CRITICAL} for f in findings):
        return QCStatus.FAIL
    if findings:
        return QCStatus.WARN
    return QCStatus.PASS


class _Stage:
    key = "stage"
    name = "Stage"

    def run(self, context: GravityQcContext) -> GravityStageOutcome:
        started = time.perf_counter()
        try:
            metrics, findings, message = self.evaluate(context)
            status = _status(findings)
        except Exception as exc:
            metrics, findings, message = {}, [_finding(f"{self.key}_error", str(exc), QCSeverity.ERROR)], f"Stage failed: {exc}"
            status = QCStatus.FAIL
        return GravityStageOutcome(self.key, self.name, status, metrics, findings, message, int((time.perf_counter() - started) * 1000))

    def evaluate(self, context: GravityQcContext) -> tuple[dict[str, Any], list[QCFinding], str]:
        raise NotImplementedError


class FileIntegrityQC(_Stage):
    key, name = "file_integrity", "File Integrity"
    def evaluate(self, c):
        d = c.observations; f=[]
        if d.record_count == 0: f.append(_finding("empty", "No gravity observations were loaded", QCSeverity.CRITICAL))
        finite = int(np.count_nonzero(np.isfinite(d.channel(RAW_GRAVITY))))
        if finite != d.record_count: f.append(_finding("gravity_missing", f"{d.record_count-finite} gravity readings are non-numeric", QCSeverity.ERROR))
        return {"records": d.record_count, "finite_gravity": finite, "checksum": d.checksum}, f, "Source integrity checked"

class SchemaUnitsQC(_Stage):
    key, name = "schema_units", "Schema and Units"
    def evaluate(self,c):
        d=c.observations; f=[]
        if RAW_GRAVITY not in d.channels: f.append(_finding("raw_missing", "Observed gravity channel is missing", QCSeverity.CRITICAL))
        med=float(np.nanmedian(d.channel(RAW_GRAVITY)))
        if not 900000 <= abs(med) <= 1100000: f.append(_finding("unit_suspect", f"Median gravity {med:.3f} is outside the usual absolute-gravity mGal range; verify units/datum"))
        return {"gravity_units":d.gravity_units,"median_observed_mgal":med,"channels":list(d.channel_names)},f,"Schema and units reviewed"

class MetadataQC(_Stage):
    key, name = "metadata", "Survey Metadata"
    def evaluate(self,c):
        d=c.observations; f=[]
        if not d.crs: f.append(_finding("crs_missing","Coordinate reference system is not defined"))
        if not np.any(d.station_id.astype(str) != ""): f.append(_finding("station_ids_missing","Station identifiers are absent"))
        return {"crs":d.crs,"station_count":d.station_count,"line_count":d.line_count},f,"Metadata inventory completed"

class TimeClockQC(_Stage):
    key, name = "time_clock", "Time and Clock"
    def evaluate(self,c):
        t=c.observations.timestamps.astype("datetime64[ms]").astype("int64"); f=[]
        dt=np.diff(t)/60000.0 if t.size>1 else np.array([])
        nonmono=int(np.count_nonzero(dt<0)); maxgap=float(np.max(dt)) if dt.size else 0.0
        if nonmono: f.append(_finding("time_order",f"{nonmono} timestamp reversals detected",QCSeverity.ERROR))
        if maxgap>c.thresholds.get("timestamp_gap_warn_min",30): f.append(_finding("time_gap",f"Maximum timestamp gap is {maxgap:.1f} min"))
        return {"non_monotonic":nonmono,"max_gap_min":maxgap},f,"Timestamp continuity checked"

class CoordinatesElevationQC(_Stage):
    key, name = "coordinates_elevation", "Coordinates and Elevation"
    def evaluate(self,c):
        d=c.observations; f=[]; valid=d.valid_coordinate_mask(); elev=np.asarray(d.elevation,float)
        if np.count_nonzero(valid)<d.record_count: f.append(_finding("coord_missing",f"{d.record_count-np.count_nonzero(valid)} observations lack valid coordinates",QCSeverity.ERROR))
        if np.count_nonzero(np.isfinite(elev))<d.record_count: f.append(_finding("elev_missing","Some elevations are missing",QCSeverity.ERROR))
        jumps=np.abs(np.diff(elev[np.isfinite(elev)])) if np.count_nonzero(np.isfinite(elev))>1 else np.array([])
        maxjump=float(np.max(jumps)) if jumps.size else 0.0
        if maxjump>c.thresholds.get("elevation_jump_warn_m",15): f.append(_finding("elev_jump",f"Maximum consecutive elevation change is {maxjump:.1f} m; verify topography/station order"))
        return {"valid_coordinates":int(np.count_nonzero(valid)),"elevation_min_m":float(np.nanmin(elev)),"elevation_max_m":float(np.nanmax(elev)),"max_elevation_jump_m":maxjump},f,"Coordinate and elevation QC complete"

class BaseDriftQC(_Stage):
    key, name = "base_drift", "Base Station and Drift"
    def evaluate(self,c):
        f=[]
        if c.base is None:
            f.append(_finding("base_missing","No base-station file is loaded; drift correction will default to zero",QCSeverity.WARNING,"Load base ties for production-grade reduction"))
            return {"base_loaded":False},f,"Base station not supplied"
        g=c.base.channel(RAW_GRAVITY); t=c.base.timestamps.astype("datetime64[ms]").astype("int64")/3_600_000.0
        duration=float(t[-1]-t[0]) if t.size>1 else 0.0; drift=float((g[-1]-g[0])/duration) if duration>0 else 0.0
        if abs(drift)>c.thresholds.get("base_drift_warn_mgal_hr",.1): f.append(_finding("base_drift",f"Base drift rate {drift:.4f} mGal/hr exceeds profile threshold"))
        return {"base_loaded":True,"record_count":c.base.record_count,"drift_rate_mgal_hr":drift,"range_mgal":float(np.nanmax(g)-np.nanmin(g))},f,"Base drift assessed"

class TidalQC(_Stage):
    key, name = "tidal", "Tidal Correction"
    def evaluate(self,c):
        f=[]; available=TIDE_CORRECTION in c.observations.channels
        if not available: f.append(_finding("tide_missing","No Earth-tide correction column is present; zero correction will be used"))
        vals=c.observations.channels.get(TIDE_CORRECTION,np.zeros(c.observations.record_count))
        return {"available":available,"min_mgal":float(np.nanmin(vals)),"max_mgal":float(np.nanmax(vals))},f,"Tidal correction availability checked"

class RepeatabilityQC(_Stage):
    key, name = "repeatability", "Repeat Stations"
    def evaluate(self,c):
        d=c.observations; groups={}; f=[]
        for s in np.unique(d.station_id.astype(str)):
            idx=np.flatnonzero(d.station_id.astype(str)==s)
            if s and idx.size>1:
                vals=d.channel(RAW_GRAVITY)[idx]; groups[s]={"station_id":s,"sample_count":int(idx.size),"mean_mgal":float(np.nanmean(vals)),"std_mgal":float(np.nanstd(vals)),"range_mgal":float(np.nanmax(vals)-np.nanmin(vals))}
        c.repeat_statistics=list(groups.values())
        rms=float(np.sqrt(np.nanmean([v["std_mgal"]**2 for v in groups.values()]))) if groups else 0.0
        if groups and rms>c.thresholds.get("repeat_rms_warn_mgal",.1): f.append(_finding("repeat_rms",f"Repeat-station RMS {rms:.4f} mGal exceeds threshold"))
        if not groups: f.append(_finding("repeat_absent","No repeat stations were identified; repeatability cannot be quantified"))
        return {"repeat_groups":len(groups),"repeat_rms_mgal":rms,"records":c.repeat_statistics},f,"Repeatability evaluated"

class LoopClosureQC(_Stage):
    key, name = "loop_closure", "Loop Closure"
    def evaluate(self,c):
        d=c.observations; f=[]; loops=[]
        for line in np.unique(d.line_id.astype(str)):
            idx=np.flatnonzero(d.line_id.astype(str)==line)
            if line and idx.size>=2:
                closure=float(d.channel(RAW_GRAVITY)[idx[-1]]-d.channel(RAW_GRAVITY)[idx[0]])
                loops.append({"loop_id":line,"closure_mgal":closure,"sample_count":int(idx.size)})
        c.loop_closures=loops
        maxc=max((abs(v["closure_mgal"]) for v in loops),default=0.0)
        if maxc>c.thresholds.get("loop_closure_warn_mgal",.15): f.append(_finding("loop_closure",f"Maximum raw loop closure is {maxc:.4f} mGal; review drift/network adjustment"))
        return {"loop_count":len(loops),"max_abs_closure_mgal":maxc,"records":loops},f,"Loop closure reviewed"

class LatitudeNormalGravityQC(_Stage):
    key, name = "latitude_normal_gravity", "Latitude / Normal Gravity"
    def evaluate(self,c):
        lat=c.observations.latitude; f=[]
        if not np.any(np.isfinite(lat)): return {},[_finding("latitude_missing","Latitude is required for normal gravity",QCSeverity.CRITICAL)],"Latitude unavailable"
        normal=GravityProcessingEngine.normal_gravity_1980(lat)
        c.observations.add_derived_channel(NORMAL_GRAVITY,normal,parent_channel=None,operation="igf_1980_normal_gravity",overwrite=NORMAL_GRAVITY in c.observations.channels)
        return {"normal_gravity_min_mgal":float(np.nanmin(normal)),"normal_gravity_max_mgal":float(np.nanmax(normal))},f,"Normal gravity calculated"

class FreeAirQC(_Stage):
    key, name = "free_air", "Free-Air Correction"
    def evaluate(self,c):
        elev=c.observations.elevation; corr=.3086*elev
        c.observations.add_derived_channel(FREE_AIR_CORRECTION,corr,parent_channel=None,operation="free_air_correction",overwrite=FREE_AIR_CORRECTION in c.observations.channels)
        return {"min_mgal":float(np.nanmin(corr)),"max_mgal":float(np.nanmax(corr))},[],"Free-air correction calculated"

class BouguerTerrainQC(_Stage):
    key, name = "bouguer_terrain", "Bouguer and Terrain Corrections"
    def evaluate(self,c):
        f=[]; terrain=c.observations.channels.get(TERRAIN_CORRECTION)
        if terrain is None: f.append(_finding("terrain_missing","Terrain correction is not present; complete Bouguer anomaly currently equals simple Bouguer anomaly"))
        GravityProcessingEngine().run_standard_reduction(c.observations,base=c.base,density_g_cm3=c.density_g_cm3)
        return {"density_g_cm3":c.density_g_cm3,"terrain_available":terrain is not None,"simple_bouguer_min":float(np.nanmin(c.observations.channel(SIMPLE_BOUGUER_ANOMALY))),"simple_bouguer_max":float(np.nanmax(c.observations.channel(SIMPLE_BOUGUER_ANOMALY)))},f,"Standard reduction chain calculated"

class CrossoversQC(_Stage):
    key, name = "crossovers", "Cross-Over Consistency"
    def evaluate(self,c):
        # Conservative station-name based cross-over check: repeated station IDs across distinct lines.
        d=c.observations; rec=[]; f=[]; anomaly=d.channels.get(COMPLETE_BOUGUER_ANOMALY,d.channel(RAW_GRAVITY))
        for station in np.unique(d.station_id.astype(str)):
            idx=np.flatnonzero(d.station_id.astype(str)==station)
            lines={str(d.line_id[i]) for i in idx if str(d.line_id[i])}
            if station and idx.size>1 and len(lines)>1:
                err=float(np.nanmax(anomaly[idx])-np.nanmin(anomaly[idx])); rec.append({"station_id":station,"line_count":len(lines),"error_mgal":err})
        c.crossovers=rec; maxerr=max((r["error_mgal"] for r in rec),default=0.0)
        if maxerr>c.thresholds.get("crossover_warn_mgal",.15): f.append(_finding("crossover",f"Maximum cross-over spread is {maxerr:.4f} mGal"))
        return {"crossover_count":len(rec),"max_error_mgal":maxerr,"records":rec},f,"Cross-over consistency evaluated"

class ReductionAuditQC(_Stage):
    key, name = "reduction_audit", "Reduction Audit"
    def evaluate(self,c):
        required=[RAW_GRAVITY,NORMAL_GRAVITY,FREE_AIR_CORRECTION,SIMPLE_BOUGUER_ANOMALY,COMPLETE_BOUGUER_ANOMALY]; missing=[x for x in required if x not in c.observations.channels]; f=[]
        if missing: f.append(_finding("reduction_missing",f"Missing reduction channels: {', '.join(missing)}",QCSeverity.ERROR))
        return {"required_channels":required,"missing_channels":missing,"provenance":[p.as_dict() for p in c.observations.provenance]},f,"Reduction provenance audited"

class FinalAnomalyQC(_Stage):
    key, name = "final_anomaly", "Final Anomaly Consistency"
    def evaluate(self,c):
        values=c.observations.channel(COMPLETE_BOUGUER_ANOMALY); finite=values[np.isfinite(values)]; f=[]
        if finite.size<3: f.append(_finding("anomaly_sparse","Too few valid final anomaly values",QCSeverity.ERROR)); return {"valid":int(finite.size)},f,"Final anomaly insufficient"
        med=float(np.nanmedian(finite)); mad=float(np.nanmedian(np.abs(finite-med))); z=np.abs(finite-med)/max(1.4826*mad,1e-9); out=int(np.count_nonzero(z>c.thresholds.get("anomaly_mad_z_warn",6)))
        if out: f.append(_finding("anomaly_outliers",f"{out} robust outliers detected in final Bouguer anomaly"))
        return {"valid":int(finite.size),"min_mgal":float(np.min(finite)),"max_mgal":float(np.max(finite)),"mean_mgal":float(np.mean(finite)),"std_mgal":float(np.std(finite)),"robust_outliers":out},f,"Final Bouguer anomaly reviewed"

class SummaryQC(_Stage):
    key, name = "summary", "Final Gravity Summary"
    def evaluate(self,c):
        previous=list(c.stage_outcomes.values()); fail=sum(s.status==QCStatus.FAIL for s in previous); warn=sum(s.status==QCStatus.WARN for s in previous)
        findings=[]
        if fail: findings.append(_finding("summary_fail",f"{fail} gravity QC stages failed",QCSeverity.ERROR,"Resolve failed stages before accepting the dataset"))
        elif warn: findings.append(_finding("summary_warn",f"{warn} gravity QC stages contain warnings",QCSeverity.WARNING,"Review warnings before final acceptance"))
        return {"failed_stages":fail,"warning_stages":warn,"completed_stages":len(previous)},findings,"Gravity QC summary complete"
