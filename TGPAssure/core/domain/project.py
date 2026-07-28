from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

@dataclass
class ProjectFile:
    id: Optional[int]
    file_uuid: str
    module: str
    file_role: str
    original_name: str
    display_name: str
    relative_path: str
    extension: Optional[str]
    mime_type: Optional[str]
    size_bytes: int
    sha256: Optional[str]
    status: str
    metadata_json: str
    imported_at: datetime
    last_verified_at: Optional[datetime] = None

@dataclass
class Project:
    id: int
    name: str
    root_folder_path: Path
    schema_version: int
    created_at: datetime
    modified_at: datetime
    project_uuid: str
    description: Optional[str] = None
    module: str = "general"
    status: str = "active"
    root_path: Optional[Path] = None
    database_path: Optional[Path] = None
    files: List[ProjectFile] = field(default_factory=list)
    last_opened_at: Optional[datetime] = None