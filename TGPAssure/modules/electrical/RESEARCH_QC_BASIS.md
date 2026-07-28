# Electrical Methods Research and QC Basis

## Scope decision

Electrical geophysics is a broad family. The EPA electrical-method overview distinguishes common surface electrical methods such as electrical resistivity, induced polarization/complex resistivity and self-potential, while also listing telluric currents, magnetotellurics, equipotential, mise-à-la-masse and electromagnetic techniques among the wider family. USGS exploration references likewise separate DC resistivity, electromagnetic, mise-à-la-masse, self-potential and induced polarization.

For TGPAssure, the implementation boundary is:

- **Electrical QC suite:** DC resistivity (ERT/VES/profiling), TDIP, FDIP, SIP/complex resistivity, SP, MALM, equipotential/potential mapping, telluric electric-field workflows.
- **EM suite:** MT/AMT, CSAMT, VLF, FDEM, TDEM and related electromagnetic workflows.

This prevents incompatible physics/QC from being forced into one generic page.

## Research basis used for implementation

Primary/official technical sources reviewed:

1. US EPA, *Electrical Methods* — method-family overview and distinction between resistivity, IP/complex resistivity, SP and wider electrical/EM methods.
   https://www.epa.gov/environmental-geophysics/electrical-methods
2. US EPA, *Electrical Resistivity* — common arrays including Wenner, Schlumberger, reverse-Schlumberger, gradient and dipole-dipole; apparent-resistivity/pseudosection/inversion context.
   https://www.epa.gov/environmental-geophysics/electrical-resistivity
3. US EPA, *Induced Polarization (IP) and Complex Resistivity* — TDIP, FDIP and SIP/complex-resistivity distinctions and frequency/phase concepts.
   https://www.epa.gov/environmental-geophysics/induced-polarization-ip-and-complex-resistivity
4. US EPA, *Self-Potential* — passive natural potential, non-polarizing electrodes, base/roving measurement concepts and drift/reference implications.
   https://www.epa.gov/environmental-geophysics/self-potential
5. IRIS Instruments resistivity/IP field guidance and SYSCAL documentation — ground/contact resistance, stacking/standard-deviation field QC, apparent-resistivity calculation and chargeability acquisition concepts.
   https://www.iris-instruments.com/
6. Guideline Geo / ABEM Terrameter LS/LS2 official manuals/product documentation — RES/IP/SP acquisition capabilities, electrode/contact checks, stacking/protocol concepts and multi-electrode survey workflow.
   https://guidelinegeo.com/products/abem/abem-terrameter-ls-2/
7. U.S. Geological Survey exploration/geophysical-method references — DC resistivity, IP, SP and mise-à-la-masse as established exploration methods.
   https://pubs.usgs.gov/

## QC design principles

### 1. Never invent unavailable raw information

The reader targets documented/exported tabular data. It does not claim to decode proprietary binary formats without a published specification. QC checks run only when the required fields exist and clearly state when a metric cannot be calculated.

### 2. Preserve original measurements

Derived resistance/resistivity, reciprocal error, SP drift-corrected channels and despiked display series are added as new fields. The imported measurement channel is retained.

### 3. Reciprocal error must use actual reciprocal geometry

A duplicate normal reading is not a reciprocal. A valid reciprocal requires the current dipole of one measurement to match the potential dipole of another and vice versa. The implementation pairs only these swapped configurations.

### 4. Apparent pseudosection is not inversion

Pseudo-depth coordinates are for QC/display organization. They are not interpreted as a depth-of-investigation model and are never labeled as an inversion.

### 5. Thresholds are configurable

Field acceptance depends on instrument, array, electrode contact, geology, target, environment and client specifications. Defaults are screening values. For example, IRIS guidance discusses improving ground resistance/current/stacking when standard deviation is high; TGPAssure therefore exposes these thresholds rather than treating a single number as universal.

## Method-specific QC matrix

| Method | Core inputs | Primary QC |
|---|---|---|
| ERT | ABMN + rho-a or current/voltage | geometry, coincidence, contact, current/voltage, stacking, rho-a, true reciprocal error, repeats, array summary |
| VES | AB/2, optionally MN/2 + rho-a | spacing validity/order, overlap/curve continuity, signal/contact/stacking, robust outliers, repeats |
| Resistivity profiling | station/line + rho-a or current/voltage | station consistency, signal/contact/stacking, rho-a, repeats, geometry where present |
| TDIP | chargeability + optional decay windows | sign/range screening, decay-window monotonicity/shape screening, signal/contact/stacking, repeats/reciprocity |
| FDIP | frequency + chargeability/phase | frequency validity/coverage, response consistency, phase units/sign, repeats |
| SIP | multiple frequencies + phase | spectral coverage, phase screening, frequency metadata, repeat/reference consistency |
| SP | SP/potential + base/reference | base/reference count, drift/closure, repeats, electrode/reference stability indicators |
| MALM | potential + energized source/reference + coordinates | source traceability, coordinate completeness, repeats/reference consistency, potential mapping integrity |
| Equipotential | potential + coordinates, optional source/reference | coordinate/map completeness, reference/source traceability when applicable, repeats, continuity/outliers |
| Telluric | electric field/potential + time + reference/repeat when available | timestamp completeness, temporal/reference consistency, signal validity, repeats/reference metadata |

## Numerical inversion boundary

TGPAssure is a QC/assurance application. A production ERT/IP inversion requires a validated forward operator, mesh/topography handling, error model, regularization, constraints, convergence diagnostics, sensitivity/depth-of-investigation assessment and extensive numerical validation. This module therefore delivers **inversion readiness and auditable export**, not a misleading home-made inversion presented as equivalent to specialist packages.
