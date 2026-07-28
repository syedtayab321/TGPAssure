from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as PdfImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.data_access.db_engine import DatabaseEngine
from modules.seismic.visualization.models import InterpretationObject, QcTraceFlag, VolumeData
from modules.seismic.visualization.processing import robust_scale


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_suffix(path: str | Path, suffix: str) -> Path:
    output = Path(path).expanduser().resolve()
    if output.suffix.lower() != suffix.lower():
        output = output.with_suffix(suffix)
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def amplitude_to_image(amplitudes: np.ndarray) -> Image.Image:
    data = np.asarray(amplitudes, dtype=np.float32)
    if data.ndim != 2:
        raise ValueError("Image export requires a two-dimensional array")
    scale = robust_scale(data, 99.0)
    normalized = np.clip(data / scale, -1.0, 1.0)
    red = np.where(normalized >= 0, 255, 255 * (1.0 + normalized))
    blue = np.where(normalized <= 0, 255, 255 * (1.0 - normalized))
    green = 255 * (1.0 - np.abs(normalized))
    rgb = np.stack((red, green, blue), axis=-1).astype(np.uint8)
    return Image.fromarray(rgb, mode="RGB")


def export_png(amplitudes: np.ndarray, output_path: str | Path) -> Path:
    output = _ensure_suffix(output_path, ".png")
    amplitude_to_image(amplitudes).save(output, format="PNG", optimize=True)
    return output


def export_geotiff(
    amplitudes: np.ndarray,
    output_path: str | Path,
    x_coordinates: np.ndarray | None = None,
    y_coordinates: np.ndarray | None = None,
    epsg: int = 4326,
) -> Path:
    try:
        import tifffile
    except ImportError as exc:
        raise RuntimeError("GeoTIFF export requires tifffile") from exc
    output = _ensure_suffix(output_path, ".tif")
    image = np.asarray(amplitudes, dtype=np.float32)
    if image.ndim != 2:
        raise ValueError("GeoTIFF export requires a two-dimensional section or time slice")
    x = np.asarray(x_coordinates if x_coordinates is not None else np.arange(image.shape[1]), dtype=np.float64)
    y = np.asarray(y_coordinates if y_coordinates is not None else np.arange(image.shape[0]), dtype=np.float64)
    finite_x = x[np.isfinite(x)]
    finite_y = y[np.isfinite(y)]
    if x.ndim == 2 and x.shape[1] > 1:
        x_steps = np.abs(np.diff(x, axis=1))
    else:
        x_steps = np.abs(np.diff(x.ravel()))
    if y.ndim == 2 and y.shape[0] > 1:
        y_steps = np.abs(np.diff(y, axis=0))
    else:
        y_steps = np.abs(np.diff(y.ravel()))
    x_steps = x_steps[np.isfinite(x_steps) & (x_steps > 0)]
    y_steps = y_steps[np.isfinite(y_steps) & (y_steps > 0)]
    pixel_x = float(np.median(x_steps)) if x_steps.size else 1.0
    pixel_y = float(np.median(y_steps)) if y_steps.size else 1.0
    tie_x = float(np.min(finite_x)) if finite_x.size else 0.0
    tie_y = float(np.max(finite_y)) if finite_y.size else float(image.shape[0])
    if int(epsg) == 4326:
        geo_keys = (1, 1, 0, 2, 1024, 0, 1, 2, 2048, 0, 1, 4326)
    else:
        geo_keys = (1, 1, 0, 2, 1024, 0, 1, 1, 3072, 0, 1, int(epsg))
    extratags = [
        (33550, "d", 3, (pixel_x, pixel_y, 0.0), False),
        (33922, "d", 6, (0.0, 0.0, 0.0, tie_x, tie_y, 0.0), False),
        (34735, "H", len(geo_keys), geo_keys, False),
    ]
    tifffile.imwrite(
        output,
        image,
        dtype=np.float32,
        photometric="minisblack",
        metadata={"axes": "YX", "source": "TGPAssure Seismic Visualization"},
        extratags=extratags,
    )
    return output


