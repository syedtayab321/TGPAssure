from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable, Optional


ProgressCallback = Callable[[int, str], None]


class UnsafeSharedProjectError(ValueError):
    """Raised when a shared-project archive fails safety validation."""


class CollaborationService:
    """Local project sharing with validated, atomic ZIP import/export.

    This service intentionally remains offline/local: it creates portable project
    archives and imports them safely. It does *not* imply multi-user/cloud sync.
    Archives are scanned for path traversal, symbolic links, excessive expansion,
    and malformed entries before extraction.
    """

    MANIFEST_NAME = "TGPASSURE_SHARE_MANIFEST.json"
    SHARE_FORMAT_VERSION = 1
    DEFAULT_MAX_FILES = 50_000
    DEFAULT_MAX_UNCOMPRESSED_BYTES = 20 * 1024**3  # 20 GiB
    DEFAULT_MAX_SINGLE_FILE_BYTES = 8 * 1024**3  # 8 GiB
    DEFAULT_MAX_COMPRESSION_RATIO = 1_000.0
    _EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache"}

    def __init__(self, app_data_dir: Path) -> None:
        self.app_data_dir = Path(app_data_dir).expanduser().resolve()
        self.shares_dir = self.app_data_dir / "shares"
        self.shares_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_tag(tag: Optional[str]) -> str:
        if not tag:
            return ""
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(tag).strip()).strip("-.")
        return f"-{cleaned[:64]}" if cleaned else ""

    @classmethod
    def _iter_share_files(cls, project_path: Path) -> list[Path]:
        files: list[Path] = []
        for path in project_path.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(project_path)
            if any(part in cls._EXCLUDED_PARTS for part in relative.parts):
                continue
            if path.name.endswith((".pyc", ".pyo", ".part", ".tmp")):
                continue
            files.append(path)
        return sorted(files, key=lambda item: item.relative_to(project_path).as_posix().lower())

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _report(callback: ProgressCallback | None, value: int, message: str) -> None:
        if callback is not None:
            callback(max(0, min(100, int(value))), str(message))

    @staticmethod
    def _check_cancel(cancel_event: threading.Event | None) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Project sharing operation cancelled")

    def share_project(
        self,
        project_path: Path,
        tag: Optional[str] = None,
        *,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Path:
        project_path = Path(project_path).expanduser().resolve()
        if not project_path.is_dir():
            raise FileNotFoundError(project_path)
        project_databases = list(project_path.glob("*.tgp-project"))
        if not project_databases:
            raise ValueError("The selected folder is not a TGPAssure project (no .tgp-project database found)")

        files = self._iter_share_files(project_path)
        total_bytes = sum(path.stat().st_size for path in files) or 1
        tag_part = self._safe_tag(tag)
        out_path = self.shares_dir / f"share-{project_path.name}{tag_part}.zip"
        tmp_path = out_path.with_name(out_path.name + f".{os.getpid()}.part")
        manifest_files: list[dict[str, object]] = []
        processed = 0
        self._report(progress_callback, 0, "Preparing project share")

        try:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                for index, path in enumerate(files, start=1):
                    self._check_cancel(cancel_event)
                    relative = path.relative_to(project_path).as_posix()
                    size = path.stat().st_size
                    archive.write(path, relative)
                    manifest_files.append({
                        "path": relative,
                        "size_bytes": size,
                        "sha256": self._sha256(path),
                    })
                    processed += size
                    self._report(
                        progress_callback,
                        min(95, int(processed * 95 / total_bytes)),
                        f"Archiving {index:,}/{len(files):,}: {relative}",
                    )

                manifest = {
                    "format": "TGPAssure Shared Project",
                    "format_version": self.SHARE_FORMAT_VERSION,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "project_name": project_path.name,
                    "project_database": project_databases[0].name,
                    "file_count": len(manifest_files),
                    "files": manifest_files,
                }
                archive.writestr(self.MANIFEST_NAME, json.dumps(manifest, indent=2))

            self._check_cancel(cancel_event)
            tmp_path.replace(out_path)
            self._report(progress_callback, 100, f"Project share created: {out_path.name}")
            return out_path
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    @classmethod
    def inspect_archive(
        cls,
        archive_path: Path,
        *,
        max_files: int = DEFAULT_MAX_FILES,
        max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
        max_single_file_bytes: int = DEFAULT_MAX_SINGLE_FILE_BYTES,
        max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO,
    ) -> dict[str, object]:
        archive_path = Path(archive_path).expanduser().resolve()
        if not archive_path.is_file():
            raise FileNotFoundError(archive_path)
        if not zipfile.is_zipfile(archive_path):
            raise UnsafeSharedProjectError("The selected file is not a valid ZIP archive")

        with zipfile.ZipFile(archive_path, "r") as archive:
            infos = archive.infolist()
            if len(infos) > max_files:
                raise UnsafeSharedProjectError(f"Archive contains too many entries ({len(infos):,})")
            total = 0
            project_databases: list[str] = []
            for info in infos:
                name = info.filename.replace("\\", "/")
                pure = PurePosixPath(name)
                if pure.is_absolute() or ".." in pure.parts or not name.strip():
                    raise UnsafeSharedProjectError(f"Unsafe archive path: {info.filename!r}")
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise UnsafeSharedProjectError(f"Symbolic links are not allowed in shared projects: {name}")
                if info.file_size > max_single_file_bytes:
                    raise UnsafeSharedProjectError(f"Archive entry is too large: {name}")
                total += int(info.file_size)
                if total > max_uncompressed_bytes:
                    raise UnsafeSharedProjectError("Archive expands beyond the configured safety limit")
                if info.compress_size > 0 and info.file_size / info.compress_size > max_compression_ratio:
                    raise UnsafeSharedProjectError(f"Suspicious compression ratio for archive entry: {name}")
                if pure.suffix.lower() == ".tgp-project":
                    project_databases.append(name)

            if not project_databases:
                raise UnsafeSharedProjectError("Archive does not contain a TGPAssure .tgp-project database")

            manifest = None
            if cls.MANIFEST_NAME in archive.namelist():
                try:
                    manifest = json.loads(archive.read(cls.MANIFEST_NAME).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise UnsafeSharedProjectError("Shared-project manifest is invalid") from exc

        return {
            "entry_count": len(infos),
            "uncompressed_bytes": total,
            "project_databases": project_databases,
            "manifest": manifest,
        }

    def import_shared_project(
        self,
        archive_path: Path,
        dest_folder: Path,
        *,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
        verify_manifest: bool = True,
    ) -> Path:
        archive_path = Path(archive_path).expanduser().resolve()
        dest_folder = Path(dest_folder).expanduser().resolve()
        inspection = self.inspect_archive(archive_path)
        if dest_folder.exists() and any(dest_folder.iterdir()):
            raise FileExistsError(f"Destination folder is not empty: {dest_folder}")
        dest_folder.parent.mkdir(parents=True, exist_ok=True)

        staging = Path(tempfile.mkdtemp(prefix=f".{dest_folder.name}.import-", dir=str(dest_folder.parent)))
        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                files = [info for info in archive.infolist() if not info.is_dir()]
                total_bytes = sum(info.file_size for info in files) or 1
                extracted = 0
                for index, info in enumerate(files, start=1):
                    self._check_cancel(cancel_event)
                    relative = PurePosixPath(info.filename.replace("\\", "/"))
                    target = staging.joinpath(*relative.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info, "r") as source, target.open("wb") as output:
                        while True:
                            self._check_cancel(cancel_event)
                            chunk = source.read(4 * 1024 * 1024)
                            if not chunk:
                                break
                            output.write(chunk)
                            extracted += len(chunk)
                            self._report(
                                progress_callback,
                                min(95, int(extracted * 95 / total_bytes)),
                                f"Extracting {index:,}/{len(files):,}: {info.filename}",
                            )

            if verify_manifest and isinstance(inspection.get("manifest"), dict):
                manifest = inspection["manifest"]
                entries = manifest.get("files", []) if isinstance(manifest, dict) else []
                for index, record in enumerate(entries, start=1):
                    self._check_cancel(cancel_event)
                    if not isinstance(record, dict) or not record.get("path") or not record.get("sha256"):
                        raise UnsafeSharedProjectError("Shared-project manifest contains an invalid file record")
                    relative = PurePosixPath(str(record["path"]))
                    target = staging.joinpath(*relative.parts)
                    if not target.is_file() or target.stat().st_size != int(record.get("size_bytes", -1)):
                        raise UnsafeSharedProjectError(f"Shared-project verification failed for {relative}")
                    if self._sha256(target) != str(record["sha256"]):
                        raise UnsafeSharedProjectError(f"Checksum verification failed for {relative}")
                    self._report(progress_callback, 95 + int(index * 4 / max(1, len(entries))), f"Verifying {relative}")

            self._check_cancel(cancel_event)
            if dest_folder.exists():
                dest_folder.rmdir()  # only empty destinations are allowed above
            staging.replace(dest_folder)
            self._report(progress_callback, 100, f"Shared project imported to {dest_folder}")
            return dest_folder
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
