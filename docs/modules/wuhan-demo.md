# Wuhan Demo Replay

## Current Capability

The Wuhan epidemic demo is a versioned local case for UI and workflow testing. It restores lightweight project, simulation, and report handles that point to deterministic local artifacts instead of calling an LLM, Zep, or a simulation runner.

The direct local route is `/demo/wuhan`. It now restores `wuhan_covid_v2` and opens the populated, read-only Step 1 foundation by default. `/demo/wuhan?version=v2` remains an equivalent explicit V2 entry, while `/demo/wuhan?version=v1` preserves the frozen V1 Step 2 rollback surface.

Both V1 and V2 now compile the same production `FacilityQueryPlan` and `SpatialRefinementSnapshot` contracts used by formal Step 2. These files describe which R3 facilities and R4 internal units would still need controlled spatial verification; they do not upgrade replay geometry into verified facility evidence.

## Playback Contract And Migration

- The current frozen Wuhan animation embeds authoritative `simulation-playback-timeline.v3` global timing and round segments. Step 3 consumes that schedule as one continuous replay; it must not treat each frame or round as an independent animation clip.
- `round` is a frozen simulation checkpoint, not a replay restart boundary. At a checkpoint transition the round label and snapshot may advance, but the global playback cursor, committed graph/map state, fading route trail, camera, and view selection continue without reset.
- Older Timeline V2 artifacts remain readable through the deterministic compatibility compiler, but their client-derived schedule is not canonical V3 timing and must not be serialized or advertised as such.
- The V3 migration bumped `WUHAN_ARTIFACT_CONTRACT_VERSION`, rebuilt both frozen animation copies, and extended validation to cover monotonic global event timing, complete contiguous round segments, stable event/segment references, copied-artifact equality, and deterministic hashes.
- Frontend-only changes to the V2 compatibility compiler or renderer do not by themselves require fixture regeneration. A persisted timeline-contract or deterministic source-data change does.

## Playback Acceptance

- Enter `/demo/wuhan?step=3` and play across at least three round checkpoints in map mode and 2D mode. Neither view may clear or restart at a round boundary.
- The same source/path/arrival order, active event IDs, trail event IDs, checkpoint round, and global progress must be observable in both modes. Switching modes mid-wave must preserve the cursor and must not duplicate the wave.
- Previously reached transport routes remain as quiet cumulative context while later fixture diffusion events propagate. The map may animate only explicitly fixture-grounded transport routes; omitted synthetic Agent links are expected and are not a continuity failure.
- Pause/resume must continue from the exact cursor. Scrubbing before an event removes its pulse, event trail, and future entity visibility; scrubbing forward restores them deterministically.
- Playback stops at the final cursor without looping to baseline. Reopening the same frozen replay produces the same schedule, event order, route geometry, and final state.

Known limits: the curated diffusion tree provides a real persisted ancestry for its 12 fixture projection events, but it does not prove that Agent actions are causal descendants. Any independent Agent, relationship, or legacy V2 event remains an independent root unless the frozen ledger explicitly records its parent.

## Key Rules

