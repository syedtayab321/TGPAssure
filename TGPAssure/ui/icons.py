from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

try:
    import qtawesome as qta
except ImportError:
    qta = None


@dataclass(frozen=True)
class IconSpec:
    glyph: str
    color: str
    overlay: str | None = None
    overlay_color: str = "#FFFFFF"
    scale: float = 0.84
    overlay_scale: float = 0.40


ICON_SPECS: dict[str, IconSpec] = {
    "document-new": IconSpec("fa6s.file-lines", "#4E8FC8", "fa6s.plus", "#D79A16"),
    "document-open": IconSpec("fa6s.folder-open", "#E3A322"),
    "document-save": IconSpec("fa6s.floppy-disk", "#4B6F94"),
    "document-import": IconSpec("fa6s.file-import", "#2C9A66"),
    "document-export": IconSpec("fa6s.file-export", "#7F5BA7"),
    "document-send": IconSpec("fa6s.paper-plane", "#4B83B8"),
    "document-properties": IconSpec("fa6s.clipboard-list", "#5D7E9D"),
    "edit-copy": IconSpec("fa6s.copy", "#5B8DC0"),
    "edit-paste": IconSpec("fa6s.paste", "#4D9A75"),
    "edit-cut": IconSpec("fa6s.scissors", "#B94B45"),
    "edit-clear": IconSpec("fa6s.eraser", "#BA5549"),
    "edit-undo": IconSpec("fa6s.rotate-left", "#3D86C6"),
    "edit-redo": IconSpec("fa6s.rotate-right", "#D08B2A"),
    "edit-find": IconSpec("fa6s.magnifying-glass", "#457FAF"),
    "edit-replace": IconSpec("fa6s.arrows-rotate", "#2D9270"),
    "delete": IconSpec("fa6s.xmark", "#C44943"),
    "folder": IconSpec("fa6s.folder", "#D9A126"),
    "project-explorer": IconSpec("fa6s.folder-tree", "#3B82A6"),
    "view-refresh": IconSpec("fa6s.arrows-rotate", "#278B9A"),
    "media-playback-start": IconSpec("fa6s.play", "#2C9561"),
    "process-stop": IconSpec("fa6s.stop", "#C44943"),
    "view-dashboard": IconSpec("fa6s.gauge-high", "#3A7FA8"),
    "application-pdf": IconSpec("fa6s.file-pdf", "#C7473B"),
    "x-office-spreadsheet": IconSpec("fa6s.file-excel", "#2E8B57"),
    "view-statistics": IconSpec("fa6s.chart-column", "#7759A6"),
    "view-grid": IconSpec("fa6s.table-cells", "#3A8B99"),
    "view-filter": IconSpec("fa6s.filter", "#C67E2B"),
    "view-list-details": IconSpec("fa6s.list", "#3C8796"),
    "image-x-generic": IconSpec("fa6s.image", "#4E88BE"),
    "color-picker": IconSpec("fa6s.palette", "#A95A94"),
    "color": IconSpec("fa6s.palette", "#A95A94"),
    "weather-clear-night": IconSpec("fa6s.moon", "#5B6FD1"),
    "preferences-system": IconSpec("fa6s.gear", "#66717C"),
    "office-chart-line": IconSpec("fa6s.chart-line", "#B94C49"),
    "office-chart-bar": IconSpec("fa6s.chart-simple", "#7356A4"),
    "appointment-new": IconSpec("fa6s.calendar-plus", "#4C86BA"),
    "list-add": IconSpec("fa6s.list", "#4A8BA3", "fa6s.plus", "#2E9864"),
    "dialog-information": IconSpec("fa6s.circle-info", "#3E82BE"),
    "dialog-warning": IconSpec("fa6s.triangle-exclamation", "#D08A2C"),
    "dialog-ok-apply": IconSpec("fa6s.circle-check", "#2C9561"),
    "document-open-recent": IconSpec("fa6s.clock-rotate-left", "#4B83B8"),
    "draw-line": IconSpec("fa6s.minus", "#4D82B0"),
    "earth": IconSpec("fa6s.globe", "#2D9270"),
    "text-html": IconSpec("fa6s.code", "#5B6FD1"),
    "video-x-generic": IconSpec("fa6s.video", "#8A5AA5"),
    "view-3d": IconSpec("fa6s.cube", "#4C86BA"),
    "view-history": IconSpec("fa6s.clock-rotate-left", "#5D7E9D"),
    "view-list-tree": IconSpec("fa6s.sitemap", "#3C8796"),
    "view-split-left-right": IconSpec("fa6s.table-columns", "#4D6E89"),
    "view-split-top-bottom": IconSpec("fa6s.table-cells-large", "#4D6E89"),
    "utilities-terminal": IconSpec("fa6s.terminal", "#425466"),
    "zoom-fit-best": IconSpec("fa6s.maximize", "#3C80B8"),
    "zoom-in": IconSpec("fa6s.magnifying-glass-plus", "#3B8C68"),
    "zoom-out": IconSpec("fa6s.magnifying-glass-minus", "#B94B45"),
    "zoom-original": IconSpec("fa6s.magnifying-glass", "#7258A4"),
    "map": IconSpec("fa6s.map", "#36936B"),
    "package-x-generic": IconSpec("fa6s.box", "#8A6238"),
    "input-keyboard": IconSpec("fa6s.keyboard", "#68737E"),
    "help-about": IconSpec("fa6s.circle-question", "#3F82BA"),
    "help-contents": IconSpec("fa6s.book-open", "#3F82BA"),
    "go-home": IconSpec("fa6s.house", "#4D8BC2"),
    "home": IconSpec("fa6s.house", "#4D8BC2"),
    "seismic": IconSpec("fa6s.wave-square", "#2C9A63"),
    "electrical": IconSpec("fa6s.bolt", "#D18A24"),
    "electrical-ip": IconSpec("fa6s.wave-square", "#8B5FBF"),
    "electrical-sp": IconSpec("fa6s.plus-minus", "#2F8A76"),
    "seg-d": IconSpec("fa6s.floppy-disk", "#E09B27"),
    "seg-y": IconSpec("fa6s.wave-square", "#8259A8"),
    "seg-2": IconSpec("fa6s.chart-line", "#2D9B91"),
    "seg-b": IconSpec("fa6s.cube", "#C8584D"),
    "ukooa": IconSpec("fa6s.map-location-dot", "#3D9270"),
    "navigation": IconSpec("fa6s.location-arrow", "#D2A11C"),
    "transform-scale": IconSpec("fa6s.expand", "#7658A6"),
    "audio-volume-high": IconSpec("fa6s.volume-high", "#3A8C98"),
    "audio-volume-medium": IconSpec("fa6s.volume-low", "#3A8C98"),
    "audio-volume-muted": IconSpec("fa6s.volume-xmark", "#777F87"),
    "draw-freehand": IconSpec("fa6s.pen", "#C7812E"),
    "measure": IconSpec("fa6s.ruler-horizontal", "#68737D"),
    "transform-move": IconSpec("fa6s.arrows-up-down-left-right", "#4384BC"),
    "window-minimize": IconSpec("fa6s.window-minimize", "#454C54", scale=0.72),
    "window-maximize": IconSpec("fa6.square", "#454C54", scale=0.70),
    "window-close": IconSpec("fa6s.xmark", "#454C54", scale=0.76),
    "window-restore": IconSpec("fa6s.clone", "#454C54", scale=0.70),
    "appearance": IconSpec("fa6s.palette", "#A66093"),
    "more": IconSpec("fa6s.ellipsis", "#4D6E89"),
    "ruler": IconSpec("fa6s.ruler-horizontal", "#6A727A"),
    "grid": IconSpec("fa6s.border-all", "#7A704A"),
    "select": IconSpec("fa6s.arrow-pointer", "#317FB8"),
    "deselect": IconSpec("fa6s.hand-pointer", "#3F78A4"),
    "invert": IconSpec("fa6s.object-group", "#496D89"),
    "pan": IconSpec("fa6s.hand", "#B17A48"),
    "reset-view": IconSpec("fa6s.arrows-up-down-left-right", "#B4534B"),
    "properties": IconSpec("fa6s.clipboard-check", "#4D88B3"),
    "fallback": IconSpec("fa6s.circle", "#4D82B0"),
}

