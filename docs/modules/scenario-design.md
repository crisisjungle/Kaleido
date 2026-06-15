# Scenario Design

## Current Capability

The Step 2 scenario design workspace is split into an input stage and a generated-display stage.

Users first confirm simulation parameters. After confirmation, the parameter form is locked and the generated display tabs become available: risk object preview, region division, Agent configuration, and relationship skeleton.

## Key Rules

- The user no longer chooses between baseline and crisis simulation modes. The frontend derives the scenario mode from the submitted variables, and the backend still receives a normalized `scenario_mode`.
- Time plan and tuning template selection are automatic by default. The frontend matches the hazard template and transport family from variable text, then derives a time step and round count.
- Users may still adjust time step unit, time step size, and total simulation rounds before confirmation.
- The former standalone mechanism-test toggle is folded into search mode. `快速搜索` uses the template-oriented `legacy_envfish_v1` path, while `深度搜索` submits `llm_mechanism_v1`.
- Environment baseline is generated/display data. It is shown under the region display tab and must not be treated as a user-editable variable.
- Step 2 must not auto-submit on mount. Confirmation is the boundary that starts generation and locks the input form.
- Risk object previews are generated as scenario-derived tracking objects, not a single generic label. The builder should produce multiple grounded risks when the scene contains distinct hazard carriers, exposed regions, affected actors, infrastructure paths, or response-capacity concerns.
- Risk scores have explicit meanings: `severity_score` is a 0-100 scenario impact score, `confidence_score` is a 0-1 grounding confidence score, and `actionability_score` is a 0-100 estimate of whether the object has clear monitoring/intervention handles.
- Risk objects should carry enough structure for the Step 2 preview: scoped regions, related actors/entities, affected clusters, chain steps, turning points, evidence, intervention templates, and scenario branches.
- In Chinese mode, Step 2 and the graph preview should avoid exposing raw internal labels when a stable Chinese label exists. Region tags such as `macro`, `coastal_zone`, `river_basin`, and `flood_risk` should render as Chinese.
- Region "agent coverage" is not the same as total agents. Total agents counts unique configured proxy bodies, while region coverage is a per-region aggregate across primary and influenced regions, so one agent may count in multiple region cards.
- The Agent panel should describe graph-derived records as temporary graph previews, not as a failure or degradation state.
- The Step 2 left map must render the same generated region, subregion, agent, and relationship projection used by the Step 2 result tabs. Demo fixtures such as the Wuhan replay and normal prepared simulations should share `SimulationView -> GraphPanel -> MapRelationPanel` and `/api/simulation/<id>/graph/realtime`.
- Fixes found through the Wuhan demo are product-flow fixes unless the issue is explicitly fixture-only.
- Visual tuning must preserve parity between fixture and formal flow. Line colors, line density rules, node halos, highlighted risk paths, relation filtering, and map/2D/3D mode behavior should live in shared Step 2/3 graph components or shared backend projection contracts. Do not patch only the Wuhan fixture to make it look right.
- If Step 2 changes the generated graph/risk/agent data contract, refresh the Wuhan golden artifact contract version. If Step 2 only changes shared rendering behavior, verify with Wuhan demo without rebuilding the frozen artifact.
- Map relation layouts should avoid obvious repeated geometry templates. Deterministic jitter is acceptable and preferred for repeatable tests, but repeated same-direction triangles, spokes, and identical agent glyphs should be treated as fixture or projection defects.

## Maintenance Entry

- Frontend component: `frontend/src/components/KaleidoStep2.vue`
- Simulation prepare API: `backend/app/api/simulation.py`
- Config generator: `backend/app/services/env_simulation_config_generator.py`

## History

- 2026-05-21: Split Step 2 into editable parameters before confirmation and generated display tabs after confirmation; folded deep search into the LLM mechanism path and moved environment baseline out of the editable parameter area.
- 2026-05-21: Replaced the compatibility-only single risk definition with deterministic multi-risk generation based on scenario variables, region tags, Agent roles, and text signals; preserved the generated fields through legacy risk object projection.
- 2026-05-21: Localized Step 2 region/agent/graph labels, clarified agent coverage versus total agents, and grouped region-card tags by purpose so the preview is readable in Chinese mode.
- 2026-05-23: Reconnected Step 2 map rendering to the shared realtime map projection so Wuhan frozen replay and normal simulations both show generated nodes and relation overlays on the left map.
- 2026-05-23: Clarified the demo/formal-flow parity rule: Wuhan replay is the quick visual fixture for the same shared Step 2 graph and map behavior that formal generated simulations use.
- 2026-05-23: Added the golden artifact refresh rule: data-contract changes require a Wuhan fixture version bump; renderer-only changes should stay shared and not trigger high-cost regeneration.
- 2026-05-23: Added the organic map-layout rule and tuned shared Step 2 map rendering away from repeated triangle/spoke patterns.
