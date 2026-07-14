from app.services.agent_state_mutation import (
    apply_state_delta,
    mutation_refs,
    resource_mutation_records,
)
from app.services.envfish_models import default_state_vector


def test_action_delta_produces_replayable_mutation_records():
    before = default_state_vector("disaster_mode", "Region")
    next_vector, records = apply_state_delta(
        current_vector=before,
        delta={"exposure_score": 4.0, "public_trust": -2.0},
        round_number=2,
        source_ref={"artifact_id": "agent_action_2_1", "contract_version": "agent-action.v2"},
        target_type="region",
        target_id="region_a",
        evidence_refs=["relationship:response"],
        scenario_version_ref={"artifact_id": "scenario_v1"},
    )

    assert len(records) == 2
    exposure = next(item for item in records if item["state_key"] == "exposure_score")
    assert exposure["previous_value"] == before["exposure_score"]
    assert exposure["next_value"] == next_vector["exposure_score"]
    assert exposure["delta"] == 4.0
    assert mutation_refs(records)[0]["contract_version"] == "state-mutation.v2"


def test_resource_settlement_becomes_resource_pool_mutations():
    records = resource_mutation_records(
        settlement={
            "before": {"attention": 10.0, "coordination": 5.0},
            "after": {"attention": 9.0, "coordination": 4.5},
        },
        round_number=1,
        source_ref={"artifact_id": "agent_action_1_1"},
        agent_id=1,
        evidence_refs=[],
        scenario_version_ref={"artifact_id": "scenario_v1"},
    )

    assert {item["state_key"] for item in records} == {"attention", "coordination"}
    assert all(item["target_type"] == "resource_pool" for item in records)
    assert all(item["delta"] < 0 for item in records)
