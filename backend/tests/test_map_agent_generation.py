import unittest

from app.services.env_profile_generator import EnvProfileGenerator
from app.services.envfish_models import RegionNode
from app.services.zep_entity_reader import EntityNode


def make_entity(
    uuid,
    name,
    label,
    *,
    subtype="",
    category="ecology",
    source_kind="observed",
    lat=22.0,
    lon=114.0,
    importance=4,
    tags=None,
    extra_attrs=None,
):
    attrs = {
        "category": category,
        "subtype": subtype,
        "source_kind": source_kind,
        "lat": lat,
        "lon": lon,
        "importance": importance,
        "confidence": 0.8,
        "tags": tags or {},
    }
    attrs.update(extra_attrs or {})
    return EntityNode(
        uuid=uuid,
        name=name,
        labels=["Entity", label],
        summary=name,
        attributes=attrs,
    )


def make_root():
    return make_entity(
        "region_root",
        "Selected AOI",
        "Region",
        subtype="",
        category="region",
        source_kind="observed",
        extra_attrs={
            "radius_m": 12000,
            "admin_context": {
                "display_name": "Selected AOI",
                "city": "",
                "lat": 22.0,
                "lon": 114.0,
            },
        },
    )


class MapAgentGenerationTestCase(unittest.TestCase):
    def setUp(self):
        self.generator = EnvProfileGenerator(llm_client=None)

    def _prepare(self, entities):
        return [self.generator._prepare_entity(entity) for entity in entities]

    def test_ocean_map_seed_gates_social_agents(self):
        prepared = self._prepare(
            [
                make_root(),
                make_entity("water_1", "WorldCover water 1", "EnvironmentalCarrier", subtype="worldcover_80", source_kind="detected", tags={"pixel_share_pct": 55}),
                make_entity("water_2", "WorldCover water 2", "EnvironmentalCarrier", subtype="worldcover_80", source_kind="detected", lat=22.01, lon=114.01, tags={"pixel_share_pct": 40}),
                make_entity("water_3", "Open water", "EnvironmentalCarrier", subtype="water", source_kind="observed", lat=22.02, lon=114.02),
            ]
        )
        regions = [
            RegionNode(
                region_id="open_ocean",
                name="远海水域",
                region_type="coastal_zone",
                land_use_class="water",
                layer="macro",
                tags=["water"],
                carriers=["water_flow"],
                lat=22.0,
                lon=114.0,
            )
        ]
        subregions = self.generator._build_subregions(
            regions=regions,
            prepared_entities=prepared,
            scenario_mode="baseline_mode",
            diffusion_template="marine",
        )
        context = self.generator._build_map_evidence_context(
            prepared_entities=prepared,
            regions=regions,
            subregions=subregions,
            diffusion_template="marine",
            search_mode="fast",
        )
        target_count = self.generator._target_agent_count(
            prepared_entities=prepared,
            regions=regions,
            subregions=subregions,
            map_evidence_context=context,
        )
        profiles, _synthetic, summary = self.generator._generate_map_seed_agent_profiles(
            prepared_entities=prepared,
            regions=regions,
            subregions=subregions,
            scenario_mode="baseline_mode",
            diffusion_template="marine",
            simulation_requirement="simulate ocean pollution spread",
            evidence_context=context,
            target_count=target_count,
            use_llm=False,
        )

        self.assertEqual(context.environment_archetype, "ocean_sparse")
        self.assertGreaterEqual(len(profiles), 8)
        self.assertLessEqual(len(profiles), 20)
        self.assertIn("rejected_candidates", summary)
        self.assertFalse(any(profile.agent_type in {"human", "organization"} for profile in profiles))
        self.assertFalse(
            any(
                profile.agent_subtype in {"resident", "shop_owner", "community_committee", "worker", "plant_operator"}
                for profile in profiles
            )
        )

    def test_urban_map_seed_social_agents_keep_evidence_refs(self):
        prepared = self._prepare(
            [
                make_root(),
                make_entity("residential_1", "Residential blocks", "HumanActor", subtype="residential", category="facility"),
                make_entity("commercial_1", "Commercial hub", "OrganizationActor", subtype="commercial_hub", category="facility", lat=22.01),
                make_entity("school_1", "School", "OrganizationActor", subtype="school", category="facility", lon=114.01),
                make_entity("road_1", "Main road", "Infrastructure", subtype="road_corridor", category="infrastructure", lat=22.02),
                make_entity("built_1", "Built-up cover", "HumanActor", subtype="worldcover_50", source_kind="detected", tags={"pixel_share_pct": 38}),
            ]
        )
        regions = [
            RegionNode(
                region_id="urban_core",
                name="城市建成片区",
                region_type="urban_zone",
                land_use_class="urban",
                layer="macro",
                tags=["urban", "transport"],
                carriers=["daily_contact", "transport_flow"],
                lat=22.0,
                lon=114.0,
            )
        ]
        subregions = self.generator._build_subregions(
            regions=regions,
            prepared_entities=prepared,
            scenario_mode="baseline_mode",
            diffusion_template="generic",
        )
        context = self.generator._build_map_evidence_context(
            prepared_entities=prepared,
            regions=regions,
            subregions=subregions,
            diffusion_template="generic",
            search_mode="fast",
        )
        target_count = self.generator._target_agent_count(
            prepared_entities=prepared,
            regions=regions,
            subregions=subregions,
            map_evidence_context=context,
        )
        profiles, _synthetic, summary = self.generator._generate_map_seed_agent_profiles(
            prepared_entities=prepared,
            regions=regions,
            subregions=subregions,
            scenario_mode="baseline_mode",
            diffusion_template="generic",
            simulation_requirement="simulate urban service disruption",
            evidence_context=context,
            target_count=target_count,
            use_llm=False,
        )

        self.assertEqual(context.environment_archetype, "urban")
        self.assertGreaterEqual(len(profiles), context.target_count_range[0])
        self.assertLessEqual(len(profiles), context.target_count_range[1])
        social_profiles = [profile for profile in profiles if profile.agent_type in {"human", "organization"}]
        self.assertTrue(social_profiles)
        for profile in social_profiles:
            self.assertTrue(any(not ref.startswith("subregion::") for ref in profile.evidence_refs))
            self.assertEqual(profile.review_status, "accepted")
        self.assertEqual(summary["actual_agent_count"], len(profiles))


if __name__ == "__main__":
    unittest.main()