ALIASES: dict[str, str] = {
    "doc_new": "document-new",
    "doc_open": "document-open",
    "doc_save": "document-save",
    "doc_import": "document-import",
    "doc_export": "document-export",
    "copy": "edit-copy",
    "paste": "edit-paste",
    "cut": "edit-cut",
    "clear": "edit-clear",
    "refresh": "view-refresh",
    "play": "media-playback-start",
    "stats": "view-statistics",
    "filter": "view-filter",
    "image": "image-x-generic",
    "gear": "preferences-system",
    "chart_line": "office-chart-line",
    "calendar": "appointment-new",
    "plus": "list-add",
    "info": "dialog-information",
    "warning": "dialog-warning",
    "terminal": "utilities-terminal",
    "zoom_fit": "zoom-fit-best",
    "zoom_in": "zoom-in",
    "zoom_out": "zoom-out",
    "zoom_100": "zoom-original",
    "package": "package-x-generic",
    "keyboard": "input-keyboard",
    "help": "help-about",
    "scale": "transform-scale",
    "volume": "audio-volume-high",
    "pencil": "draw-freehand",
    "move": "transform-move",
    "window_minimize": "window-minimize",
    "window_maximize": "window-maximize",
    "window_close": "window-close",
    "window_restore": "window-restore",
    "segd": "seg-d",
    "segy": "seg-y",
    "seg2": "seg-2",
    "segb": "seg-b",
    "electric": "electrical",
    "resistivity": "electrical",
    "ip": "electrical-ip",
    "sp": "electrical-sp",
}