- Default restore behavior reuses an existing replay handle for the same golden case, so repeated UI testing does not create a new project and report every time.
- Add `?fresh=1` to `/demo/wuhan` when a new handle is needed for an isolated test pass.
- Add `?step=3` or `?playback=1` to `/demo/wuhan` only when the playback page itself is the target under test.
- Frozen replay artifacts are generated and validated by `backend/scripts/build_wuhan_golden_run.py`.
- The frozen animation artifact itself carries `simulation-animation.v2` plus `simulation-playback-timeline.v3`; replay does not depend on the animation API synthesizing canonical global timing at request time.
- The frozen fixture carries a deterministic `spread_event_ledger.jsonl`. Its only root is the existing outbreak variable injected at `jianghan_market_corridor`; every later arrival follows one configured directed `transport_edge` and its `travel_time_rounds` through a first-arrival tree. Each arrival persists that transport edge as its sole `path_edge_ids` entry and keeps `related_edge_ids` empty, so fixture evidence cannot be replayed as invented extra hops.
- Frozen diffusion is curated projection data, not an observed epidemic record. The ledger and embedded Timeline V3 identify it as `golden_fixture_projection` / `curated_deterministic_fixture` with `observed=false`. Agent reactions are not attached as children unless a future fixture contains an explicit persisted causal reference.
- The frozen animation layout also identifies its deterministic coordinates as `curated_deterministic_fixture`, with `map_seed_id=null`, `coordinates_observed=false`, and a stable spatial fixture ID. These coordinates are valid for replay geometry but are not claimed as observations or a production map seed.
- V1 replay subregions enter the spatial-refinement evaluator only as grade `S` synthetic candidates. They may explain an unresolved request, but `covered_r3_count` must remain `0`, `selected_r3_features` must remain empty, and no R4 unit may be inferred from them.
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
- `facility_query_plan.json` and `spatial_refinement_snapshot.json` are required Step 2 artifacts in both golden manifests. Their hashes are referenced by `agent_planning_request.json`; stale or missing files make the scaffold unhealthy and trigger a deterministic rebuild.
- Diffusion regeneration must preserve the Jianghan injected-variable root, directed transport-edge references, cumulative travel-time rounds, stable `event_id` / `root_event_id` / `parent_event_ids` / `hop`, and resolvable source, target, variable, and edge references. Shared round or region membership is not causal evidence.
- The Wuhan fixture map layout should avoid obvious geometry templates. Region, subregion, and Agent positions are deterministic, but they should use stable geographic jitter and role-aware spacing rather than identical triangle/spoke patterns.
- When the V1 contract changes, bump `WUHAN_ARTIFACT_CONTRACT_VERSION`, run `cd backend && uv run python scripts/build_wuhan_golden_run.py --stage all`, then verify `/demo/wuhan?version=v1`. Existing replay handles may be reused because they point at the same golden artifact root.
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
- The 2026-07-15 contract rebuild passed `--stage all` and validation with equal animation copies: 37 frames, 696 timeline events, `clock.committed_end_ms=203000`, and animation SHA-256 `e7b22154f5d68373e6410681fe1ceaf0d2f53992867085a8f37d7be7b08e2491`.

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
- 2026-07-14: Bumped and rebuilt the Wuhan fixture for Timeline V3. Both animation copies now embed the same 203-second canonical global clock across 37 checkpoint frames and 696 events, with deterministic event/segment references, parent-before-child timing, and equal rebuild hashes.
- 2026-07-15: Bumped V1 and V2 artifact contracts for production `FacilityQueryPlan` and `SpatialRefinementSnapshot` parity. V1 synthetic geometry remains grade `S`; V2 named public anchors remain grade `D` and designed functional networks grade `S`, so neither fixture can silently satisfy an R3 requirement.
- 2026-07-15: Switched the local `/demo/wuhan` alias to the complete V2 Step 1 entry. Explicit `?version=v1` keeps the V1 Step 2 rollback path; this local routing change has not been deployed to production.

## Wuhan COVID V2 Curated Target-State Showcase

`wuhan_covid_v2` is a versioned, read-only Ultra showcase. It is intentionally compiled from editorial source data rather than generated by the current Agent planner or live runner. It is now the default local `/demo/wuhan` target; V1 remains an explicit rollback baseline through `?version=v1`.

### Routes and capabilities

- Default local entry: `/demo/wuhan`; it opens the populated V2 Step 1 foundation.
- Explicit entries: `/demo/wuhan?version=v2` keeps the same V2 behavior, while `/demo/wuhan?version=v1` opens the V1 Step 2 rollback.
- Direct checks: `/demo/wuhan?version=v2&step=1`, `step=2`, `step=3`, and `step=4`.
- Restore returns stable `foundation`, `scenario`, `runtime`, and `analysis` routes plus matching artifact references.
- `demo_mode=curated_showcase`; the case is read-only, does not expose live intervention or rerun, supports chapter navigation, and offers `复制为新推演`.
- `复制为新推演` returns to a normal editable Step 1 with the Wuhan scope, baseline, anchors, research questions, and evidence boundaries prefilled; it does not reuse the frozen runtime ledger as a new result.
- Step 3 `查看介入节点` moves the shared cursor to the nearest policy node and opens Step 4 `政策观察`; it never starts a new run.

