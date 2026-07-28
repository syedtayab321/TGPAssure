from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any

from core.domain.qc_engine import QCStage, QCStageResult, QCStatus, QCSeverity, QCFinding
from core.data_access.project_repository import ProjectRepository
from core.domain.project import ProjectFile


class UploadStage(QCStage):
    def __init__(self, project_repo: ProjectRepository, module_hint: str = "seismic") -> None:
        self.project_repo = project_repo
        self.module_hint = module_hint

    def run(self, context: Dict[str, Any]) -> QCStageResult:
        findings = []
        file_path = context.get("file_path")
        if file_path is None:
            return QCStageResult(
                stage_name="Upload",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": "No file path provided in context"}),
                findings=[
                    QCFinding(
                        rule_id="upload_no_file",
                        severity=QCSeverity.CRITICAL,
                        message="No file path provided in context",
                        suggested_action="Ensure file_path is set in context"
                    )
                ]
            )

        path = Path(file_path)
        if not path.exists():
            return QCStageResult(
                stage_name="Upload",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": f"File not found: {file_path}"}),
                findings=[
                    QCFinding(
                        rule_id="upload_file_not_found",
                        severity=QCSeverity.CRITICAL,
                        message=f"File not found: {file_path}",
                        suggested_action="Check that the file exists"
                    )
                ]
            )

        try:
            sha256_hash, size_bytes = self._compute_sha256_streaming(path)
            file_uuid = str(uuid.uuid4())
            now = datetime.now(timezone.utc)

            project_file = ProjectFile(
                id=None,
                file_uuid=file_uuid,
                module=self.module_hint,
                file_role="imported",
                original_name=path.name,
                display_name=path.stem,
                relative_path=f"raw/{self.module_hint}/{path.name}",
                extension=path.suffix,
                mime_type="application/octet-stream",
                size_bytes=size_bytes,
                sha256=sha256_hash,
                status="available",
                metadata_json=json.dumps({
                    "uploaded_at": now.isoformat(),
                    "source_path": str(path)
                }),
                imported_at=now,
                last_verified_at=now
            )

            saved_file = self.project_repo.add_file(project_file)
            context["file_uuid"] = saved_file.file_uuid
            context["file_id"] = saved_file.id

            return QCStageResult(
                stage_name="Upload",
                status=QCStatus.PASS,
                summary_json=json.dumps({
                    "file_uuid": saved_file.file_uuid,
                    "file_id": saved_file.id,
                    "original_name": saved_file.original_name,
                    "size_bytes": saved_file.size_bytes,
                    "sha256": saved_file.sha256
                })
            )

        except Exception as e:
            return QCStageResult(
                stage_name="Upload",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": str(e)}),
                findings=[
                    QCFinding(
                        rule_id="upload_failed",
                        severity=QCSeverity.ERROR,
                        message=f"Upload failed: {str(e)}",
                        suggested_action="Check file permissions and disk space"
                    )
                ]
            )

    def _compute_sha256_streaming(self, path: Path) -> tuple[str, int]:
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