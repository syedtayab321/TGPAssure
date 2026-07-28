# Electrical Import Field Guide

TGPAssure maps common header aliases automatically. CSV/TXT/DAT/XYZ/TSV/XLSX/XLSM are supported.

## ERT / four-electrode resistivity

Recommended columns:

`Line, Station, A, B, M, N, Current_mA, Voltage_mV, Apparent_Resistivity, Contact_Resistance, Q_pct, Repeat_ID`

Apparent resistivity can be calculated when valid finite ABMN positions plus resistance/current/voltage are available. If the instrument already exports rho-a, that value is retained.

## VES

`Station, AB/2, MN/2, Rhoa, Current_mA, Voltage_mV, Q, M`

In VES/IP field sheets, a bare `M` without explicit ABMN geometry is interpreted as chargeability. With explicit A/B/N geometry, `M` is treated as the potential electrode.

## TDIP

`Line, Station, A, B, M, N, Rhoa, Chargeability, M1, M2, M3, ..., Current_mA, Voltage_mV, Q_pct`

`M1`, `M2`, etc. are preserved as `window_01`, `window_02`, etc. for decay-window QC.

## FDIP / SIP

`Station, Frequency_Hz, Phase_mrad, Chargeability, Amplitude, Repeat_ID`

`Phase_Deg` is also accepted and converted to milliradians internally.

## Self-Potential

`Line, Station, Easting, Northing, SP_mV, Timestamp, is_base, Repeat_ID`

Set `is_base` to values such as `1`, `true`, `base`, `reference` or `ref` for base/reference readings.

## MALM

`Source_ID, Station, Easting, Northing, Voltage_mV, Repeat_ID`

Source ID is required for MALM QC traceability.

## Equipotential / potential mapping

`Station, Easting, Northing, Voltage_mV, Source_ID(optional), Repeat_ID`

A source ID is useful but not mandatory for generic potential mapping.

## Telluric

Any of these signal fields can be used:

- `Electric_Field_mV_km`
- `Electric_Field_X_mV_km`
- `Electric_Field_Y_mV_km`
- `Voltage_mV`
- `SP_mV`

Recommended supporting fields:

`Timestamp, Station, is_base/reference, Repeat_ID`

## Units

Canonical internal units include:

- current: mA
- voltage/SP: mV
- resistance/contact resistance: ohm
- apparent resistivity: ohm·m
- chargeability: mV/V
- frequency: Hz
- phase: mrad
- electric field: mV/km

Always retain the original field export and survey metadata as the authoritative raw record.

## DJF-10A / DWJ-3B note

DJF-10A is used as the high-power transmitter and DWJ-3B as the measurement/control side in compatible IP/resistivity workflows. TGPAssure can ingest their **exported tabular measurements** when the export contains recognizable fields such as current, primary voltage/potential, apparent resistivity, chargeability/IP, SP, deviation/stacking QC, station/geometry, etc. A native proprietary binary format is intentionally not guessed without an actual sample file or published binary specification; add a dedicated reader once such a sample/specification is available.