def export_kml(
    interpretations: Iterable[InterpretationObject],
    output_path: str | Path,
    document_name: str,
) -> Path:
    output = _ensure_suffix(output_path, ".kml")
    placemarks: list[str] = []
    for interpretation in interpretations:
        if not interpretation.visible or interpretation.kind not in {"horizon", "fault", "well_path"}:
            continue
        coordinates: list[str] = []
        for point in interpretation.points:
            x = point.x if point.x is not None else float(point.trace_index)
            y = point.y if point.y is not None else float(point.time_ms)
            z = -float(point.time_ms)
            coordinates.append(f"{x:.10f},{y:.10f},{z:.3f}")
        if len(coordinates) < 2:
            continue
        color = interpretation.color.lstrip("#")
        if len(color) != 6:
            color = "00E5FF"
        kml_color = f"ff{color[4:6]}{color[2:4]}{color[0:2]}"
        placemarks.append(
            "<Placemark>"
            f"<name>{html.escape(interpretation.name)}</name>"
            f"<description>{html.escape(interpretation.kind.title())} exported by TGPAssure</description>"
            f"<Style><LineStyle><color>{kml_color}</color><width>3</width></LineStyle></Style>"
            "<LineString><altitudeMode>relativeToGround</altitudeMode><coordinates>"
            + " ".join(coordinates)
            + "</coordinates></LineString></Placemark>"
        )
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f"<name>{html.escape(document_name)}</name>"
        + "".join(placemarks)
        + "</Document></kml>"
    )
    output.write_text(content, encoding="utf-8")
    return output


def export_kmz(
    interpretations: Iterable[InterpretationObject],
    output_path: str | Path,
    document_name: str,
) -> Path:
    output = _ensure_suffix(output_path, ".kmz")
    temporary_kml = output.with_suffix(".kml")
    export_kml(interpretations, temporary_kml, document_name)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(temporary_kml, "doc.kml")
    temporary_kml.unlink(missing_ok=True)
    return output


def export_horizons_shapefile(
    interpretations: Iterable[InterpretationObject],
    output_path: str | Path,
    crs_wkt: str | None = None,
) -> list[Path]:
    try:
        import shapefile
    except ImportError as exc:
        raise RuntimeError("Shapefile export requires pyshp") from exc
    requested = Path(output_path).expanduser().resolve()
    base = requested.with_suffix("")
    base.parent.mkdir(parents=True, exist_ok=True)
    writer = shapefile.Writer(str(base), shapeType=shapefile.POLYLINEZ)
    writer.autoBalance = 1
    writer.field("OBJECT_ID", "C", size=40)
    writer.field("NAME", "C", size=80)
    writer.field("KIND", "C", size=16)
    writer.field("POINTS", "N", size=10, decimal=0)
    count = 0
    for interpretation in interpretations:
        if interpretation.kind not in {"horizon", "fault"} or len(interpretation.points) < 2:
            continue
        points = []
        for point in interpretation.points:
            x = float(point.x if point.x is not None else point.trace_index)
            y = float(point.y if point.y is not None else 0.0)
            z = -float(point.time_ms)
            points.append([x, y, z, 0.0])
        writer.linez([points])
        writer.record(interpretation.object_id, interpretation.name, interpretation.kind, len(points))
        count += 1
    writer.close()
    if count == 0:
        for suffix in (".shp", ".shx", ".dbf"):
            base.with_suffix(suffix).unlink(missing_ok=True)
        raise ValueError("No interpreted horizons or faults contain enough points for export")
    if crs_wkt:
        base.with_suffix(".prj").write_text(crs_wkt, encoding="utf-8")
    return [path for path in (base.with_suffix(".shp"), base.with_suffix(".shx"), base.with_suffix(".dbf"), base.with_suffix(".prj")) if path.exists()]


def export_time_slice_animation(
    volume: VolumeData,
    output_path: str | Path,
    frame_count: int = 40,
    duration_ms: int = 120,
) -> Path:
    output = _ensure_suffix(output_path, ".gif")
    total_samples = volume.amplitudes.shape[2]
    positions = np.unique(np.linspace(0, total_samples - 1, min(frame_count, total_samples)).astype(int))
    frames = [amplitude_to_image(volume.amplitudes[:, :, position]).resize((640, 480)) for position in positions]
    if not frames:
        raise ValueError("The seismic volume has no samples to animate")
    frames[0].save(
        output,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=max(20, int(duration_ms)),
        loop=0,
        optimize=True,
    )
    return output


