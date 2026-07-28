from __future__ import annotations

import hashlib
import shutil
import mimetypes
import struct
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass

from core.data_access.project_repository import ProjectRepository
from core.domain.project import ProjectFile


@dataclass
class FormatDescriptor:
    format_id: str
    extension: str
    mime_type: str
    display_name: str
    detected_by: str
    confidence: float


class FileManager:
    def __init__(self, project_repo: ProjectRepository) -> None:
        self._project_repo = project_repo

    def detect_format(self, path: Path) -> FormatDescriptor:
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        
        magic_bytes = self._read_magic_bytes(path)
        extension = path.suffix.lower()
        mime_type_guess, _ = mimetypes.guess_type(str(path))
        
        format_info = self._probe_format(magic_bytes, extension, path)
        
        if format_info:
            return FormatDescriptor(
                format_id=format_info["id"],
                extension=format_info["extension"],
                mime_type=format_info["mime_type"],
                display_name=format_info["display_name"],
                detected_by=format_info["detected_by"],
                confidence=format_info["confidence"]
            )
        
        # A MIME guess is metadata, not proof that TGPAssure supports the
        # corresponding extension. Keep unrecognised application formats
        # explicitly unknown so they cannot be routed into the wrong module.
        if mime_type_guess:
            return FormatDescriptor(
                format_id="unknown",
                extension=extension,
                mime_type="application/octet-stream",
                display_name="Unknown Format",
                detected_by="fallback",
                confidence=0.1
            )

        return FormatDescriptor(
            format_id="unknown",
            extension=extension,
            mime_type="application/octet-stream",
            display_name="Unknown Format",
            detected_by="fallback",
            confidence=0.1
        )

    def import_file(self, path: Path, module_hint: str = "general") -> ProjectFile:
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        
        sha256_hash, size_bytes = self._compute_sha256_streaming(path)
        format_desc = self.detect_format(path)
        file_uuid = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        relative_path = self._generate_relative_path(path, module_hint, format_desc)
        
        project_file = ProjectFile(
            id=None,
            file_uuid=file_uuid,
            module=module_hint,
            file_role="imported",
            original_name=path.name,
            display_name=path.stem,
            relative_path=relative_path,
            extension=format_desc.extension,
            mime_type=format_desc.mime_type,
            size_bytes=size_bytes,
            sha256=sha256_hash,
            status="available",
            metadata_json='{"format_id": "' + format_desc.format_id + '", "detected_by": "' + format_desc.detected_by + '", "confidence": ' + str(format_desc.confidence) + '}',
            imported_at=now,
            last_verified_at=now
        )
        
        return self._project_repo.add_file(project_file)

    def _read_magic_bytes(self, path: Path) -> bytes:
        with open(path, "rb") as f:
            return f.read(32)

    def _compute_sha256_streaming(self, path: Path) -> Tuple[str, int]:
        sha256 = hashlib.sha256()
        size_bytes = 0
        chunk_size = 1024 * 1024
        
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                sha256.update(chunk)
                size_bytes += len(chunk)
        
        return sha256.hexdigest(), size_bytes

    def _probe_format(self, magic_bytes: bytes, extension: str, path: Path) -> Optional[Dict[str, Any]]:
        signatures = {
            b"RIFF": {
                "id": "wav",
                "extension": ".wav",
                "mime_type": "audio/wav",
                "display_name": "WAV Audio",
                "detected_by": "magic"
            },
            b"\x89PNG": {
                "id": "png",
                "extension": ".png",
                "mime_type": "image/png",
                "display_name": "PNG Image",
                "detected_by": "magic"
            },
            b"\xff\xd8\xff": {
                "id": "jpeg",
                "extension": ".jpg",
                "mime_type": "image/jpeg",
                "display_name": "JPEG Image",
                "detected_by": "magic"
            },
            b"GIF8": {
                "id": "gif",
                "extension": ".gif",
                "mime_type": "image/gif",
                "display_name": "GIF Image",
                "detected_by": "magic"
            },
            b"PK": {
                "id": "zip",
                "extension": ".zip",
                "mime_type": "application/zip",
                "display_name": "ZIP Archive",
                "detected_by": "magic"
            },
            b"%PDF": {
                "id": "pdf",
                "extension": ".pdf",
                "mime_type": "application/pdf",
                "display_name": "PDF Document",
                "detected_by": "magic"
            },
        }
        
        for signature, info in signatures.items():
            if magic_bytes.startswith(signature):
                info["confidence"] = 0.95
                return info
        
        extension_map = {
            ".txt": {"id": "text", "extension": ".txt", "mime_type": "text/plain", "display_name": "Text File", "detected_by": "extension", "confidence": 0.5},
            ".csv": {"id": "csv", "extension": ".csv", "mime_type": "text/csv", "display_name": "CSV Data", "detected_by": "extension", "confidence": 0.6},
            ".json": {"id": "json", "extension": ".json", "mime_type": "application/json", "display_name": "JSON Data", "detected_by": "extension", "confidence": 0.6},
            ".xml": {"id": "xml", "extension": ".xml", "mime_type": "application/xml", "display_name": "XML Data", "detected_by": "extension", "confidence": 0.6},
            ".html": {"id": "html", "extension": ".html", "mime_type": "text/html", "display_name": "HTML Document", "detected_by": "extension", "confidence": 0.5},
            ".shp": {"id": "shapefile", "extension": ".shp", "mime_type": "application/x-esri-shapefile", "display_name": "Shapefile", "detected_by": "extension", "confidence": 0.7},
            ".dbf": {"id": "dbf", "extension": ".dbf", "mime_type": "application/x-dbf", "display_name": "DBF Table", "detected_by": "extension", "confidence": 0.5},
            ".prj": {"id": "prj", "extension": ".prj", "mime_type": "text/plain", "display_name": "Projection File", "detected_by": "extension", "confidence": 0.5},
            ".shx": {"id": "shx", "extension": ".shx", "mime_type": "application/x-esri-shapefile-index", "display_name": "Shapefile Index", "detected_by": "extension", "confidence": 0.5},
            ".las": {"id": "las", "extension": ".las", "mime_type": "application/x-las", "display_name": "LiDAR LAS", "detected_by": "extension", "confidence": 0.7},
            ".laz": {"id": "laz", "extension": ".laz", "mime_type": "application/x-las", "display_name": "LiDAR LAZ", "detected_by": "extension", "confidence": 0.7},
            ".tif": {"id": "geotiff", "extension": ".tif", "mime_type": "image/tiff", "display_name": "GeoTIFF", "detected_by": "extension", "confidence": 0.7},
            ".tiff": {"id": "geotiff", "extension": ".tiff", "mime_type": "image/tiff", "display_name": "GeoTIFF", "detected_by": "extension", "confidence": 0.7},
        }
        
        if extension in extension_map:
            info = extension_map[extension]
            info["confidence"] = 0.6
            return info
        
        return None

    def _generate_relative_path(self, path: Path, module_hint: str, format_desc: FormatDescriptor) -> str:
        base_name = path.stem.lower().replace(" ", "_")
        suffix = format_desc.extension if format_desc.extension else path.suffix
        return f"raw/{module_hint}/{base_name}{suffix}"