def _normalize(name: str | None) -> str:
    """Resolve a registered icon name.

    Unknown icon names intentionally resolve to an empty key instead of a
    synthetic placeholder glyph. This prevents broken/misleading ribbon icons
    from being shown while still allowing explicit ``fallback`` use where a
    generic icon is wanted.
    """
    if not name:
        return ""
    key = ALIASES.get(name, name)
    return key if key in ICON_SPECS else ""


def icon_color(name: str | None, fallback: str = "#4D82B0") -> str:
    key = _normalize(name)
    if not key:
        return fallback
    return ICON_SPECS.get(key, ICON_SPECS["fallback"]).color or fallback


def _fallback_pixmap(key: str, color: str, size: int, scale: int) -> QPixmap:
    physical = max(1, size * scale)
    pixmap = QPixmap(physical, physical)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    inset = max(1, int(physical * 0.12))
    rect = QRect(inset, inset, physical - 2 * inset, physical - 2 * inset)
    painter.setPen(QPen(QColor(color).darker(120), max(1, scale)))
    painter.setBrush(QColor(color))
    painter.drawRoundedRect(rect, physical * 0.16, physical * 0.16)
    painter.setPen(QColor("#FFFFFF"))
    font = painter.font()
    font.setBold(True)
    font.setPixelSize(max(8, int(physical * 0.42)))
    painter.setFont(font)
    painter.drawText(rect, Qt.AlignCenter, key[:1].upper())
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return pixmap


@lru_cache(maxsize=1024)
def _render_icon(key: str, color: str, size: int, scale: int) -> QPixmap:
    spec = ICON_SPECS.get(key, ICON_SPECS["fallback"])
    if qta is None:
        return _fallback_pixmap(key, color, size, scale)

    physical = max(1, size * scale)
    pixmap = QPixmap(physical, physical)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    base_size = max(1, int(physical * spec.scale))
    base_x = (physical - base_size) // 2
    base_y = (physical - base_size) // 2
    base_icon = qta.icon(spec.glyph, color=color)
    painter.drawPixmap(base_x, base_y, base_icon.pixmap(QSize(base_size, base_size)))

    if spec.overlay:
        overlay_size = max(6, int(physical * spec.overlay_scale))
        overlay_x = physical - overlay_size
        overlay_y = physical - overlay_size
        halo = max(1, int(physical * 0.035))
        halo_rect = QRect(
            overlay_x - halo,
            overlay_y - halo,
            overlay_size + 2 * halo,
            overlay_size + 2 * halo,
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(halo_rect)
        overlay_icon = qta.icon(spec.overlay, color=spec.overlay_color)
        painter.drawPixmap(
            overlay_x,
            overlay_y,
            overlay_icon.pixmap(QSize(overlay_size, overlay_size)),
        )

    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return pixmap


def get_icon(name: str | None, color: str | None = None, size: int = 18) -> QIcon:
    key = _normalize(name)
    if not key:
        return QIcon()
    resolved_color = color or ICON_SPECS[key].color
    icon = QIcon()
    for scale in (1, 2):
        icon.addPixmap(_render_icon(key, resolved_color, max(8, int(size)), scale))
    return icon


def icon_for_extension(extension: str, color: str | None = None, size: int = 16) -> QIcon:
    ext = (extension or "").lower().lstrip(".")
    mapping = {
        "sgy": "seg-y",
        "segy": "seg-y",
        "sgd": "seg-d",
        "segd": "seg-d",
        "seg2": "seg-2",
        "segb": "seg-b",
        "csv": "view-list-details",
        "xlsx": "view-grid",
        "xls": "view-grid",
        "pdf": "document-export",
        "txt": "document-new",
    }
    return get_icon(mapping.get(ext, "document-new"), color=color, size=size)
