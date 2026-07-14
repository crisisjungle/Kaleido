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
    resolved_tags = dict(tags or {})
    if source_kind in {"observed", "detected"} and "provider" not in resolved_tags:
        resolved_tags["provider"] = "worldcover_cog" if source_kind == "detected" else "osm_overpass"
    attrs = {
        "category": category,
        "subtype": subtype,
        "source_kind": source_kind,
        "lat": lat,
        "lon": lon,
        "importance": importance,
        "confidence": 0.8,
        "tags": resolved_tags,
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
            "data_quality": {"status": "complete", "formal_ready": True},
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

    def test_map_seed_water_regions_keep_hydrologic_type_and_real_name(self):
        prepared = self._prepare(
            [
                make_root(),
                make_entity("coast_1", "深圳湾", "EnvironmentalCarrier", subtype="coastline", lat=22.02, lon=114.0),
                make_entity("river_1", "茅洲河", "EnvironmentalCarrier", subtype="river", lat=22.0, lon=114.02),
                make_entity(
                    "reservoir_1",
                    "石岩水库",
                    "EnvironmentalCarrier",
                    subtype="reservoir",
                    source_kind="reference",
                    lat=21.98,
                    lon=114.0,
                ),
            ]
        )
        prepared[0].node_family = "Region"
        self.assertTrue(self.generator._looks_like_map_seed_context(prepared))

        regions = self.generator._build_regions_from_map_seed(
            prepared_entities=prepared,
            scenario_mode="baseline_mode",
            diffusion_template="inland_water_network",
            search_mode="fast",
        )
        by_name = {region.name: region for region in regions}

        self.assertEqual(by_name["深圳湾"].region_type, "coastal_zone")
        self.assertEqual(by_name["茅洲河"].region_type, "river_corridor")
        self.assertEqual(by_name["石岩水库"].region_type, "reservoir_zone")
        self.assertIn("coast", by_name["深圳湾"].tags)
        self.assertIn("river", by_name["茅洲河"].tags)
        self.assertIn("reservoir", by_name["石岩水库"].tags)
        self.assertIn("source_reference", by_name["石岩水库"].tags)
        self.assertIn("reference", by_name["石岩水库"].description)

    def test_reference_map_feature_weight_is_below_observed_and_detected(self):
        prepared = self._prepare(
            [
                make_entity("observed", "实测水库", "EnvironmentalCarrier", subtype="reservoir", source_kind="observed"),
                make_entity("detected", "遥感水库", "EnvironmentalCarrier", subtype="reservoir", source_kind="detected"),
                make_entity("reference", "名录水库", "EnvironmentalCarrier", subtype="reservoir", source_kind="reference"),
            ]
        )
        weights = [
            self.generator._map_seed_feature_weight(item, macro_class="water", radius_m=12000)
            for item in prepared
        ]

        self.assertGreater(weights[0], weights[1])
        self.assertGreater(weights[1], weights[2])

    def test_degraded_seed_does_not_turn_reference_density_into_regions_or_people(self):
        root = make_root()
        root.attributes["data_quality"] = {"status": "partial", "formal_ready": False}
        prepared = self._prepare(
            [
                root,
                make_entity(
                    "reference_residential",
                    "深圳参考居民片区",
                    "HumanActor",
                    subtype="residential",
                    category="facility",
                    source_kind="reference",
                    tags={"provider": "local_geographic_gazetteer"},
                    lat=22.7,
                    lon=113.9,
                ),
                make_entity(
                    "reference_water",
                    "深圳湾参考水域",
                    "EnvironmentalCarrier",
                    subtype="water",
                    source_kind="reference",
                    tags={"provider": "local_geographic_gazetteer"},
                    lat=22.4,
                    lon=114.0,
                ),
                make_entity(
                    "reference_road",
                    "深圳参考道路",
                    "Infrastructure",
                    subtype="road_corridor",
                    category="facility",
                    source_kind="reference",
                    tags={"provider": "local_geographic_gazetteer"},
                    lat=22.6,
                    lon=113.8,
                ),
            ]
        )
        prepared[0].node_family = "Region"

        regions = self.generator._build_regions_from_map_seed(
            prepared_entities=prepared,
            scenario_mode="baseline_mode",
            diffusion_template="generic",
            search_mode="fast",
        )
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

        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0].region_type, "analysis_area")
        self.assertIn("spatial_evidence_degraded", regions[0].tags)
        self.assertFalse(context.formal_spatial_ready)
        self.assertEqual(context.evidence_level, "low")
        self.assertEqual(context.human_activity_score, 0)
        self.assertIn("resident", context.forbidden_roles)

    def test_reference_residential_never_manufactures_human_activity_evidence(self):
        root = make_root()
        root.attributes["data_quality"] = {"status": "partial", "formal_ready": True}
        prepared = self._prepare(
            [
                root,
                make_entity(
                    "reference_residential_1",
                    "参考居民片区一",
                    "HumanActor",
                    subtype="residential",
                    category="facility",
                    source_kind="reference",
                    tags={"provider": "local_geographic_gazetteer"},
                ),
                make_entity(
                    "reference_residential_2",
                    "参考居民片区二",
                    "HumanActor",
                    subtype="residential",
                    category="facility",
                    source_kind="reference",
                    tags={"provider": "local_geographic_gazetteer"},
                    lat=22.01,
                    lon=114.01,
                ),
            ]
        )
        regions = [
            RegionNode(
                region_id="aoi",
                name="AOI",
                region_type="analysis_area",
                land_use_class="unknown",
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

        self.assertEqual(context.human_activity_score, 0)
        self.assertIn("resident", context.forbidden_roles)

    def test_legacy_seed_without_quality_and_unknown_provider_defaults_to_degraded(self):
        root = make_root()
        root.attributes.pop("data_quality", None)
        prepared = self._prepare(
            [
                root,
                make_entity(
                    "unknown_residential",
                    "未知来源居民区",
                    "HumanActor",
                    subtype="residential",
                    category="facility",
                    source_kind="observed",
                    tags={"provider": "unknown_provider"},
                ),
                make_entity(
                    "unknown_road",
                    "未知来源道路",
                    "Infrastructure",
                    subtype="road_corridor",
                    category="facility",
                    source_kind="observed",
                    tags={"provider": "unknown_provider"},
                    lat=22.01,
                    lon=114.01,
                ),
                make_entity(
                    "golden_reference",
                    "旧金标参考点",
                    "EnvironmentalCarrier",
                    subtype="water",
                    source_kind="reference",
                    tags={"provider": "golden_case_curated"},
                    lat=22.02,
                    lon=114.02,
                ),
            ]
        )
        prepared[0].node_family = "Region"
        regions = self.generator._build_regions_from_map_seed(
            prepared_entities=prepared,
            scenario_mode="baseline_mode",
            diffusion_template="generic",
            search_mode="fast",
        )
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

        self.assertEqual(regions[0].region_type, "analysis_area")
        self.assertFalse(context.formal_spatial_ready)
        self.assertEqual(context.human_activity_score, 0)
        self.assertEqual(context.transport_score, 0)

    def test_legacy_seed_with_only_one_reference_still_uses_map_degraded_guard(self):
        root = make_root()
        root.attributes.pop("data_quality", None)
        prepared = self._prepare(
            [
                root,
                make_entity(
                    "single_reference",
                    "静态参考片区",
                    "Region",
                    subtype="admin_district",
                    category="region",
                    source_kind="reference",
                    tags={"provider": "local_geographic_gazetteer"},
                    lat=22.03,
                    lon=114.03,
                ),
            ]
        )
        prepared[0].node_family = "Region"

        self.assertTrue(self.generator._looks_like_map_seed_context(prepared))
        regions = self.generator._build_regions_from_map_seed(
            prepared_entities=prepared,
            scenario_mode="baseline_mode",
            diffusion_template="generic",
            search_mode="fast",
        )

        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0].region_type, "analysis_area")
        self.assertNotEqual(regions[0].name, "静态参考片区")

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
            injected_variables=[],
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

    def test_effort_agent_cap_bounds_map_range_and_manual_legacy_override(self):
        prepared = self._prepare(
            [
                make_root(),
                *[
                    make_entity(
                        f"residential_{index}",
                        f"Residential blocks {index}",
                        "HumanActor",
                        subtype="residential",
                        category="facility",
                        lat=22.0 + index * 0.001,
                    )
                    for index in range(8)
                ],
            ]
        )
        regions = [
            RegionNode(
                region_id="urban_core",
                name="城市建成片区",
                region_type="urban_zone",
                land_use_class="urban",
                layer="macro",
                tags=["urban"],
                carriers=["social_contact"],
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
            search_mode="deep_search",
            max_agent_count=20,
        )

        self.assertLessEqual(context.target_count_range[1], 20)
        self.assertLessEqual(context.target_agent_count, 20)
        self.assertEqual(
            self.generator._target_agent_count(
                prepared_entities=prepared,
                regions=regions,
                subregions=subregions,
                map_evidence_context=context,
                override_target_agent_count=999,
                max_agent_count=20,
            ),
            20,
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
            injected_variables=[],
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