### Source and compiler contract

Tracked editorial sources live in `backend/fixtures/golden_cases/wuhan_covid_v2/`:

- `case_manifest.json`: 36 rounds, six chapters, six storylines, eight business-state dimensions, and capability flags.
- `source_manifest.json`: eight public historical sources and their permitted claim scope.
- `spatial_anchors.geojson`: 36 differentiated public, aggregate, and functional-network anchors.
- `agent_roster.json`: 240 explicit Agent records, 72 core and 168 aggregate Agents, all 36 anchor assignments, exact system allocations, and at least 24 role archetypes.
- `story_events.jsonl`: one non-empty mainline story event for every round.
- `analysis_spec.json`: findings, turning points, five risk lifecycles, six policy observations, evidence, and uncertainty boundaries.

`backend/app/services/wuhan_showcase_builder.py` expands these sources deterministically. It must not call network services, an LLM, Zep, AgentPlanner, or a runtime. The output includes the four workflow artifacts, Agent/placement/resolution/policy plans, the production facility-query plan and spatial-refinement snapshot, frozen ledgers, a full Markdown report, and `simulation-playback-timeline.v3`.

Locked acceptance counts are 12 macro scenarios, 36 anchors, 240 Agents including 72 core Agents, 288 layout nodes, 2016 layout edges, 36 rounds, 37 frames, 203000 ms, and 696 timeline events. The dynamic ledger contains 168 unique relationships and 216 lifecycle events; 12 highlighted relationships each traverse create, activate, strengthen, weaken, and end. Each R1–R36 timeline segment exposes four to six primary editorial actions while retaining background events in the ledger. R0 is a real configuration baseline and must never fall through to the R36 snapshot.

### Evidence boundary

- Historical dates and named locations use `observed/public_source` references.
- Agent actions, relationships, continuous state curves, and mechanism links use `curated_projection`.
- For the R3/R4 refinement contract, named public anchors are still only grade `D` directory candidates and designed functional networks are grade `S` synthetic candidates. Public-source naming is not sufficient to claim authoritative facility verification; the frozen V2 snapshot therefore keeps `selected_r3_features` empty and exposes the remaining gaps.
- Aggregate actors carry `representation_level=aggregate`; no real person identity is used.
- Huanan Seafood Market is an early case-cluster anchor only and is not represented as the origin.
- Policy pages compare before/after states inside the frozen mainline. They do not claim counterfactual or causal proof.
- Step 4 exposes 175 traceable evidence groups: eight `observed/public_source` records and 167 `curated_projection` ledger records. The two groups remain visibly separated and never share an observational claim.

### Build and verification

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/build_wuhan_showcase.py verify --force
PYTHONPATH=backend backend/.venv/bin/pytest -q backend/tests/test_wuhan_showcase_v2.py backend/tests/test_golden_case_service.py
cd frontend && npm run test:workflow-architecture
cd frontend && npm run test:simulation-playback
cd frontend && npm run test:display-text
cd frontend && npm run build
```

The showcase builder must never switch route aliases. The local frontend alias now defaults `/demo/wuhan` to V2 after the semantic and visual checks; V1 remains reachable through `?version=v1`. Production deployment and any production alias change remain separate, explicit release actions.

### V2 maintenance entry

- Compiler: `backend/app/services/wuhan_showcase_builder.py`
- Validation CLI: `backend/scripts/build_wuhan_showcase.py`
- Restore and artifact API: `backend/app/services/golden_case_service.py`, `backend/app/api/golden_cases.py`
- Contract tests: `backend/tests/test_wuhan_showcase_v2.py`
- Four-step entry: `frontend/src/views/WuhanDemoView.vue`
- Shared Step 1–4 surfaces: `SceneComposerView.vue`, `KaleidoStep2.vue`, `KaleidoStep3.vue`, and `AnalysisView.vue`

This implementation and the V2 default alias change are local-only. Building or validating V2 does not switch either the local or production alias, deploy the application, or overwrite the V1 source fixture.
