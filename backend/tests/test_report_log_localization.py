import json

from flask import Flask

from app.api import report_bp
from app.api import report as report_api


def _report_client():
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.register_blueprint(report_bp, url_prefix="/api/report")
    return app.test_client()


def _assert_no_internal_log_text(value):
    serialized = json.dumps(value, ensure_ascii=False)
    forbidden = (
        "envfish_summary",
        "planning_start",
        "llm_response",
        "tool_call",
        "tool_result",
        "Traceback",
        "RuntimeError",
        "POST /api",
        "/api/",
        "/tmp/",
        "/Users/",
        "127.0.0.1",
        "ReACT",
        "LLM",
        "Agent 9",
        "feature_relation_1527220",
        "9f8c67a1-e231-4cab-8a99-125470ab68bf",
    )
    assert all(token not in serialized for token in forbidden)


def test_console_log_projection_keeps_chinese_and_hides_diagnostics():
    projected = report_api._project_console_log_payload(
        {
            "logs": [
                "[12:00:00] INFO: 开始规划报告大纲...",
                "[12:00:01] INFO: 执行工具: envfish_summary, 参数: {'limit': 10}",
                "[12:00:02] WARNING: ReACT生成章节: 风险扩散达到最大迭代次数",
                (
                    "[12:00:03] ERROR: Traceback RuntimeError at "
                    "/tmp/private.py POST /api/report 127.0.0.1:8000"
                ),
                "[12:00:04] INFO: 章节已保存: report_secret/section_01.md",
                (
                    "[12:00:05] INFO: 关系feature_relation_1527220已归档，"
                    "记录9f8c67a1-e231-4cab-8a99-125470ab68bf已更新，"
                    "主机127.0.0.1已隐藏"
                ),
            ],
            "total_lines": 6,
            "from_line": 0,
            "has_more": False,
        }
    )

    assert projected["total_lines"] == 6
    assert projected["from_line"] == 0
    assert projected["has_more"] is False
    assert any("开始规划报告大纲" in line for line in projected["logs"])
    assert any("正在执行内部分析步骤" in line for line in projected["logs"])
    assert any("开始生成章节：风险扩散达到最大迭代次数" in line for line in projected["logs"])
    assert any("内部处理异常，详细信息已隐藏" in line for line in projected["logs"])
    assert any("章节已保存" in line for line in projected["logs"])
    assert any("关系已归档，记录已更新，主机已隐藏" in line for line in projected["logs"])
    assert all(any("\u3400" <= char <= "\u9fff" for char in line) for line in projected["logs"])
    _assert_no_internal_log_text(projected["logs"])


def test_console_log_http_uses_public_projection(monkeypatch):
    monkeypatch.setattr(
        report_api.ReportManager,
        "get_console_log",
        classmethod(
            lambda cls, report_id, from_line=0: {
                "logs": [
                    "[08:00:00] INFO: 执行工具: envfish_summary, 参数: {'limit': 8}",
                    "[08:00:01] INFO: 报告已保存: report_secret",
                    "[08:00:02] ERROR: Traceback at /Users/dev/private.py",
                ],
                "total_lines": 3,
                "from_line": from_line,
                "has_more": False,
            }
        ),
    )

    response = _report_client().get("/api/report/report_public/console-log?from_line=1")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["data"]["from_line"] == 1
    assert any("内部分析步骤" in line for line in payload["data"]["logs"])
    _assert_no_internal_log_text(payload["data"]["logs"])


def test_agent_log_projection_exposes_only_readable_progress():
    projected = report_api._project_agent_log_payload(
        {
            "logs": [
                {
                    "timestamp": "2026-07-13T12:00:00.123456",
                    "elapsed_seconds": 2.5,
                    "report_id": "report_secret",
                    "action": "tool_call",
                    "stage": "generating",
                    "section_title": "风险扩散",
                    "section_index": 1,
                    "details": {
                        "iteration": 2,
                        "tool_name": "envfish_summary",
                        "parameters": {"endpoint": "POST /api/private"},
                        "tool_calls_count": 4,
                        "message": "调用工具: envfish_summary",
                    },
                },
                {
                    "timestamp": "2026-07-13T12:00:01.123456",
                    "elapsed_seconds": 3.0,
                    "action": "llm_response",
                    "stage": "generating",
                    "section_title": "风险扩散",
                    "section_index": 1,
                    "details": {
                        "iteration": 3,
                        "response": (
                            "<tool_call>{'name': 'envfish_summary'}</tool_call>\n"
                            "Traceback at /tmp/private.py"
                        ),
                        "response_length": 80,
                        "message": "LLM response for Agent 9 at 127.0.0.1",
                    },
                },
                {
                    "timestamp": "2026-07-13T12:00:02.123456",
                    "elapsed_seconds": 3.5,
                    "action": "error",
                    "stage": "failed",
                    "section_title": "风险扩散",
                    "section_index": 1,
                    "details": {
                        "error": "RuntimeError at /Users/dev/private.py",
                        "message": "发生错误: RuntimeError at /api/private",
                    },
                },
            ],
            "total_lines": 3,
            "from_line": 0,
            "has_more": False,
        }
    )

    assert [item["action"] for item in projected["logs"]] == [
        "正在执行内部分析步骤",
        "报告内容生成状态已更新",
        "报告生成异常",
    ]
    assert [item["stage"] for item in projected["logs"]] == ["生成中", "生成中", "失败"]
    assert projected["logs"][0]["details"] == {
        "message": "正在执行内部分析步骤",
        "iteration": 2,
    }
    assert projected["logs"][1]["details"]["response_length"] == 80
    assert projected["logs"][2]["details"]["message"] == "报告生成出现异常，详细信息已隐藏"
    assert all("tool_name" not in item["details"] for item in projected["logs"])
    assert all("tool_calls_count" not in item["details"] for item in projected["logs"])
    assert all("response" not in item["details"] for item in projected["logs"])
    _assert_no_internal_log_text(projected["logs"])


def test_agent_log_http_uses_public_projection(monkeypatch):
    monkeypatch.setattr(
        report_api.ReportManager,
        "get_agent_log",
        classmethod(
            lambda cls, report_id, from_line=0: {
                "logs": [
                    {
                        "timestamp": "2026-07-13T12:00:00",
                        "elapsed_seconds": 1,
                        "report_id": report_id,
                        "action": "planning_start",
                        "stage": "planning",
                        "section_title": None,
                        "section_index": None,
                        "details": {
                            "message": "开始规划报告大纲",
                            "context": {
                                "endpoint": "POST /api/private",
                                "host": "127.0.0.1",
                            },
                        },
                    }
                ],
                "total_lines": 1,
                "from_line": from_line,
                "has_more": False,
            }
        ),
    )

    response = _report_client().get("/api/report/report_public/agent-log")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["data"]["logs"][0]["action"] == "开始规划报告大纲"
    assert payload["data"]["logs"][0]["stage"] == "规划中"
    assert payload["data"]["logs"][0]["details"] == {"message": "开始规划报告大纲"}
    _assert_no_internal_log_text(payload["data"]["logs"])
