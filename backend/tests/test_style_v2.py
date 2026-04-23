import os
import shutil
import tempfile
import unittest

from app.services.style_v2 import (
    ReviewPolicyV2,
    StyleKnowledgeRetrieverV2,
    StyleLibraryV2Manager,
    StyleReviewerV2,
    StyleWritingEngineV2,
)


class DummyLLM:
    def __init__(self, response: str = "默认输出"):
        self.response = response
        self.calls = 0

    def chat(self, **kwargs):
        self.calls += 1
        return self.response


class StyleV2TestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="style_v2_test_")

        self._orig_root = StyleLibraryV2Manager.ROOT_DIR
        self._orig_profiles = StyleLibraryV2Manager.PROFILES_DIR
        self._orig_bindings = StyleLibraryV2Manager.BINDINGS_DIR
        self._orig_policies = StyleLibraryV2Manager.POLICIES_DIR

        StyleLibraryV2Manager.ROOT_DIR = self.temp_dir
        StyleLibraryV2Manager.PROFILES_DIR = os.path.join(self.temp_dir, "profiles")
        StyleLibraryV2Manager.BINDINGS_DIR = os.path.join(self.temp_dir, "bindings")
        StyleLibraryV2Manager.POLICIES_DIR = os.path.join(self.temp_dir, "review_policies")

        self.manager = StyleLibraryV2Manager()

    def tearDown(self):
        StyleLibraryV2Manager.ROOT_DIR = self._orig_root
        StyleLibraryV2Manager.PROFILES_DIR = self._orig_profiles
        StyleLibraryV2Manager.BINDINGS_DIR = self._orig_bindings
        StyleLibraryV2Manager.POLICIES_DIR = self._orig_policies
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_legacy_profile_migration(self):
        legacy = {
            "id": "legacy-style",
            "身份与视角": "冷静讲事实，但结尾有情绪推力",
            "节奏与结构": "先结论后解释",
            "推荐口头禅": "又双叒叕,天钧",
            "禁忌词": "总而言之,综上所述",
        }
        profile = self.manager.save_profile(legacy)

        self.assertEqual(profile.id, "legacy-style")
        self.assertEqual(profile.core.persona, "冷静讲事实，但结尾有情绪推力")
        self.assertEqual(len(profile.signal_pool), 2)
        self.assertIn("总而言之", profile.anti_patterns.hard)

    def test_signal_budget_enforcement(self):
        profile = self.manager.save_profile(
            {
                "id": "signal-style",
                "core": {"persona": "测试", "audience": "用户", "stance": "中立"},
                "writing": {
                    "ordering": "先结论后解释",
                    "sentence_mix": "短句为主+少量长句",
                    "paragraph_rule": "每段一个点",
                    "density": "中高信息密度",
                },
                "signal_pool": [
                    {
                        "text": "又双叒叕",
                        "scene": "通用",
                        "max_per_600_chars": 1,
                        "max_per_doc": 1,
                    }
                ],
                "anti_patterns": {"hard": [], "soft": []},
            }
        )

        engine = StyleWritingEngineV2(manager=self.manager, llm_client=DummyLLM())
        cleaned = engine._enforce_signal_budget(
            "又双叒叕，这段话开头。又双叒叕，这段话中段。又双叒叕，这段话结尾。",
            profile,
            scene="通用",
        )

        self.assertLessEqual(cleaned.count("又双叒叕"), 1)

    def test_hard_rule_hit_triggers_rewrite(self):
        profile = self.manager.save_profile(
            {
                "id": "hard-style",
                "core": {"persona": "测试", "audience": "用户", "stance": "中立"},
                "writing": {
                    "ordering": "先结论后解释",
                    "sentence_mix": "短句为主+少量长句",
                    "paragraph_rule": "每段一个点",
                    "density": "中高信息密度",
                },
                "signal_pool": [],
                "anti_patterns": {"hard": ["总而言之"], "soft": []},
            }
        )
        reviewer = StyleReviewerV2()
        policy = ReviewPolicyV2.default()

        result = reviewer.evaluate("总而言之，这个结论已经很清楚了。", profile, policy)

        self.assertEqual(result["decision"], "hard_rewrite")
        self.assertGreaterEqual(len(result["hard_hits"]), 1)

    def test_missing_kb_refs_fallback(self):
        self.manager.save_profile(
            {
                "id": "kb-style",
                "core": {"persona": "测试", "audience": "用户", "stance": "中立"},
                "writing": {
                    "ordering": "先结论后解释",
                    "sentence_mix": "短句为主+少量长句",
                    "paragraph_rule": "每段一个点",
                    "density": "中高信息密度",
                },
                "signal_pool": [],
                "anti_patterns": {"hard": [], "soft": []},
            }
        )

        binding = self.manager.save_binding(
            {
                "style_id": "kb-style",
                "kb_refs": [{"doc_id": "project:missing:text", "scene": "通用", "weight": 1.0}],
                "retrieval": {"top_k": 5, "min_sources": 2, "max_quote_chars": 220},
            }
        )

        retriever = StyleKnowledgeRetrieverV2(self.manager)
        samples = retriever.retrieve_samples(task="写一个短评", scene="通用", binding=binding)

        self.assertEqual(samples, [])

    def test_generate_with_draft_works_without_llm(self):
        self.manager.save_profile(
            {
                "id": "draft-style",
                "core": {"persona": "测试", "audience": "用户", "stance": "中立"},
                "writing": {
                    "ordering": "先结论后解释",
                    "sentence_mix": "短句为主+少量长句",
                    "paragraph_rule": "每段一个点",
                    "density": "中高信息密度",
                },
                "signal_pool": [],
                "anti_patterns": {"hard": [], "soft": []},
            }
        )

        dummy = DummyLLM(response="不会被调用")
        engine = StyleWritingEngineV2(manager=self.manager, llm_client=dummy)

        result = engine.generate(
            style_id="draft-style",
            task="根据主题写一段文字",
            scene="通用",
            draft_text="首先，这是第一点。其次，这是第二点。最后，这是总结。",
            max_rewrite_rounds=0,
        )

        self.assertEqual(dummy.calls, 0)
        self.assertTrue(result["trace"]["fallback_to_style_only"])
        self.assertIn("text", result)
        self.assertIn("review", result)


if __name__ == "__main__":
    unittest.main()
