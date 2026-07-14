"""Single replaceable Agent planning boundary for Step 2.

Step 2 owns the scenario contract, not the Agent implementation.  The default
provider submits RoleDemand to Agent V2 while retaining only the compatibility
projection needed by the current runtime engine.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .scenario_planner import (
    AgentPlanningPort,
    AgentV2PlanningAdapter,
    ScenarioPlanningInput,
)


_DEFAULT_PORT: AgentPlanningPort = AgentV2PlanningAdapter()


class AgentPlanningPortError(RuntimeError):
    pass


def get_agent_planning_port() -> AgentPlanningPort:
    return _DEFAULT_PORT


def plan_scenario_agents(
    scenario: ScenarioPlanningInput,
    *,
    port: Optional[AgentPlanningPort] = None,
) -> Dict[str, Any]:
    provider = port or get_agent_planning_port()
    try:
        result = provider.plan(scenario)
    except Exception as exc:
        raise AgentPlanningPortError(f"Agent 规划适配失败: {exc}") from exc
    if not isinstance(result, dict):
        raise AgentPlanningPortError("Agent 规划服务返回了无效结果")
    result.setdefault("agent_plan_source", "unknown")
    return result
