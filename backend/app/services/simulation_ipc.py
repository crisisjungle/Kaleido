import os
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List


class CommandType(str, Enum):
    INTERVIEW = "interview"
    BATCH_INTERVIEW = "batch_interview"
    CLOSE_ENV = "close_env"
    INJECT_VARIABLE = "inject_variable"


class IPCStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IPCResponse:
    status: IPCStatus
    result: Any = None
    error: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class IPCCommand:
    command_id: str
    command_type: CommandType
    args: Dict[str, Any] = field(default_factory=dict)


class SimulationIPCClient:
    def __init__(self, sim_dir: str):
        self.sim_dir = sim_dir
        self.ipc_dir = os.path.join(sim_dir, "ipc")
        self.commands_dir = os.path.join(self.ipc_dir, "commands")
        self.responses_dir = os.path.join(self.ipc_dir, "responses")

    def check_env_alive(self) -> bool:
        status_file = os.path.join(self.sim_dir, "env_status.json")
        if not os.path.exists(status_file):
            return False
        try:
            with open(status_file, "r", encoding="utf-8") as handle:
                status = json.load(handle)
            if status.get("status") != "alive":
                return False
            process_pid = status.get("process_pid")
            if process_pid:
                try:
                    os.kill(int(process_pid), 0)
                except (OSError, ProcessLookupError, ValueError, TypeError):
                    return False
            return True
        except (OSError, json.JSONDecodeError):
            return False

    def _send_command(self, command_type: CommandType, args: Dict[str, Any] = None, timeout: float = 30.0) -> IPCResponse:
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)
        command_id = f"cmd_{uuid.uuid4().hex}"
        command_path = os.path.join(self.commands_dir, f"{command_id}.json")
        response_path = os.path.join(self.responses_dir, f"{command_id}.json")
        payload = {
            "command_id": command_id,
            "command_type": command_type.value,
            "args": args or {},
            "created_at": datetime.now().isoformat(),
        }
        with open(command_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

        deadline = time.time() + max(0.1, float(timeout or 30.0))
        while time.time() < deadline:
            if os.path.exists(response_path):
                try:
                    with open(response_path, "r", encoding="utf-8") as handle:
                        data = json.load(handle)
                    return IPCResponse(
                        status=IPCStatus(data.get("status") or IPCStatus.FAILED.value),
                        result=data.get("result"),
                        error=str(data.get("error") or ""),
                        timestamp=str(data.get("timestamp") or datetime.now().isoformat()),
                    )
                except Exception as exc:
                    return IPCResponse(status=IPCStatus.FAILED, error=str(exc))
            time.sleep(0.15)
        return IPCResponse(status=IPCStatus.FAILED, error="IPC command timed out")

    def send_interview(self, agent_id: int, prompt: str, platform: str = None, timeout: float = 60.0) -> IPCResponse:
        return self._send_command(
            CommandType.INTERVIEW,
            {"agent_id": agent_id, "prompt": prompt, "platform": platform},
            timeout=timeout,
        )

    def send_batch_interview(self, interviews: List[Dict[str, Any]], platform: str = None, timeout: float = 180.0) -> IPCResponse:
        return self._send_command(
            CommandType.BATCH_INTERVIEW,
            {"interviews": interviews, "platform": platform},
            timeout=timeout,
        )

    def send_close_env(self, timeout: float = 30.0) -> IPCResponse:
        return self._send_command(CommandType.CLOSE_ENV, {}, timeout=timeout)

    def send_inject_variable(self, variable: Dict[str, Any], timeout: float = 30.0) -> IPCResponse:
        return self._send_command(CommandType.INJECT_VARIABLE, {"variable": variable}, timeout=timeout)


class SimulationIPCServer:
    def __init__(self, sim_dir: str):
        self.sim_dir = sim_dir
        self.ipc_dir = os.path.join(sim_dir, "ipc")
        self.commands_dir = os.path.join(self.ipc_dir, "commands")
        self.responses_dir = os.path.join(self.ipc_dir, "responses")

    def start(self):
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)

    def stop(self):
        return None

    def poll_commands(self):
        if not os.path.isdir(self.commands_dir):
            return None
        files = sorted(name for name in os.listdir(self.commands_dir) if name.endswith(".json"))
        if not files:
            return None
        path = os.path.join(self.commands_dir, files[0])
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            os.remove(path)
            return IPCCommand(
                command_id=str(data.get("command_id") or files[0].removesuffix(".json")),
                command_type=CommandType(data.get("command_type")),
                args=data.get("args") if isinstance(data.get("args"), dict) else {},
            )
        except Exception as exc:
            try:
                os.remove(path)
            except OSError:
                pass
            command_id = files[0].removesuffix(".json")
            self.send_error(command_id, str(exc))
            return None

    def poll_command(self):
        return self.poll_commands()

    def _write_response(self, command_id: str, response: IPCResponse):
        os.makedirs(self.responses_dir, exist_ok=True)
        path = os.path.join(self.responses_dir, f"{command_id}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "status": response.status.value,
                    "result": response.result,
                    "error": response.error,
                    "timestamp": response.timestamp,
                },
                handle,
                ensure_ascii=False,
                indent=2,
            )

    def send_success(self, command_id: str, result: Any = None):
        self._write_response(command_id, IPCResponse(status=IPCStatus.COMPLETED, result=result))

    def send_error(self, command_id: str, error: str):
        self._write_response(command_id, IPCResponse(status=IPCStatus.FAILED, error=error))
