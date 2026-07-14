"""M9 honesty deepening tests.

Proves the three honesty fixes for the report / analysis / node-exploration
layer, using deterministic construction only (no live LLM, no network):

1. The agent-state tool (formerly `interview_agents`) emits observed-metric
   *state cards*, NOT first-person "quotes" / "原话" / "采访实录".
2. The deprecated `interview_agents` alias delegates to the honest summary and
   carries the same non-quote framing.
3. The report agent's prompts are positioned as relationship-exploration, with
   prediction / "上帝视角" / "未来预测" language removed.
4. The narrative tab USES a runtime-provided `reasoning.summary` and surfaces
   `feedback.detected_feedback_loops` when present, falling back to the
   deterministic template only when absent.
"""

import unittest

from app.services.zep_tools import (
    ZepToolsService,
    AgentStateSummaryResult,
    InterviewResult,
)
from app.services import report_agent
from app.services.report_analysis import ReportAnalysisService


# ── state-card honesty (zep_tools) ──────────────────────────────────────────


def _make_service_with_bundle():
    """Build a ZepToolsService whose bundle is injected deterministically.

    We pre-seed the internal cache so `_load_bundle` never touches the
    SimulationManager / filesystem / LLM.
    """
    service = ZepToolsService()
    bundle = {
        "state": {},
        "config": {},
        "artifacts": {
            "latest_snapshot": {
                "round": 3,
                "agents": [
                    {
                        "agent_name": "渔业合作社负责人",
                        "primary_region": "茅洲河口",
                        "state_vector": {
                            "vulnerability_score": 0.71,
                            "panic_level": 0.40,
                            "response_capacity": 0.30,
                        },
                    }
                ],
            },
            "agent_interactions": [
                {
                    "source_agent_name": "环保监测站",
                    "action_type": "上报水质异常",
                    "rationale": "检测到溶解氧骤降",
                }
            ],
        },
    }
    service._bundle_cache["sim_test"] = bundle
    return service


# Affirmative quote / testimony framing that the OLD fake interview produced.
# (We must not catch our own honesty disclaimers like "非原话" / "非采访", so we
#  target affirmative speech-attribution patterns, not bare keyword mentions.)
QUOTE_FRAMINGS = ["表示：", "说：", "受访者", "采访实录", "第一人称发言"]


def _assert_no_quote_framing(testcase, text):
    for framing in QUOTE_FRAMINGS:
        testcase.assertNotIn(
            framing, text, f"state card must not read as a first-person quote ({framing})"
        )
    # The honest card explicitly disowns the quote framing.
    testcase.assertIn("非", text)


class AgentStateCardHonestyTests(unittest.TestCase):
    def test_summary_is_state_card_not_quote(self):
        service = _make_service_with_bundle()
        result = service.summarize_agent_state("sim_test", focus="谁最脆弱", max_agents=5)

        self.assertIsInstance(result, AgentStateSummaryResult)
        text = result.to_text()

        # Honest framing: labelled as observed metrics / state card.
        self.assertIn("状态卡", text)
        self.assertIn("观测", text)
        # Explicitly disowns interview / quote framing in the header.
        self.assertIn("非采访", text)

        # Must NOT present numbers as testimony / first-person quotes.
        _assert_no_quote_framing(self, text)

        # The observed numbers should still be present (it's a real summary).
        self.assertIn("脆弱性", text)
        self.assertIn("0.71", text)

    def test_legacy_interview_alias_delegates_and_is_not_a_quote(self):
        service = _make_service_with_bundle()
        legacy = service.interview_agents("sim_test", interview_requirement="任意主题")

        self.assertIsInstance(legacy, InterviewResult)
        text = legacy.to_text()

        # Alias inherits the honest state-card framing, never a fake interview.
        self.assertIn("状态卡", text)
        self.assertIn("非采访", text)
        _assert_no_quote_framing(self, text)


# ── report-agent positioning honesty ────────────────────────────────────────


