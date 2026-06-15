# Wuhan Demo Replay

## Current Capability

The Wuhan epidemic demo is a frozen replay case for UI and workflow testing. It restores lightweight project, simulation, and report handles that point to deterministic local artifacts instead of calling an LLM, Zep, or a simulation runner.

The direct local route is `/demo/wuhan`. It restores the case and redirects to the Step 2 scenario-design page with `replay=1` and `demo_mode=frozen_replay`, so map, graph, region, Agent, and relationship UI can be tested quickly against the formal Step 2 surface.

## Key Rules

- Default restore behavior reuses an existing replay handle for the same golden case, so repeated UI testing does not create a new project and report every time.
- Add `?fresh=1` to `/demo/wuhan` when a new handle is needed for an isolated test pass.
- Add `?step=3` or `?playback=1` to `/demo/wuhan` only when the playback page itself is the target under test.
- Frozen replay artifacts are generated and validated by `backend/scripts/build_wuhan_golden_run.py`.
- Frozen replay artifacts are versioned by `WUHAN_ARTIFACT_CONTRACT_VERSION` in `backend/app/services/golden_case_service.py`. If the stored manifest version is stale, `ensure_scaffold()` regenerates the deterministic artifacts before restore.
- The frozen replay path must not call LLM clients, Zep, or live simulation runners.
- The home-page Wuhan demo button should remain an intentional quick-test entry.
- Wuhan demo UI findings should be fixed in the shared product flow unless the issue is only a frozen-artifact data problem. For Step 2 map/graph issues, the shared path is `SimulationView -> GraphPanel -> MapRelationPanel` plus `/api/simulation/<id>/graph/realtime`.
- The desired product contract is parity: what the user tunes and approves in the Wuhan demo should be what a normal generated simulation shows when it produces the same projection, relation, risk-object, and playback data contracts.
- For line-style and relation-display work, update the shared graph/map components and projection metadata first, then use `/demo/wuhan` or an existing Wuhan replay simulation as the fast visual check.

## Update Policy

- Do not regenerate the Wuhan artifact just because a button style, line color, edge opacity, density cap, label display rule, map fit behavior, or shared Step 2 layout changes. Those belong in shared frontend components or shared backend projection services, and the demo should pick them up immediately.
- Regenerate the Wuhan artifact when the formal simulation data contract changes: generated region/subregion schema, Agent schema, relationship schema, risk object schema, animation frame shape, replay report contract, or any deterministic golden-case source data.
- The Wuhan fixture map layout should avoid obvious geometry templates. Region, subregion, and Agent positions are deterministic, but they should use stable geographic jitter and role-aware spacing rather than identical triangle/spoke patterns.
- When the contract changes, bump `WUHAN_ARTIFACT_CONTRACT_VERSION`, run `cd backend && uv run python scripts/build_wuhan_golden_run.py --stage all`, then verify `/demo/wuhan`. Existing replay handles may be reused because they point at the same golden artifact root.
- Use `/demo/wuhan?fresh=1` only when testing a clean restore handle. It is not the normal way to refresh stale artifact contents.

## Maintenance Entry

- Frontend direct entry: `frontend/src/views/WuhanDemoView.vue`
- Home-page entry: `frontend/src/views/HomeView.vue`
- Restore API: `backend/app/api/golden_cases.py`
- Golden case service: `backend/app/services/golden_case_service.py`
- Validation script: `backend/scripts/build_wuhan_golden_run.py`

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
