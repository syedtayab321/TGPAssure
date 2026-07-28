from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from core.data_access.db_engine import DatabaseEngine
from core.domain.project import Project, ProjectFile

class ProjectRepository:
    def __init__(self, db_engine: DatabaseEngine) -> None:
        self._db_engine = db_engine

    def create(self, project: Project) -> Project:
        conn = self._db_engine.get_write_connection()
        try:
            conn.execute(
                "INSERT INTO project (id, project_uuid, name, description, module, status, "
                "root_path, database_path, schema_version, created_at, updated_at, last_opened_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    1,
                    project.project_uuid,
                    project.name,
                    project.description,
                    project.module,
                    project.status,
                    str(project.root_folder_path),
                    str(project.database_path) if project.database_path else None,
                    project.schema_version,
                    project.created_at.isoformat(),
                    project.modified_at.isoformat(),
                    project.last_opened_at.isoformat() if project.last_opened_at else None
                )
            )
            conn.commit()
            return project
        finally:
            conn.close()

    def get_by_id(self, project_id: int = 1) -> Optional[Project]:
        conn = self._db_engine.get_read_connection()
        try:
            row = conn.execute(
                "SELECT id, project_uuid, name, description, module, status, "
                "root_path, database_path, schema_version, created_at, updated_at, last_opened_at "
                "FROM project WHERE id = ?",
                (project_id,)
            ).fetchone()
            if row is None:
                return None
            return Project(
                id=row["id"],
                project_uuid=row["project_uuid"],
                name=row["name"],
                description=row["description"],
                module=row["module"],
                status=row["status"],
                root_folder_path=Path(row["root_path"]) if row["root_path"] else Path.cwd(),
                database_path=Path(row["database_path"]) if row["database_path"] else None,
                schema_version=row["schema_version"],
                created_at=datetime.fromisoformat(row["created_at"]),
                modified_at=datetime.fromisoformat(row["updated_at"]),
                last_opened_at=datetime.fromisoformat(row["last_opened_at"]) if row["last_opened_at"] else None
            )
        finally:
            conn.close()

    def update(self, project: Project) -> Project:
        conn = self._db_engine.get_write_connection()
        try:
            conn.execute(
                "UPDATE project SET name = ?, description = ?, module = ?, status = ?, "
                "root_path = ?, database_path = ?, schema_version = ?, updated_at = ?, last_opened_at = ? "
                "WHERE id = ?",
                (
                    project.name,
                    project.description,
                    project.module,
                    project.status,
                    str(project.root_folder_path),
                    str(project.database_path) if project.database_path else None,
                    project.schema_version,
                    project.modified_at.isoformat(),
                    project.last_opened_at.isoformat() if project.last_opened_at else None,
                    project.id
                )
            )
            conn.commit()
            return project
        finally:
            conn.close()

    def list_files(self, project_id: int = 1) -> List[ProjectFile]:
        conn = self._db_engine.get_read_connection()
        try:
            rows = conn.execute(
                "SELECT id, file_uuid, module, file_role, original_name, display_name, "
                "relative_path, extension, mime_type, size_bytes, sha256, status, "
                "metadata_json, imported_at, last_verified_at "
                "FROM project_files WHERE project_id = ? ORDER BY original_name",
                (project_id,)
            ).fetchall()
            files = []
            for row in rows:
                files.append(ProjectFile(
                    id=row["id"],
                    file_uuid=row["file_uuid"],
                    module=row["module"],
                    file_role=row["file_role"],
                    original_name=row["original_name"],
                    display_name=row["display_name"],
                    relative_path=row["relative_path"],
                    extension=row["extension"],
                    mime_type=row["mime_type"],
                    size_bytes=row["size_bytes"],
                    sha256=row["sha256"],
                    status=row["status"],
                    metadata_json=row["metadata_json"],
                    imported_at=datetime.fromisoformat(row["imported_at"]),
                    last_verified_at=datetime.fromisoformat(row["last_verified_at"]) if row["last_verified_at"] else None
                ))
            return files
        finally:
            conn.close()

    def add_file(self, project_file: ProjectFile, project_id: int = 1) -> ProjectFile:
        conn = self._db_engine.get_write_connection()
        try:
            cursor = conn.execute(
                "INSERT INTO project_files (project_id, file_uuid, module, file_role, "
                "original_name, display_name, relative_path, extension, mime_type, "
                "size_bytes, sha256, status, metadata_json, imported_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    project_file.file_uuid,
                    project_file.module,
                    project_file.file_role,
                    project_file.original_name,
                    project_file.display_name,
                    project_file.relative_path,
                    project_file.extension,
                    project_file.mime_type,
                    project_file.size_bytes,
                    project_file.sha256,
                    project_file.status,
                    project_file.metadata_json,
                    project_file.imported_at.isoformat()
                )
            )
            conn.commit()
            project_file.id = cursor.lastrowid
            return project_file
        finally:
            conn.close()

    def get_file_by_uuid(self, file_uuid: str) -> Optional[ProjectFile]:
        conn = self._db_engine.get_read_connection()
        try:
            row = conn.execute(
                "SELECT id, file_uuid, module, file_role, original_name, display_name, "
                "relative_path, extension, mime_type, size_bytes, sha256, status, "
                "metadata_json, imported_at, last_verified_at "
                "FROM project_files WHERE file_uuid = ?",
                (file_uuid,)
            ).fetchone()
            if row is None:
                return None
            return ProjectFile(
                id=row["id"],
                file_uuid=row["file_uuid"],
                module=row["module"],
                file_role=row["file_role"],
                original_name=row["original_name"],
                display_name=row["display_name"],
                relative_path=row["relative_path"],
                extension=row["extension"],
                mime_type=row["mime_type"],
                size_bytes=row["size_bytes"],
                sha256=row["sha256"],
                status=row["status"],
                metadata_json=row["metadata_json"],
                imported_at=datetime.fromisoformat(row["imported_at"]),
                last_verified_at=datetime.fromisoformat(row["last_verified_at"]) if row["last_verified_at"] else None
            )
        finally:
            conn.close()

    def update_file(self, project_file: ProjectFile) -> ProjectFile:
        conn = self._db_engine.get_write_connection()
        try:
            conn.execute(
                "UPDATE project_files SET module = ?, file_role = ?, display_name = ?, "
                "status = ?, metadata_json = ?, last_verified_at = ? "
                "WHERE file_uuid = ?",
                (
                    project_file.module,
                    project_file.file_role,
                    project_file.display_name,
                    project_file.status,
                    project_file.metadata_json,
                    project_file.last_verified_at.isoformat() if project_file.last_verified_at else None,
                    project_file.file_uuid
                )
            )
            conn.commit()
            return project_file
        finally:
            conn.close()

    def delete_file(self, file_uuid: str) -> bool:
        conn = self._db_engine.get_write_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM project_files WHERE file_uuid = ?",
                (file_uuid,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()