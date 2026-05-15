import os
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from werkzeug.utils import secure_filename

from ..utils.atomic_file import read_json_file, read_text_file, write_json_file, write_text_file


class ProjectStatus(str, Enum):
    CREATED = "created"
    ONTOLOGY_GENERATED = "ontology_generated"
    GRAPH_BUILDING = "graph_building"
    GRAPH_COMPLETED = "graph_completed"
    FAILED = "failed"


@dataclass
class Project:
    project_id: str
    name: str = ""
    status: ProjectStatus = ProjectStatus.CREATED
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    simulation_requirement: str = ""
    files: List[Dict[str, Any]] = field(default_factory=list)
    total_text_length: int = 0
    ontology: Optional[Dict[str, Any]] = None
    analysis_summary: str = ""
    graph_id: Optional[str] = None
    graph_build_task_id: Optional[str] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value if isinstance(self.status, ProjectStatus) else self.status
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        payload = dict(data or {})
        payload["status"] = ProjectStatus(payload.get("status", ProjectStatus.CREATED))
        return cls(**{key: payload.get(key) for key in cls.__dataclass_fields__.keys()})


class ProjectManager:
    PROJECTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../uploads/projects"))

    @classmethod
    def _get_project_dir(cls, project_id: str) -> str:
        return os.path.join(cls.PROJECTS_DIR, project_id)

    @classmethod
    def _get_project_files_dir(cls, project_id: str) -> str:
        return os.path.join(cls._get_project_dir(project_id), "files")

    @classmethod
    def _get_project_path(cls, project_id: str) -> str:
        return os.path.join(cls._get_project_dir(project_id), "project.json")

    @classmethod
    def create_project(cls, name: str = "") -> Project:
        os.makedirs(cls.PROJECTS_DIR, exist_ok=True)
        project = Project(project_id=f"proj_{uuid.uuid4().hex[:12]}", name=name or "Untitled Project")
        cls.save_project(project)
        return project

    @classmethod
    def save_project(cls, project: Project) -> None:
        os.makedirs(cls._get_project_dir(project.project_id), exist_ok=True)
        project.updated_at = datetime.now().isoformat()
        write_json_file(cls._get_project_path(project.project_id), project.to_dict())

    @classmethod
    def get_project(cls, project_id: str) -> Optional[Project]:
        path = cls._get_project_path(project_id)
        if not os.path.exists(path):
            return None
        try:
            data = read_json_file(path, default=None)
            return Project.from_dict(data) if data else None
        except Exception:
            return None

    @classmethod
    def list_projects(cls, limit: int = 50) -> List[Project]:
        if not os.path.exists(cls.PROJECTS_DIR):
            return []
        projects = []
        for name in os.listdir(cls.PROJECTS_DIR):
            project = cls.get_project(name)
            if project:
                projects.append(project)
        projects.sort(key=lambda item: item.updated_at or item.created_at, reverse=True)
        return projects[:limit]

    @classmethod
    def delete_project(cls, project_id: str) -> bool:
        path = cls._get_project_dir(project_id)
        if not os.path.exists(path):
            return False
        shutil.rmtree(path)
        return True

    @classmethod
    def save_file_to_project(cls, project_id: str, file_obj, filename: str) -> Dict[str, Any]:
        files_dir = cls._get_project_files_dir(project_id)
        os.makedirs(files_dir, exist_ok=True)
        safe_name = secure_filename(filename) or f"upload_{uuid.uuid4().hex[:8]}"
        path = os.path.join(files_dir, safe_name)
        file_obj.save(path)
        return {
            "path": path,
            "filename": safe_name,
            "original_filename": filename,
            "size": os.path.getsize(path),
        }

    @classmethod
    def save_extracted_text(cls, project_id: str, text: str) -> None:
        os.makedirs(cls._get_project_dir(project_id), exist_ok=True)
        write_text_file(os.path.join(cls._get_project_dir(project_id), "extracted_text.txt"), text or "")

    @classmethod
    def get_extracted_text(cls, project_id: str) -> str:
        path = os.path.join(cls._get_project_dir(project_id), "extracted_text.txt")
        return read_text_file(path, default="")
