from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from modules.collaboration.collaboration_service import CollaborationService, UnsafeSharedProjectError


def _project(root: Path) -> Path:
    project = root / "Demo"
    (project / "raw" / "seismic").mkdir(parents=True)
    (project / "Demo.tgp-project").write_bytes(b"sqlite-placeholder")
    (project / "raw" / "seismic" / "line.sgy").write_bytes(b"1234567890")
    return project


def test_share_and_import_round_trip(tmp_path: Path) -> None:
    service = CollaborationService(tmp_path / "app")
    source = _project(tmp_path / "source")
    progress: list[int] = []
    archive = service.share_project(source, "review", progress_callback=lambda value, _message: progress.append(value))
    assert archive.is_file()
    inspection = service.inspect_archive(archive)
    assert inspection["project_databases"]
    assert isinstance(inspection["manifest"], dict)

    destination = tmp_path / "imported"
    result = service.import_shared_project(archive, destination)
    assert result == destination
    assert (destination / "Demo.tgp-project").is_file()
    assert (destination / "raw" / "seismic" / "line.sgy").read_bytes() == b"1234567890"
    assert progress and progress[-1] == 100


def test_import_rejects_path_traversal(tmp_path: Path) -> None:
    service = CollaborationService(tmp_path / "app")
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Demo.tgp-project", b"db")
        zf.writestr("../escape.txt", b"unsafe")
    with pytest.raises(UnsafeSharedProjectError):
        service.import_shared_project(archive, tmp_path / "destination")
    assert not (tmp_path / "escape.txt").exists()