class ReportPromptPositioningTests(unittest.TestCase):
    def test_prompts_drop_prediction_and_oracle_language(self):
        plan = report_agent.PLAN_SYSTEM_PROMPT
        section = report_agent.SECTION_SYSTEM_PROMPT_TEMPLATE

        # The OLD prompt's affirmative oracle/prediction framing must be gone.
        # (We target affirmative sentences, not bare keywords, because the new
        #  prompt legitimately *negates* "上帝视角"/"未来预测".)
        for banned in [
            "「未来预测报告」的撰写专家",
            "拥有对模拟世界的「上帝视角」",
            "模拟世界的演化结果，就是对未来可能发生情况的预测",
        ]:
            self.assertNotIn(banned, plan, f"plan prompt still claims prediction/oracle: {banned}")

        # New positioning is relationship-exploration and honesty-aware.
        self.assertIn("关系探索", plan)
        self.assertIn("观测", plan)

        # Section prompt no longer instructs the model to fabricate first-person
        # agent quotes as the "core evidence".
        self.assertNotIn("必须引用Agent的原始言行", section)
        self.assertNotIn("「上帝视角」观察未来的预演", section)
        self.assertIn("禁止伪造", section)

    def test_state_tool_registered_and_described_without_interview_framing(self):
        desc = report_agent.TOOL_DESC_AGENT_STATE_SUMMARY
        self.assertIn("状态卡", desc)
        self.assertIn("这不是采访", desc)


# ── narrative tab uses real reasoning.summary ───────────────────────────────


def _make_analyzer(round_snapshots):
    """Construct a ReportAnalysisService without running __init__.

    `_build_narrative_tab` only reads `round_snapshots` / `latest_snapshot`,
    so we bypass the DB/report-loading constructor entirely.
    """
    analyzer = ReportAnalysisService.__new__(ReportAnalysisService)
    analyzer.round_snapshots = round_snapshots
    analyzer.latest_snapshot = round_snapshots[-1] if round_snapshots else {}
    analyzer.mechanism_artifacts = {}
    return analyzer