def _image_data_uri(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/gif"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def export_html_report(
    output_path: str | Path,
    source_metadata: dict[str, Any],
    image_paths: dict[str, Path],
    interpretations: Iterable[InterpretationObject],
    qc_flags: Iterable[QcTraceFlag],
) -> Path:
    output = _ensure_suffix(output_path, ".html")
    image_cards: list[str] = []
    image_buttons: list[str] = []
    for index, (title, path) in enumerate(image_paths.items()):
        if not path.exists():
            continue
        safe_title = html.escape(title)
        active = " active" if not image_cards else ""
        image_cards.append(
            f'<article class="image-panel{active}" data-image-index="{index}">'
            f'<h2>{safe_title}</h2><img src="{_image_data_uri(path)}" alt="{safe_title}"></article>'
        )
        image_buttons.append(
            f'<button type="button" class="image-button{active}" data-image-target="{index}">{safe_title}</button>'
        )
    metadata_rows = "".join(
        f"<tr><th>{html.escape(str(key).replace('_', ' ').title())}</th><td>{html.escape(str(value))}</td></tr>"
        for key, value in source_metadata.items()
        if not isinstance(value, (dict, list, tuple))
    )
    interpretation_rows = "".join(
        f'<tr data-search="{html.escape((item.name + " " + item.kind).lower())}">'
        f"<td>{html.escape(item.name)}</td><td>{html.escape(item.kind)}</td><td>{len(item.points)}</td></tr>"
        for item in interpretations
    ) or '<tr><td colspan="3">No interpretations saved</td></tr>'
    flag_rows = "".join(
        f'<tr data-search="{html.escape((str(item.trace_index + 1) + " " + item.severity + " " + item.reason + " " + item.source).lower())}">'
        f"<td>{item.trace_index + 1}</td><td>{html.escape(item.severity)}</td>"
        f"<td>{html.escape(item.reason)}</td><td>{html.escape(item.source)}</td></tr>"
        for item in qc_flags
    ) or '<tr><td colspan="4">No flagged traces</td></tr>'
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TGPAssure Seismic Visualization Report</title>
<style>
:root{{--navy:#0c3558;--blue:#1d6f9e;--ink:#172b3a;--line:#cbd8e3;--paper:#eef3f8}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font-family:Segoe UI,Arial,sans-serif}}
header{{padding:24px 36px;background:linear-gradient(135deg,#082b49,#0f507d);color:white}}
header h1{{margin:0 0 8px}}nav{{position:sticky;top:0;z-index:10;display:flex;gap:8px;padding:10px 24px;background:#fff;border-bottom:1px solid var(--line)}}
nav button,.image-button{{border:1px solid #9fb6c8;background:white;color:var(--ink);border-radius:5px;padding:8px 12px;cursor:pointer}}
nav button.active,.image-button.active{{background:var(--blue);border-color:var(--blue);color:white}}
main{{max-width:1500px;margin:auto;padding:24px}}.report-panel{{display:none}}.report-panel.active{{display:block}}
.card,.image-panel{{background:white;border:1px solid var(--line);border-radius:8px;padding:18px;box-shadow:0 4px 16px rgba(20,45,70,.08);margin-bottom:18px}}
.image-panel{{display:none}}.image-panel.active{{display:block}}img{{width:100%;height:auto;background:#08131d;border-radius:4px}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:8px;border-bottom:1px solid #dbe5ed;text-align:left}}th{{background:#e9f1f7}}
.badge{{display:inline-block;padding:4px 9px;border-radius:12px;background:#2b86b6;color:white;margin-right:8px}}
.toolbar{{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px}}input[type=search]{{width:min(520px,100%);padding:9px;border:1px solid #9fb6c8;border-radius:5px}}
.status{{font-size:13px;color:#4f6575;margin-left:auto;align-self:center}}@media print{{nav,.toolbar{{display:none}}.report-panel{{display:block}}}}
</style>
</head>
<body>
<header><h1>TGPAssure Seismic Visualization Report</h1><span class="badge">2D/3D</span><span class="badge">QC Integrated</span><p>Generated {_utc_now()}</p></header>
<nav aria-label="Report sections">
<button type="button" class="nav-button active" data-panel="overview">Overview</button>
<button type="button" class="nav-button" data-panel="images">Viewports</button>
<button type="button" class="nav-button" data-panel="interpretations">Interpretations</button>
<button type="button" class="nav-button" data-panel="qc">QC Flags</button>
</nav>
<main>
<section id="overview" class="report-panel active"><div class="card"><h2>Source Metadata</h2><table>{metadata_rows}</table></div></section>
<section id="images" class="report-panel"><div class="toolbar">{''.join(image_buttons) or '<span>No viewport images exported</span>'}</div>{''.join(image_cards)}</section>
<section id="interpretations" class="report-panel"><div class="card"><div class="toolbar"><input id="interpretation-filter" type="search" placeholder="Filter interpretations"></div><table id="interpretation-table"><thead><tr><th>Name</th><th>Type</th><th>Points</th></tr></thead><tbody>{interpretation_rows}</tbody></table></div></section>
<section id="qc" class="report-panel"><div class="card"><div class="toolbar"><input id="qc-filter" type="search" placeholder="Filter by trace, severity, reason or source"><span id="qc-count" class="status"></span></div><table id="qc-table"><thead><tr><th>Trace</th><th>Severity</th><th>Reason</th><th>Source</th></tr></thead><tbody>{flag_rows}</tbody></table></div></section>
</main>
<script>
const navButtons=[...document.querySelectorAll('.nav-button')];
navButtons.forEach(button=>button.addEventListener('click',()=>{{
  navButtons.forEach(item=>item.classList.remove('active'));
  document.querySelectorAll('.report-panel').forEach(panel=>panel.classList.remove('active'));
  button.classList.add('active');document.getElementById(button.dataset.panel).classList.add('active');
}}));
const imageButtons=[...document.querySelectorAll('.image-button')];
imageButtons.forEach(button=>button.addEventListener('click',()=>{{
  imageButtons.forEach(item=>item.classList.remove('active'));
  document.querySelectorAll('.image-panel').forEach(panel=>panel.classList.remove('active'));
  button.classList.add('active');
  const panel=document.querySelector(`[data-image-index="${{button.dataset.imageTarget}}"]`);if(panel)panel.classList.add('active');
}}));
function attachFilter(inputId,tableId,countId){{
  const input=document.getElementById(inputId),table=document.getElementById(tableId);if(!input||!table)return;
  const rows=[...table.querySelectorAll('tbody tr')],count=countId?document.getElementById(countId):null;
  const update=()=>{{const query=input.value.trim().toLowerCase();let visible=0;rows.forEach(row=>{{const show=!query||(row.dataset.search||row.innerText.toLowerCase()).includes(query);row.hidden=!show;if(show)visible++;}});if(count)count.textContent=`${{visible}} row(s)`;}};
  input.addEventListener('input',update);update();
}}
attachFilter('interpretation-filter','interpretation-table');attachFilter('qc-filter','qc-table','qc-count');
</script>
</body>
</html>"""
    output.write_text(document, encoding="utf-8")
    return output

def export_pdf_report(
    output_path: str | Path,
    source_metadata: dict[str, Any],
    image_paths: dict[str, Path],
    interpretations: Iterable[InterpretationObject],
    qc_flags: Iterable[QcTraceFlag],
) -> Path:
    output = _ensure_suffix(output_path, ".pdf")
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(
        str(output),
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title="TGPAssure Seismic Visualization Report",
        author="TGPAssure",
    )
    story: list[Any] = [Paragraph("TGPAssure Seismic Visualization Report", styles["Title"]), Spacer(1, 5 * mm)]
    metadata = [[str(key).replace("_", " ").title(), str(value)] for key, value in source_metadata.items() if not isinstance(value, (dict, list, tuple))]
    metadata_table = Table([["Property", "Value"], *metadata], colWidths=[55 * mm, 195 * mm])
    metadata_table.setStyle(_table_style())
    story.extend([metadata_table, Spacer(1, 5 * mm)])
    for title, path in image_paths.items():
        if not path.exists() or path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            continue
        story.append(Paragraph(html.escape(title), styles["Heading2"]))
        story.append(PdfImage(str(path), width=250 * mm, height=125 * mm, kind="proportional"))
        story.append(Spacer(1, 4 * mm))
    interpretation_rows = [[item.name, item.kind, str(len(item.points))] for item in interpretations]
    story.append(Paragraph("Interpretations", styles["Heading2"]))
    table = Table([["Name", "Type", "Points"], *(interpretation_rows or [["None", "", "0"]])])
    table.setStyle(_table_style())
    story.extend([table, Spacer(1, 4 * mm)])
    flag_rows = [[str(item.trace_index + 1), item.severity, item.reason, item.source] for item in qc_flags]
    story.append(Paragraph("QC Trace Flags", styles["Heading2"]))
    flag_table = Table([["Trace", "Severity", "Reason", "Source"], *(flag_rows or [["None", "", "", ""]])], colWidths=[20 * mm, 28 * mm, 170 * mm, 35 * mm])
    flag_table.setStyle(_table_style())
    story.append(flag_table)
    document.build(story)
    return output


def _table_style() -> TableStyle:
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173A5E")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B8C7D3")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F7FA")]),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]
    )


def register_visualization_report(
    database_engine: DatabaseEngine | None,
    output_path: str | Path,
    report_type: str,
    title: str,
    metadata: dict[str, Any] | None = None,
) -> str | None:
    if database_engine is None:
        return None
    path = Path(output_path).expanduser().resolve()
    report_uuid = str(uuid.uuid4())
    digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    connection = database_engine.get_write_connection()
    try:
        connection.execute(
            """
            INSERT INTO reports (
                project_id, report_uuid, report_type, title, format, status,
                file_path, sha256, metadata_json, generated_at, created_at
            ) VALUES (1, ?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?)
            """,
            (
                report_uuid,
                report_type,
                title,
                path.suffix.lower().lstrip("."),
                str(path),
                digest,
                json.dumps(metadata or {}, ensure_ascii=False, separators=(",", ":")),
                _utc_now(),
                _utc_now(),
            ),
        )
        connection.commit()
        return report_uuid
    finally:
        connection.close()
