"""Versioned contracts shared by every semantic user-input boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SEMANTIC_INPUT_CONTRACT_VERSION = "semantic-input.v1"
SEMANTIC_PROMPT_VERSION = "semantic-input.prompt.v1"

ALLOWED_EVENT_KEYS = {
    "typhoon",
    "strong_wind",
    "heavy_rain",
    "earthquake",
    "tsunami",
    "landslide",
    "liquefaction",
    "secondary_fire",
    "storm_surge",
    "flood",
    "facility_ingress",
    "power_loss",
    "cooling_failure",
    "chemical_release",
    "radioactive_release",
    "marine_spread",
    "air_spread",
    "river_spread",
    "surface_spread",
    "human_exposure",
    "ecological_impact",
    "resource_contamination",
    "medical_pressure",
    "traffic_pressure",
    "supply_pressure",
    "governance_pressure",
    "generic_event",
}

ALLOWED_POLICY_PRIMITIVES = {
    "school_closure",
    "workplace_shutdown",
    "transport_restriction",
    "shelter_in_place",
    "evacuation",
    "environmental_monitoring",
    "resource_dispatch",
    "information_release",
    "infrastructure_repair",
    "economic_compensation",
    "activity_restriction",
    "governance_intervention",
}

InputKind = Literal[
    "scene_definition",
    "scenario_configuration",
    "runtime_intervention",
    "scene_revision",
    "analysis_question",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SemanticArtifactRef(StrictModel):
    artifact_id: str
    revision: int = Field(ge=1)
    contract_version: str = SEMANTIC_INPUT_CONTRACT_VERSION
    content_hash: str
    authority: Literal["draft", "authoritative"] = "draft"


class SemanticTime(StrictModel):
    start_round: Optional[int] = Field(default=None, ge=0)
    duration_rounds: Optional[int] = Field(default=None, ge=1)
    time_text: str = ""


class SemanticIntensity(StrictModel):
    score: Optional[float] = Field(default=None, ge=0, le=100)
    direction: str = ""
    label_zh: str = ""


class SceneSemantics(StrictModel):
    location: str = ""
    time_scope: str = ""
    stable_contexts: List[str] = Field(default_factory=list)
    analysis_boundaries: List[str] = Field(default_factory=list)
    questions: List[str] = Field(default_factory=list)
    known_entities: List[str] = Field(default_factory=list)
    simulation_requirement: str = ""


class SemanticEvent(StrictModel):
    input_id: str
    raw_text: str
    name: str
    description: str
    order: int = Field(default=1, ge=1)
    atomic_keys: List[str] = Field(default_factory=list)
    open_concept: str = ""
    target_region_ids: List[str] = Field(default_factory=list)
    target_entity_ids: List[str] = Field(default_factory=list)
    target_labels: List[str] = Field(default_factory=list)
    expected_effects: List[str] = Field(default_factory=list)
    time: SemanticTime = Field(default_factory=SemanticTime)
    intensity: SemanticIntensity = Field(default_factory=SemanticIntensity)
    source_origin: str = "user_input"

    @field_validator("atomic_keys")
    @classmethod
    def validate_atomic_keys(cls, value: List[str]) -> List[str]:
        return list(dict.fromkeys(item for item in value if item in ALLOWED_EVENT_KEYS))


class SemanticPolicy(StrictModel):
    input_id: str
    raw_text: str
    name: str
    intent: str
    order: int = Field(default=1, ge=1)
    action_primitives: List[str] = Field(default_factory=list)
    executor_capability_keys: List[str] = Field(default_factory=list)
    expected_effects: List[str] = Field(default_factory=list)
    target_event_keys: List[str] = Field(default_factory=list)
    target_region_ids: List[str] = Field(default_factory=list)
    target_entity_ids: List[str] = Field(default_factory=list)
    target_labels: List[str] = Field(default_factory=list)
    time: SemanticTime = Field(default_factory=SemanticTime)
    intensity: SemanticIntensity = Field(default_factory=SemanticIntensity)
    source_origin: str = "user_input"

    @field_validator("action_primitives")
    @classmethod
    def validate_action_primitives(cls, value: List[str]) -> List[str]:
        return list(dict.fromkeys(item for item in value if item in ALLOWED_POLICY_PRIMITIVES))

    @field_validator("target_event_keys")
    @classmethod
    def validate_target_event_keys(cls, value: List[str]) -> List[str]:
        return list(dict.fromkeys(item for item in value if item in ALLOWED_EVENT_KEYS))


class SemanticIntervention(StrictModel):
    input_id: str
    raw_text: str
    type: Literal["disaster", "policy"] = "disaster"
    name: str
    description: str
    atomic_keys: List[str] = Field(default_factory=list)
    action_primitives: List[str] = Field(default_factory=list)
    target_region_ids: List[str] = Field(default_factory=list)
    target_entity_ids: List[str] = Field(default_factory=list)
    target_labels: List[str] = Field(default_factory=list)
    time: SemanticTime = Field(default_factory=SemanticTime)
    intensity: SemanticIntensity = Field(default_factory=SemanticIntensity)
    policy_mode: str = ""

    @field_validator("atomic_keys")
    @classmethod
    def validate_atomic_keys(cls, value: List[str]) -> List[str]:
        return list(dict.fromkeys(item for item in value if item in ALLOWED_EVENT_KEYS))

    @field_validator("action_primitives")
    @classmethod
    def validate_action_primitives(cls, value: List[str]) -> List[str]:
        return list(dict.fromkeys(item for item in value if item in ALLOWED_POLICY_PRIMITIVES))


class SemanticInputArtifact(StrictModel):
    contract_version: str = SEMANTIC_INPUT_CONTRACT_VERSION
    artifact_id: str
    revision: int = Field(default=1, ge=1)
    input_kind: InputKind
    authority: Optional[Literal["draft", "authoritative"]] = None
    source_hash: str
    scene: SceneSemantics = Field(default_factory=SceneSemantics)
    events: List[SemanticEvent] = Field(default_factory=list)
    policies: List[SemanticPolicy] = Field(default_factory=list)
    interventions: List[SemanticIntervention] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    previous_artifact_ref: Optional[SemanticArtifactRef] = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    content_hash: str = ""

    @model_validator(mode="after")
    def resolve_authority(self) -> "SemanticInputArtifact":
        if self.authority is None:
            self.authority = (
                "authoritative"
                if self.input_kind in {"scenario_configuration", "runtime_intervention"}
                else "draft"
            )
        return self

    def ref(self) -> SemanticArtifactRef:
        return SemanticArtifactRef(
            artifact_id=self.artifact_id,
            revision=self.revision,
            contract_version=self.contract_version,
            content_hash=self.content_hash,
            authority=self.authority or "draft",
        )


class SemanticAuditRecord(StrictModel):
    audit_id: str
    artifact_id: str
    revision: int = Field(ge=1)
    input_kind: InputKind
    prompt_version: str = SEMANTIC_PROMPT_VERSION
    processing_mode: Literal["llm", "llm_repaired", "deterministic_fallback"]
    model_name: str = ""
    elapsed_ms: int = Field(default=0, ge=0)
    repair_attempted: bool = False
    fallback_reason: str = ""
    unresolved_target_refs: List[str] = Field(default_factory=list)
    rejected_output_fields: List[str] = Field(default_factory=list)
    confidence_summary: Dict[str, Any] = Field(default_factory=dict)
    source_hash: str
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class LLMSceneOutput(StrictModel):
    scene: SceneSemantics = Field(default_factory=SceneSemantics)
    events: List[SemanticEvent] = Field(default_factory=list)
    policies: List[SemanticPolicy] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)


class LLMInterventionOutput(StrictModel):
    intervention: SemanticIntervention


class SceneSemanticPatch(StrictModel):
    location: Optional[str] = None
    time_scope: Optional[str] = None
    stable_contexts: Optional[List[str]] = None
    analysis_boundaries: Optional[List[str]] = None
    questions: Optional[List[str]] = None
    known_entities: Optional[List[str]] = None
    simulation_requirement: Optional[str] = None


class LLMRevisionPatchOutput(StrictModel):
    scene_patch: SceneSemanticPatch = Field(default_factory=SceneSemanticPatch)
    event_upserts: List[SemanticEvent] = Field(default_factory=list)
    policy_upserts: List[SemanticPolicy] = Field(default_factory=list)
    remove_input_ids: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)


class LLMQuestionOutput(StrictModel):
    interpreted_question: str
    response: str
