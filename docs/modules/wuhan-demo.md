# Wuhan Demo Replay

## Current Capability

The Wuhan epidemic demo is a frozen replay case for UI and workflow testing. It restores lightweight project, simulation, and report handles that point to deterministic local artifacts instead of calling an LLM, Zep, or a simulation runner.

The direct local route is `/demo/wuhan`. It restores the case and redirects to the Step 2 scenario-design page with `replay=1` and `demo_mode=frozen_replay`, so map, graph, region, Agent, and relationship UI can be tested quickly against the formal Step 2 surface.

## Key Rules

- Default restore behavior reuses an existing replay handle for the same golden case, so repeated UI testing does not create a new project and report every time.
- Add `?fresh=1` to `/demo/wuhan` when a new handle is needed for an isolated test pass.
- Add `?step=3` or `?playback=1` to `/demo/wuhan` only when the playback page itself is the target under test.
- Frozen replay artifacts are generated and validated by `backend/scripts/build_wuhan_golden_run.py`.
- The frozen animation artifact itself carries `simulation-animation.v2` plus `simulation-playback-timeline.v2`; replay does not depend on the animation API synthesizing Timeline V2 at request time.
- The frozen fixture carries a deterministic `spread_event_ledger.jsonl`. Its only root is the existing outbreak variable injected at `jianghan_market_corridor`; every later arrival follows one configured directed `transport_edge` and its `travel_time_rounds` through a first-arrival tree. Each arrival persists that transport edge as its sole `path_edge_ids` entry and keeps `related_edge_ids` empty, so fixture evidence cannot be replayed as invented extra hops.
- Frozen diffusion is curated projection data, not an observed epidemic record. The ledger and embedded Timeline V2 identify it as `golden_fixture_projection` / `curated_deterministic_fixture` with `observed=false`. Agent reactions are not attached as children unless a future fixture contains an explicit persisted causal reference.
- The frozen animation layout also identifies its deterministic coordinates as `curated_deterministic_fixture`, with `map_seed_id=null`, `coordinates_observed=false`, and a stable spatial fixture ID. These coordinates are valid for replay geometry but are not claimed as observations or a production map seed.
- A Wuhan map propagation wave requires both endpoints to carry explicit fixture coordinates and the referenced edge to be an explicitly fixture-grounded `transport_edge`. Other fixture region links remain muted schematics, while Agent and mixed links are not promoted into physical map routes.
- Restore response routes are machine navigation contracts. Their `route.name` values (for example the Step 2 and Step 3 route names) must bypass public-copy localization, while user-facing restore titles, summaries, and errors still pass through the Chinese display boundary.
- If restore or navigation fails, the Wuhan entry shows one short Chinese recovery message. It must never stringify a Vue Router location object, backend exception, or internal route name into the page.
- Frozen replay artifacts are versioned by `WUHAN_ARTIFACT_CONTRACT_VERSION` in `backend/app/services/golden_case_service.py`. If the stored manifest version is stale, `ensure_scaffold()` regenerates the deterministic artifacts before restore.
- The frozen replay path must not call LLM clients, Zep, or live simulation runners.
- The home-page Wuhan demo button should remain an intentional quick-test entry.
- Wuhan demo UI findings should be fixed in the shared product flow unless the issue is only a frozen-artifact data problem. For Step 2 map/graph issues, the shared path is `SimulationView -> GraphPanel -> MapRelationPanel` plus `/api/simulation/<id>/graph/realtime`.
- The desired product contract is parity: what the user tunes and approves in the Wuhan demo should be what a normal generated simulation shows when it produces the same projection, relation, risk-object, and playback data contracts.
- For line-style and relation-display work, update the shared graph/map components and projection metadata first, then use `/demo/wuhan` or an existing Wuhan replay simulation as the fast visual check.

## Update Policy

