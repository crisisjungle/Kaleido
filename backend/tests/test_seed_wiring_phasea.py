"""Phase A seed-wiring regression tests.

These tests prove that the on-disk map-seed handle is forwarded from
``EnvProfileGenerator.generate_from_entities`` down into
``PublicDataGroundingService.ground()`` and
``TransportContextResolver.resolve()`` so the (previously dormant) disk
grounding path is actually reachable for real map-seed runs.

They are intentionally hermetic: the grounding service and transport resolver
are replaced with light-weight spies that record the kwargs they receive, so we
assert on the *wiring* without touching the network, the filesystem, or an LLM.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.env_profile_generator import EnvProfileGenerator
from app.services.zep_entity_reader import EntityNode


class _GroundingSpy:
    """Stands in for PublicDataGroundingService; records ground() kwargs."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def ground(
        self,
        regions: Any = None,
        diffusion_template: Any = None,
        document_text: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        self.calls.append(dict(kwargs))
        # Minimal backward-compatible shape consumed by _apply_grounding_priors.
        return {
            "source": "local_fallback",
            "regions": regions or [],
            "diffusion_template": diffusion_template,
            "priors": {},
            "records": [],
            "notes": [],
        }


class _ResolverSpy:
    """Stands in for TransportContextResolver; records resolve() kwargs."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def resolve(
        self,
        regions: Any = None,
        diffusion_template: Any = None,
        reference_time: Any = None,
        preferred_provider: Any = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        self.calls.append(dict(kwargs))
        return {"provider": "spy", "flow_direction_deg": None, "note": ""}


def _make_entities() -> List[EntityNode]:
    """Two plain region-ish entities that exercise the cheap rule-based path.

    Deliberately NOT a map-seed context (no admin_context root + observed
    physical features), so generate_from_entities stays on the fast,
    LLM-free template path while still calling ground()/resolve() exactly once.
    """
    return [
        EntityNode(
            uuid="ent-1",
            name="Coastal District",
            labels=["Region"],
            summary="A coastal district near the bay.",
            attributes={"lat": 30.5, "lon": 114.3},
        ),
        EntityNode(
            uuid="ent-2",
            name="River Port",
            labels=["Region"],
            summary="A river port region.",
            attributes={"lat": 30.6, "lon": 114.4},
        ),
    ]


def _build_generator() -> tuple[EnvProfileGenerator, _GroundingSpy, _ResolverSpy]:
    grounding_spy = _GroundingSpy()
    resolver_spy = _ResolverSpy()
    generator = EnvProfileGenerator(llm_client=None, grounding_service=grounding_spy)
    # Replace the resolver instance with our spy (constructor builds a real one).
    generator.transport_context_resolver = resolver_spy
    # Force the rule-based, LLM-free code paths regardless of environment.
    generator.llm_client = None
    return generator, grounding_spy, resolver_spy


def test_seed_handle_forwarded_to_ground_and_resolve() -> None:
    generator, grounding_spy, resolver_spy = _build_generator()

    generator.generate_from_entities(
        entities=_make_entities(),
        simulation_requirement="explore relations",
        document_text="",
        diffusion_template="marine",
        use_llm=False,
        parallel_count=1,
        map_seed_id="seed_abc123",
    )

    assert grounding_spy.calls, "ground() was never invoked"
    assert resolver_spy.calls, "resolve() was never invoked"

    # The seed handle must be threaded as the documented kwarg the disk path reads.
    assert grounding_spy.calls[0].get("seed_id") == "seed_abc123"
    assert resolver_spy.calls[0].get("seed_id") == "seed_abc123"


def test_explicit_seed_dir_is_forwarded() -> None:
    generator, grounding_spy, resolver_spy = _build_generator()

    generator.generate_from_entities(
        entities=_make_entities(),
        simulation_requirement="explore relations",
        document_text="",
        diffusion_template="marine",
        use_llm=False,
        parallel_count=1,
        map_seed_id="seed_abc123",
        seed_dir="/tmp/map_seeds/seed_abc123",
    )

    assert grounding_spy.calls[0].get("seed_id") == "seed_abc123"
    assert grounding_spy.calls[0].get("seed_dir") == "/tmp/map_seeds/seed_abc123"
    assert resolver_spy.calls[0].get("seed_dir") == "/tmp/map_seeds/seed_abc123"


def test_no_seed_keeps_grounding_kwargs_empty() -> None:
    """Guard: without a seed handle the dormant path stays dormant (unchanged)."""
    generator, grounding_spy, resolver_spy = _build_generator()

    generator.generate_from_entities(
        entities=_make_entities(),
        simulation_requirement="explore relations",
        document_text="",
        diffusion_template="marine",
        use_llm=False,
        parallel_count=1,
        # map_seed_id intentionally omitted
    )

    assert grounding_spy.calls, "ground() was never invoked"
    assert resolver_spy.calls, "resolve() was never invoked"
    assert "seed_id" not in grounding_spy.calls[0]
    assert "seed_dir" not in grounding_spy.calls[0]
    assert "seed_id" not in resolver_spy.calls[0]
    assert "seed_dir" not in resolver_spy.calls[0]
