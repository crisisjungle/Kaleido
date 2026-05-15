import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from ..utils.atomic_file import read_json_file, write_json_file


class TaskCancelledError(Exception):
    pass


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    task_id: str
    name: str
    status: TaskStatus = TaskStatus.PENDING
    message: str = ""
    progress: int = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    progress_detail: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    task_type: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value if isinstance(self.status, TaskStatus) else self.status
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        payload = dict(data or {})
        payload["status"] = TaskStatus(payload.get("status", TaskStatus.PENDING))
        return cls(**{key: payload.get(key) for key in cls.__dataclass_fields__.keys()})


class TaskManager:
    TASKS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../uploads/tasks"))

    def __init__(self):
        os.makedirs(self.TASKS_DIR, exist_ok=True)

    def _path(self, task_id: str) -> str:
        return os.path.join(self.TASKS_DIR, f"{task_id}.json")

    def create_task(self, name: str, metadata: Dict[str, Any] | None = None, task_type: str = "") -> str:
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        task = Task(task_id=task_id, name=name, metadata=metadata or {}, task_type=task_type)
        self._save(task)
        return task_id

    def _save(self, task: Task) -> None:
        task.updated_at = datetime.now().isoformat()
        write_json_file(self._path(task.task_id), task.to_dict())

    def get_task(self, task_id: str) -> Optional[Task]:
        path = self._path(task_id)
        if not os.path.exists(path):
            return None
        data = read_json_file(path, default=None)
        return Task.from_dict(data) if data else None

    def update_task(self, task_id: str, status: TaskStatus | None = None, message: str | None = None, progress: int | None = None, result: Dict[str, Any] | None = None, error: str | None = None, **extra) -> Optional[Task]:
        task = self.get_task(task_id)
        if not task:
            return None
        if status is not None:
            task.status = status
        if message is not None:
            task.message = message
        if progress is not None:
            task.progress = progress
        if result is not None:
            task.result = result
        if error is not None:
            task.error = error
        for key, value in extra.items():
            if hasattr(task, key):
                setattr(task, key, value)
        self._save(task)
        return task

    def complete_task(
        self,
        task_id: str,
        result: Dict[str, Any] | None = None,
        message: str = "任务完成",
    ) -> Optional[Task]:
        return self.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message=message,
            result=result or {},
            error="",
        )

    def fail_task(self, task_id: str, error: str, message: str | None = None) -> Optional[Task]:
        return self.update_task(
            task_id,
            status=TaskStatus.FAILED,
            message=message or f"任务失败: {error}",
            error=error,
        )

    def cancel_task(self, task_id: str, reason: str = "用户强制停止") -> Optional[Task]:
        return self.update_task(
            task_id,
            status=TaskStatus.CANCELLED,
            message=reason,
            error=reason,
        )

    def list_tasks(self) -> List[Dict[str, Any]]:
        tasks = []
        for filename in os.listdir(self.TASKS_DIR):
            if not filename.endswith(".json"):
                continue
            task = self.get_task(filename[:-5])
            if task:
                tasks.append(task.to_dict())
        tasks.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
        return tasks

    def is_cancelled(self, task_id: str) -> bool:
        task = self.get_task(task_id)
        return bool(task and task.status == TaskStatus.CANCELLED)

    def ensure_not_cancelled(self, task_id: str) -> None:
        if self.is_cancelled(task_id):
            raise TaskCancelledError("用户强制停止")

    def cancel_active_tasks(self, reason: str = "用户强制停止") -> List[Dict[str, Any]]:
        cancelled = []
        for item in self.list_tasks():
            if item.get("status") in {TaskStatus.PENDING.value, TaskStatus.PROCESSING.value}:
                task = self.cancel_task(item["task_id"], reason=reason)
                if task:
                    cancelled.append(task.to_dict())
        return cancelled

    def fail_active_tasks(self, reason: str = "服务重启后任务已中断，请重新提交") -> List[Dict[str, Any]]:
        failed = []
        for item in self.list_tasks():
            if item.get("status") in {TaskStatus.PENDING.value, TaskStatus.PROCESSING.value}:
                task = self.update_task(
                    item["task_id"],
                    status=TaskStatus.FAILED,
                    message=reason,
                    error=reason,
                )
                if task:
                    failed.append(task.to_dict())
        return failed
