"""M4 deepening tests: agent identity no longer collapses to (human, resident)
and every entity_template profile carries an honest provenance stamp.

These exercise the deterministic rule/fallback path only (use_llm=False), so
they import and run without any live LLM or network access.
"""

import unittest

from app.services.env_profile_generator import EnvProfileGenerator, PreparedEntityContext
from app.services.envfish_models import RegionNode, infer_node_family
from app.services.zep_entity_reader import EntityNode


def make_prepared(uuid, name, label, *, summary="", attributes=None, relation_hints=None):
    attrs = {"source_kind": "inferred"}
    attrs.update(attributes or {})
    entity = EntityNode(
        uuid=uuid,
        name=name,
        labels=["Entity", label],
        summary=summary or name,
        attributes=attrs,
    )
    summary_text = summary or name
    return PreparedEntityContext(
        entity=entity,
        entity_type=label,
        node_family=infer_node_family(label, name, summary_text),
        summary=summary_text,
        relation_hints=relation_hints or [],
    )


def build(generator, index, prepared):
    region = RegionNode(region_id="region_core", name="Core Region", land_use_class="mixed")
    return generator._build_profile(
        index=index,
        prepared=prepared,
        regions=[region],
        subregions=[],
        scenario_mode="baseline_mode",
        simulation_requirement="探索人-自然耦合关系",
        injected_variables=[],
        use_llm=False,
    )


class AgentIdentityDeepeningTests(unittest.TestCase):
    def setUp(self):
        # llm_client=None + use_llm=False guarantees the deterministic path.
        self.generator = EnvProfileGenerator(llm_client=None)
        self.generator.llm_client = None

    def test_distinct_role_signals_do_not_collapse_to_resident(self):
        prepared = [
            make_prepared("u_sci", "Coastal Ecology Lab", "OrganizationActor",
                          summary="research institute studying water quality"),
            make_prepared("u_worker", "Riverside Worker", "HumanActor",
                          attributes={"role": "factory operator"}),
            make_prepared("u_journ", "Local Reporter", "HumanActor",
                          attributes={"profession": "journalist"}, summary="covers pollution news"),
            make_prepared("u_gov", "Environment Bureau", "GovernmentActor",
                          summary="environmental enforcement agency"),
            make_prepared("u_eco", "Mangrove Habitat", "EcologicalReceptor",
                          summary="coastal mangrove habitat"),
            make_prepared("u_infra", "Cross-bay Bridge", "Infrastructure",
                          summary="transport pipeline and road hub"),
        ]
        profiles = [build(self.generator, i, p) for i, p in enumerate(prepared)]

        subtypes = [p.agent_subtype for p in profiles]
        agent_types = [p.agent_type for p in profiles]

        # The core regression: NOT everything is (human, resident).
        self.assertGreaterEqual(
            len(set(zip(agent_types, subtypes))), 4,
            f"identity collapsed across role signals: {list(zip(agent_types, subtypes))}",
        )
        self.assertFalse(
            all(p.agent_type == "human" and p.agent_subtype == "resident" for p in profiles),
            "all distinct entities collapsed onto (human, resident)",
        )
        # Type spectrum really spreads beyond human.
        self.assertTrue({"governance", "ecology", "infrastructure"} & set(agent_types))
        # Persona must not be left empty / must be subtype-consistent (non-generic resident text).
        for profile in profiles:
            self.assertTrue(profile.persona.strip())

    def test_unknown_role_is_unspecified_not_silently_resident(self):
        prepared = make_prepared(
            "u_unknown", "Node 7", "Entity",
            summary="an entity with no defensible role signal",
        )
        profile = build(self.generator, 0, prepared)
        self.assertEqual(profile.agent_subtype, "unspecified")
        self.assertEqual(profile.review_status, "assumed")
        self.assertNotEqual(profile.agent_subtype, "resident")

    def test_provenance_is_stamped_observed_vs_inferred(self):
        observed = make_prepared(
            "u_obs", "Surveyed Worker", "HumanActor",
            attributes={"role": "worker", "source_kind": "observed", "osm_id": "12345"},
        )
        inferred = make_prepared(
            "u_inf", "Inferred Worker", "HumanActor",
            attributes={"role": "worker", "source_kind": "inferred"},
        )
        p_obs = build(self.generator, 0, observed)
        p_inf = build(self.generator, 1, inferred)

        # Observed: backed by external evidence anchors, higher confidence, honest (<1.0).
        self.assertEqual(p_obs.review_status, "observed")
        self.assertTrue(p_obs.evidence_refs)
        self.assertTrue(any(not r.startswith(("subregion::", "entity::")) for r in p_obs.evidence_refs))
        self.assertGreater(p_obs.evidence_confidence, p_inf.evidence_confidence)
        self.assertLess(p_obs.evidence_confidence, 1.0)

        # Inferred: real source entity but no external corroboration of the role.
        self.assertEqual(p_inf.review_status, "inferred")
        self.assertTrue(any("\u3400" <= char <= "\u9fff" for char in p_inf.grounding_reason))
        self.assertNotIn("provenance=", p_inf.grounding_reason)

        # Both share the resolved role; only the provenance tier differs.
        self.assertEqual(p_obs.agent_subtype, "worker")
        self.assertEqual(p_inf.agent_subtype, "worker")
        self.assertEqual(p_obs.generation_mode, "entity_template")

    def test_provenance_survives_serialization(self):
        prepared = make_prepared(
            "u_ser", "Field Scientist", "HumanActor",
            attributes={"role": "scientist", "source_kind": "observed"},
        )
        profile = build(self.generator, 0, prepared)
        payload = profile.to_dict()
        config = profile.to_agent_config()
        self.assertEqual(payload["review_status"], "observed")
        self.assertEqual(config["review_status"], "observed")
        self.assertEqual(config["agent_name"], profile.name)
        self.assertTrue(any("\u3400" <= char <= "\u9fff" for char in config["grounding_reason"]))
        self.assertNotIn("provenance=", config["grounding_reason"])
        self.assertEqual(profile.agent_subtype, "scientist")


if __name__ == "__main__":
    unittest.main()
