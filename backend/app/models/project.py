import os
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from werkzeug.utils import secure_filename

from ..utils.atomic_file import read_json_file, read_text_file, write_json_file, write_text_file


ONTOLOGY_DISPLAY_NAMES = {
    "Actor": "行动者",
    "Region": "区域",
    "Resource": "资源",
    "Institution": "制度/机构",
    "Infrastructure": "基础设施",
    "Process": "过程",
    "EcologicalReceptor": "生态受体",
    "EnvironmentalCarrier": "环境载体",
    "HumanActor": "人群主体",
    "GovernmentActor": "治理主体",
    "OrganizationActor": "组织主体",
    "Risk": "风险",
    "Threshold": "阈值",
    "AFFECTS": "影响",
    "LOCATED_IN": "位于",
    "TRANSMITS_TO": "向下游传导",
    "COMPETES_FOR": "竞争资源",
    "DEPENDS_ON": "依赖",
    "REGULATES": "调控",
    "EXPOSES": "暴露",
    "AMPLIFIES": "放大",
    "MITIGATES": "缓解",
    "TRIGGERS": "触发",
    "located_in": "位于",
    "depends_on": "依赖",
    "affects": "影响",
    "regulates": "调控",
    "uses": "使用",
    "location": "位置",
    "scene_type": "场景类型",
    "source_kind": "来源类型",
    "jurisdiction": "管辖范围",
    "service_scope": "服务范围",
}


ONTOLOGY_DESCRIPTION_ZH = {
    "A geographic analysis region or bounded area.": "地理分析区域或有边界的场景范围。",
    "A habitat or ecological receptor inferred from map-first analysis.": "从地图优先分析中识别出的栖息地或生态受体。",
    "A water, air, shoreline, or transport carrier relevant to spread.": "与扩散相关的水体、空气、岸线或交通载体。",
    "A facility or built asset in the local environment.": "本地环境中的设施或建成资产。",
    "A spatially anchored human proxy group.": "带有空间锚点的人群代理主体。",
    "A governing or regulatory actor inferred from map context.": "从地图上下文推断出的治理或监管主体。",
    "A maintenance or operator proxy inferred from facilities.": "从设施和服务上下文推断出的维护、运营或协作组织。",
    "Region description": "区域位置说明",
    "Auto-classified scene type": "自动判定的场景类型",
    "Primary ecological location": "主要生态位置",
    "Primary environmental location": "主要环境位置",
    "Facility location": "设施所在位置",
    "Anchor location": "主体的空间锚点",
    "Administrative scope": "行政或治理覆盖范围",
    "Service scope": "组织服务或维护覆盖范围",
    "observed/detected/inferred": "观测、检测或推断来源",
    "The source lies within the target region.": "源节点位于目标区域内。",
    "The source depends on the target.": "源节点依赖目标节点提供支撑。",
    "The source can affect the target.": "源节点可能对目标节点产生影响。",
    "The source regulates or governs the target.": "源节点对目标节点具有治理、监管或调控作用。",
    "The source uses the target.": "源节点使用目标节点提供的设施或服务。",
}


def _ontology_display_name(name: Any) -> str:
    text = str(name or "").strip()
    if not text:
        return ""
    return ONTOLOGY_DISPLAY_NAMES.get(text) or ONTOLOGY_DISPLAY_NAMES.get(text.upper()) or ""


def _has_cjk(value: Any) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in str(value or ""))


def _ontology_description_zh(description: Any) -> str:
    text = str(description or "").strip()
    return ONTOLOGY_DESCRIPTION_ZH.get(text, text)


def _localize_ontology(ontology: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(ontology, dict):
        return ontology

    localized = dict(ontology)
    for group_key in ("entity_types", "edge_types"):
        items = localized.get(group_key)
        if not isinstance(items, list):
            continue
        normalized_items = []
        for raw_item in items:
            if not isinstance(raw_item, dict):
                normalized_items.append(raw_item)
                continue
            item = dict(raw_item)
            display_name = _ontology_display_name(item.get("name"))
            if display_name:
                item["display_name"] = display_name
            elif item.get("display_name") and not _has_cjk(item.get("display_name")):
                item.pop("display_name", None)
            if "description" in item:
                item["description"] = _ontology_description_zh(item.get("description"))
            if isinstance(item.get("attributes"), list):
                attrs = []
                for raw_attr in item["attributes"]:
                    if not isinstance(raw_attr, dict):
                        attrs.append(raw_attr)
                        continue
                    attr = dict(raw_attr)
                    attr_display_name = _ontology_display_name(attr.get("name"))
                    if attr_display_name:
                        attr["display_name"] = attr_display_name
                    elif attr.get("display_name") and not _has_cjk(attr.get("display_name")):
                        attr.pop("display_name", None)
                    if "description" in attr:
                        attr["description"] = _ontology_description_zh(attr.get("description"))
                    attrs.append(attr)
                item["attributes"] = attrs
            normalized_items.append(item)
        localized[group_key] = normalized_items
    return localized


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
    effort_snapshot: Dict[str, Any] = field(default_factory=dict)
    map_seed_id: Optional[str] = None
    scene_id: Optional[str] = None
    semantic_artifact_ref: Dict[str, Any] = field(default_factory=dict)
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
        payload["ontology"] = _localize_ontology(payload.get("ontology"))
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
    def create_project(
        cls,
        name: str = "",
        *,
        effort_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Project:
        os.makedirs(cls.PROJECTS_DIR, exist_ok=True)
        project = Project(
            project_id=f"proj_{uuid.uuid4().hex[:12]}",
            name=name or "Untitled Project",
            effort_snapshot=dict(effort_snapshot or {}),
        )
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