- Do not regenerate the Wuhan artifact just because a button style, line color, edge opacity, density cap, label display rule, map fit behavior, or shared Step 2 layout changes. Those belong in shared frontend components or shared backend projection services, and the demo should pick them up immediately.
- Regenerate the Wuhan artifact when the formal simulation data contract changes: generated region/subregion schema, Agent schema, relationship schema, risk object schema, Step 2 `ScenarioPlanningInput`/Effort/PolicyPlan/RoleDemand fields, animation frame shape, replay report contract, or any deterministic golden-case source data.
- Diffusion regeneration must preserve the Jianghan injected-variable root, directed transport-edge references, cumulative travel-time rounds, stable `event_id` / `root_event_id` / `parent_event_ids` / `hop`, and resolvable source, target, variable, and edge references. Shared round or region membership is not causal evidence.
- The Wuhan fixture map layout should avoid obvious geometry templates. Region, subregion, and Agent positions are deterministic, but they should use stable geographic jitter and role-aware spacing rather than identical triangle/spoke patterns.
- When the contract changes, bump `WUHAN_ARTIFACT_CONTRACT_VERSION`, run `cd backend && uv run python scripts/build_wuhan_golden_run.py --stage all`, then verify `/demo/wuhan`. Existing replay handles may be reused because they point at the same golden artifact root.
- `--stage all` is deterministic and does not call a live LLM in the current script, but it does rewrite the scaffold files under the configured `GOLDEN_RUNS_FOLDER/wuhan_covid_v1` root: scene seed/report, simulation config and ledgers, report artifacts, animation, and manifest. Preserve any manually curated fixture changes before running it. A stale-version restore also invokes `ensure_scaffold()` and rewrites the same files.
- Use `/demo/wuhan?fresh=1` only when testing a clean restore handle. It is not the normal way to refresh stale artifact contents.

## Maintenance Entry

- Frontend direct entry: `frontend/src/views/WuhanDemoView.vue`
- Home-page entry: `frontend/src/views/HomeView.vue`
- Restore API: `backend/app/api/golden_cases.py`
- Golden case service: `backend/app/services/golden_case_service.py`
- Validation script: `backend/scripts/build_wuhan_golden_run.py`
- Frozen diffusion ledger: `${GOLDEN_RUNS_FOLDER}/wuhan_covid_v1/simulation/spread_event_ledger.jsonl`

## Verification

- `cd backend && uv run python scripts/build_wuhan_golden_run.py --stage validate`
- `cd backend && uv run python scripts/build_wuhan_golden_run.py --stage all`
- `cd backend && uv run pytest tests/test_golden_case_service.py`
- `cd frontend && npm run build`

## History

- 2026-05-23: Added a direct Wuhan demo route and made restore reuse replay handles by default, while keeping `fresh=1` available for isolated testing.
- 2026-05-23: Recorded that Wuhan replay issues must stay connected to the formal simulation flow; Step 2 map projection fixes apply to both.
- 2026-05-23: Added the explicit parity contract that visual tuning in the Wuhan demo must reflect the formal simulation flow rather than fixture-only styling.
- 2026-05-23: Added artifact contract versioning so stale deterministic Wuhan artifacts are rebuilt when formal simulation data contracts change.
- 2026-05-23: Changed the default Wuhan demo entry to Step 2 so the fixture opens on the same scene-design surface currently used for UI and graph/map tuning; Step 3 remains available through `?step=3`.
- 2026-05-23: Replaced the repeated triangle/spoke Wuhan fixture layout with deterministic, role-aware geographic jitter and shared curved/density-managed map rendering.
- 2026-07-13: Bumped and refreshed the frozen artifact contract for the locked Effort snapshot and Step 2 scenario-planning payload (`EventMechanismGraph`, temporal plan, `PolicyPlan`, `RoleDemand`, assumptions, and Agent planning source). The deterministic offline fixture passed scaffold, freeze, and validation without an online model call.
- 2026-07-13: Preserved route descriptor names through the backend display-localization boundary and hardened the demo error fallback, preventing localized route keys or serialized router objects from breaking the Step 2/3 redirect.
- 2026-07-13: Bumped the frozen contract for Timeline V2, embedded the deterministic ledger-projected timeline in both animation artifacts, removed numeric Agent-ID reveal batching from frozen frames, and extended offline validation to check event order, references, copied-artifact equality, and deterministic rebuild hashes.
- 2026-07-14: Added an honest curated environment-diffusion ledger rooted at the existing Jianghan outbreak variable. The current deterministic transport tree covers all 12 fixture regions with 12 events and a maximum depth of five hops; validation now rejects missing ancestry, invented/non-directed edges, travel-time drift, out-of-range rounds, observed-grounding claims, and unequal animation-copy hashes.
- 2026-07-14: Added explicit spatial provenance to every frozen layout node and transport route. Step 3 can now animate the curated Wuhan diffusion tree on the map without mislabeling deterministic fixture coordinates as observed geography or relaxing synthetic-placement safeguards.
