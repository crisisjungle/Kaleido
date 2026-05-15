"""
Small in-process task executor.

This is not a durable queue. It centralizes the current background-thread
pattern so long-running API handlers share cancellation and failure behavior.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

from ..models.task import TaskCancelledError, TaskManager
from ..utils.logger import get_logger

logger = get_logger("envfish.task_executor")


class TaskExecutor:
    def __init__(self, task_manager: Optional[TaskManager] = None):
        self.task_manager = task_manager or TaskManager()

    def start(
        self,
        *,
        task_id: str,
        target: Callable[[], Any],
        on_success: Optional[Callable[[Any], None]] = None,
        on_cancel: Optional[Callable[[BaseException], None]] = None,
        on_error: Optional[Callable[[BaseException], None]] = None,
        complete_on_return: bool = False,
    ) -> threading.Thread:
        def runner() -> None:
            try:
                result = target()
                if complete_on_return:
                    self.task_manager.complete_task(task_id, result if isinstance(result, dict) else {})
                if on_success:
                    on_success(result)
            except BaseException as exc:
                if isinstance(exc, TaskCancelledError) or self.task_manager.is_cancelled(task_id):
                    self.task_manager.cancel_task(task_id, str(exc) or "用户强制停止")
                    if on_cancel:
                        on_cancel(exc)
                    return

                logger.exception("Background task failed: task_id=%s", task_id)
                self.task_manager.fail_task(task_id, str(exc))
                if on_error:
                    on_error(exc)

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        return thread