class NarrativeTabHonestyTests(unittest.TestCase):
    def test_narrative_uses_runtime_reasoning_summary(self):
        snap = {
            "round": 4,
            "regions": [
                {
                    "name": "石岩水库",
                    "vulnerability_score": 0.82,
                    "uncertainty_band": {"confidence": 0.6},
                }
            ],
            "reasoning": {
                "summary": "本轮恐慌-响应-摩擦回路放大了上游暴露，石岩水库张力上升。",
                "turning_points": [
                    {"description": "第4轮治理响应迟滞，暴露转为自我强化"}
                ],
            },
            "feedback": {
                "detected_feedback_loops": [
                    {"loop": "恐慌→响应迟滞→暴露上升→更多恐慌"}
                ]
            },
        }
        analyzer = _make_analyzer([snap])
        tab = analyzer._build_narrative_tab()

        self.assertEqual(tab["tab"], "narrative")
        entry = tab["rounds"][0]

        # The runtime summary is used verbatim as the headline (not a template).
        self.assertEqual(entry["narrative_source"], "snapshot.reasoning.summary")
        self.assertEqual(
            entry["headline"],
            "本轮恐慌-响应-摩擦回路放大了上游暴露，石岩水库张力上升。",
        )

        # Detected feedback loops + turning points are surfaced.
        self.assertEqual(
            entry["detected_feedback_loops"], ["恐慌→响应迟滞→暴露上升→更多恐慌"]
        )
        self.assertIn("第4轮治理响应迟滞，暴露转为自我强化", entry["turning_points"])
        self.assertIn("恐慌→响应迟滞→暴露上升→更多恐慌", entry["amplifier"])

    def test_narrative_falls_back_to_template_when_reasoning_absent(self):
        snap = {
            "round": 1,
            "regions": [{"name": "茅洲河", "vulnerability_score": 0.55}],
        }
        analyzer = _make_analyzer([snap])
        entry = analyzer._build_narrative_tab()["rounds"][0]

        self.assertEqual(entry["narrative_source"], "derived_template")
        self.assertIn("茅洲河", entry["headline"])
        self.assertEqual(entry["detected_feedback_loops"], [])

    def test_narrative_hides_english_runtime_summary(self):
        snap = {
            "round": 1,
            "regions": [{"name": "南侧近岸水域", "vulnerability_score": 81}],
            "reasoning": {
                "summary": "Round 1 establishes the initial radioactive release in the southern nearshore waters."
            },
        }
        analyzer = _make_analyzer([snap])
        entry = analyzer._build_narrative_tab()["rounds"][0]

        self.assertEqual(entry["narrative_source"], "derived_template")
        self.assertNotIn("Round 1", entry["headline"])
        self.assertIn("南侧近岸水域", entry["headline"])

    def test_feedback_tab_localizes_english_snapshot_text(self):
        snap = {
            "round": 10,
            "feedback": {
                "feedback_propagation": [
                    {
                        "region_id": "south",
                        "region_name": "南侧近岸水域",
                        "loop": "Minor propagation from southern corridor.",
                        "delta": {"panic_level": 1, "economic_stress": -1},
                    }
                ],
                "ecological_impacts": [
                    {
                        "region_id": "east",
                        "region_name": "东侧建成片区",
                        "note": "Urban runoff and habitat fragmentation continue.",
                        "delta": {"ecosystem_integrity": -1},
                    }
                ],
            },
        }
        analyzer = _make_analyzer([snap])
        tab = analyzer._build_feedback_tab()

        self.assertEqual(tab["items"][0]["loop"], "南侧廊道出现轻微传播。")
        self.assertEqual(tab["ecological_impacts"][0]["note"], "城市径流与栖息地破碎化影响仍在持续。")

    def test_mechanism_tab_uses_display_labels_not_internal_ids(self):
        analyzer = _make_analyzer([])
        analyzer.mechanism_artifacts = {
            "scenario_model": {},
            "mechanism_graph": {
                "nodes": [
                    {"id": "mech_1", "name": "释放源"},
                    {"id": "mech_2", "name": "洋流扩散"},
                ],
                "edges": [
                    {
                        "id": "edge_1",
                        "source": "mech_1",
                        "target": "mech_2",
                        "relation_label": "triggers",
                        "scope": "local",
                    }
                ],
            },
            "relation_ledger": [
                {
                    "status": "accepted",
                    "relation_label": "reports_to",
                    "candidate": {"relation_label": "reports_to", "mechanism": "巡护站上报监测数据"},
                }
            ],
            "round_reasoning": [
                {
                    "round": 1,
                    "summary": "Round 1 establishes the initial radioactive release.",
                    "feedback_turning_points": ["第1轮，治理响应启动。"],
                }
            ],
        }

        tab = analyzer._build_mechanisms_tab()
        edge = tab["mechanism_graph"]["edges"][0]

        self.assertEqual(edge["source_label"], "释放源")
        self.assertEqual(edge["target_label"], "洋流扩散")
        self.assertEqual(edge["scope_label"], "局部")
        self.assertEqual(tab["relation_samples"][0]["relation_label"], "上报给")
        self.assertEqual(tab["round_reasoning"][0]["summary"], "第1轮，治理响应启动。")

    def test_roles_tab_uses_environment_state_nodes_for_ecology_group(self):
        snap = {
            "round": 10,
            "agents": [
                {
                    "agent_id": 1,
                    "agent_name": "环保部门",
                    "agent_type": "governance",
                    "agent_subtype": "environment_bureau",
                    "primary_region": "东侧湿地生态带",
                    "state_vector": {"response_capacity": 70, "service_capacity": 40, "public_trust": 50},
                }
            ],
            "regions": [
                {
                    "region_id": "wetland",
                    "name": "东侧湿地生态带",
                    "region_type": "ecology_zone",
                    "state_vector": {
                        "ecosystem_integrity": 54.5,
                        "exposure_score": 58.0,
                        "spread_pressure": 56.0,
                    },
                },
                {
                    "region_id": "urban",
                    "name": "东侧建成片区",
                    "region_type": "urban_zone",
                    "state_vector": {
                        "ecosystem_integrity": 48.0,
                        "exposure_score": 61.0,
                        "spread_pressure": 55.0,
                    },
                },
            ],
            "subregions": [
                {
                    "subregion_id": "shore",
                    "name": "南侧近岸水域·滨海生态缓冲带",
                    "parent_region_id": "南侧近岸水域",
                    "land_use_class": "ecology",
                    "region_type": "shore_buffer_zone",
                    "state_vector": {
                        "ecosystem_integrity": 53.8,
                        "exposure_score": 57.0,
                        "spread_pressure": 63.0,
                    },
                }
            ],
        }
        analyzer = _make_analyzer([snap])
        tab = analyzer._build_roles_tab()
        ecology = next(group for group in tab["groups"] if group["group_id"] == "ecology")

        self.assertEqual(ecology["node_count"], 2)
        self.assertEqual(ecology["metric_averages"]["ecosystem_integrity"], 54.15)
        self.assertEqual(ecology["metric_averages"]["exposure_score"], 57.5)
        self.assertIn("东侧湿地生态带", [item["name"] for item in ecology["sample_nodes"]])
        self.assertIn("南侧近岸水域·滨海生态缓冲带", [item["name"] for item in ecology["sample_nodes"]])


if __name__ == "__main__":
    unittest.main()
