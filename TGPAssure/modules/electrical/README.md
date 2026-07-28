# TGPAssure Electrical Geophysics Module

This package adds a first-class Electrical QC workspace to TGPAssure. It is designed for acquisition QC, method-specific screening, auditable processing, visualization, QC-history persistence, and report/export generation.

## Supported electrical workflows

1. **Electrical Resistivity Tomography (ERT)** — 2D/3D multi-electrode apparent-resistivity acquisition QC.
2. **Vertical Electrical Sounding (VES)** — AB/2 and MN/2 sounding-curve QC.
3. **DC Resistivity Profiling** — lateral profiling/traverse QC.
4. **Time-Domain Induced Polarization (TDIP)** — apparent chargeability and decay-window QC.
5. **Frequency-Domain Induced Polarization (FDIP)** — frequency-dependent chargeability/phase QC.
6. **Spectral IP / Complex Resistivity (SIP)** — multi-frequency phase/spectral-coverage QC.
7. **Self-Potential (SP)** — passive potential, base/reference drift and closure QC.
8. **Mise-à-la-Masse (MALM)** — energized-source/potential mapping QC.
9. **Equipotential / Potential Mapping** — potential-map coordinate/reference/source QC without forcing MALM source metadata.
10. **Telluric Electric-Field Method** — passive time-dependent electric-field/potential QC.

MT, CSAMT, VLF, FDEM and TDEM are intentionally kept in the electromagnetic domain/module because their acquisition physics, time/frequency processing, transfer functions and QC requirements differ materially from the galvanic/potential workflows above.

## End-to-end workflow

1. **Open data** — CSV, TSV, TXT, DAT, XYZ, XLSX or XLSM instrument/export tables.
2. **Schema mapping** — common headers are mapped to canonical electrical fields; ambiguous `M` is resolved contextually as electrode M or chargeability.
3. **Method selection** — auto-detect or explicitly select ERT, VES, profiling, TDIP, FDIP, SIP, SP, MALM, Equipotential or Telluric.
4. **Derive standard fields** — resistance, four-electrode geometric factor, apparent resistivity (when input fields permit), pseudo-position/depth display coordinates, common array classification and true normal-reciprocal error.
5. **File/schema QC** — record integrity, required method fields and column consistency.
6. **Geometry QC** — ABMN validity/coincidence, AB/2 validity, geometric-factor sanity and array summary.
7. **Signal/acquisition QC** — injected current, receiver voltage, contact/ground resistance and stacking/deviation screening when available.
8. **Resistivity QC** — finite/positive apparent resistivity, missing values and robust log-domain MAD outliers.
9. **Reciprocity/repeat QC** — genuine swapped-dipole reciprocal pairs only; duplicate normal readings are not mislabeled as reciprocals. Repeat-group spread is calculated when IDs are available.
10. **Method-specific QC** — VES curve continuity/order; TDIP chargeability/decay windows; FDIP/SIP frequency/phase; SP base drift/closure; MALM source traceability; Equipotential mapping coordinates/reference; Telluric timestamps/reference consistency.
11. **Visual review** — apparent pseudosections, profiles/curves, spectral plots and QC distributions. Apparent pseudosections are explicitly labeled as displays, not inversions.
12. **Auditable processing** — SP drift correction and despiked display series preserve the original imported channel.
13. **QC history** — runs, stages, metrics and findings are persisted through the common TGPAssure QC-history repository.
14. **Export/report** — CSV plus PDF/XLSX reports with stage/status/severity charts, reciprocal screening, array distribution, method-specific frequency/decay coverage and detailed metrics.
15. **Inversion readiness** — export reviewed/QC-ready data for a validated inversion package; this module does not pretend an apparent pseudosection is a subsurface inversion.

## QC threshold policy

The defaults in `constants.py` are **screening defaults**, not universal geological acceptance criteria. Contact resistance, stacking deviation, reciprocal error, minimum signal, SP closure and IP/phase limits must be adjusted for instrument, array, geology, target, noise conditions and client specification.

## Main package files

- `constants.py` — methods, labels, aliases and configurable default thresholds.
- `models.py` — dataset, stage, finding and QC-result models.
- `reader.py` — tabular import, header mapping, method inference and unit normalization.
- `processing.py` — derived electrical fields, geometry/array diagnostics, reciprocal pairing, despiking and SP drift correction.
- `qc_engine.py` — shared + method-specific staged QC engine.
- `reporting.py` — PDF/XLSX report-model construction and graphs.
- `history.py` — centralized QC-history persistence.
- `ui/electrical_dashboard.py` — asynchronous Electrical workspace and visualization.
- `ui/ribbon/electrical_ribbon.py` (project UI package) — Electrical ribbon actions.

See `RESEARCH_QC_BASIS.md` for technical basis and `templates/IMPORT_FIELD_GUIDE.md` for import schemas.
