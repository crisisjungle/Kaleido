# Workflow Information Architecture

## Product Flow

Kaleido uses one four-step business flow. Step names describe stable user goals rather than page implementations:

1. `背景定义`: define the location, steady context, source material, question, and the five-level analysis budget used by all later generation. The accepted Effort snapshot is locked for the whole run.
2. `场景生成`: confirm initial conditions, generate a runnable scenario, and review its regions, formal agents, relationship skeleton, and risk definitions.
3. `推演运行`: observe round-by-round evolution and apply optional runtime interventions.
4. `分析与报告`: explain what happened, trace evidence, and deliver the result.

The durable data boundary is:

```text
Step 1 map evidence, scene material, and locked Effort snapshot
  -> Step 2 event/mechanism plan and runnable scenario configuration
  -> Step 3 runtime states, events, dynamic relationships, and interventions
  -> Step 4 analysis and report artifacts
```

Step 1 inferred map nodes, Step 2 formal agents, and Step 3 runtime states are different layers and must not share a single ambiguous “agent generation” label.

## Flow States

The normal state sequence is:

```text
background draft
-> background generation
-> background review
-> scenario configuration
-> scenario generation
-> scenario review
-> simulation running / paused
-> simulation stopped / completed
-> analysis generation
-> results ready
```

A failure branches from the current stage. Keep the last valid input or generated artifact available for a scoped retry.

## Result-First Output Contract

The formal product presents validated business results directly and does not report whether its internal processing succeeded or failed. Success is the default precondition for showing a result, not a separate piece of user-facing content. A generated map is shown as a map, a resolved event is shown as an event, a prepared Agent set is shown as an Agent table, and a completed report opens as the report; none requires an additional success banner, Toast, badge, or explanation.

Testing and operational diagnostics may expose completion states, failures, retries, model routes, confidence, fallback paths, unresolved references, and structured errors. Those signals remain in task state, logs, audit artifacts, automated tests, and optional diagnostic surfaces. They do not become business copy in the formal Step 1-4 workflow.

System logs are an explicit test/debug surface and may truthfully show those internal processing outcomes. Formal business components must consume structured artifacts and state instead of copying log messages into banners, Toasts, result summaries, or activity feeds.

Result-first does not permit fabricated success. Only validated results may enter the business surface. While no valid result exists, preserve the user's input and the last valid artifact, continue internal recovery where possible, or expose a task action such as `继续生成`, `重新获取`, `调整范围`, or `返回修改`. Do not turn the internal execution judgment itself into the product output.

The full cross-step contract, examples, environment boundary, and acceptance rules are maintained in `docs/modules/result-first-output.md`.

## Unified Interface Rules

- All four steps use `KaleidoWorkflowShell`, the same 60px product header, the same four-step menu, and one green brand-token system. Blue is not an action or selected-state color in the workflow.
- Desktop workspaces use a deliberate graph/workbench split rather than independent page layouts. Mobile switches between two full-width local views instead of squeezing both panes together.
- The right workbench is already the page surface. A child element may own scrolling or layout, but it must not draw another full-height rounded background, border, or shadow around the whole active page. Use section dividers for reading hierarchy; reserve a bounded card surface for a real selectable/comparable record, not for a wrapper around other containers.
- Primary navigation uses `KWorkflowTabs`. Step 2 may use rich tabs with counts because its four result types are peer business objects; Step 3/4 use compact tabs; nested views with many choices use one select or a drawer instead of another horizontal tab row.
- A step has one progress representation for the same state. Do not render a legacy range and a new progress bar together.
- Primary step actions stay in one workbench-internal tail bar. In Steps 1-3 the middle business surface is the only scroll container and the action bar is its flex sibling, so it remains visible without using viewport `fixed` positioning or covering content. The bar has one top divider and no rounded outer container, four-side border, shadow, or bottom gap. Step 4 does not render an empty bar when there is no real cross-step action. The header contains context and infrequent secondary actions, not a second competing action group.
- Tags are secondary metadata. Use thin outline tags, neutral surfaces, and the green accent only for selected or positive state. Show no more than two or three representative tags inline and collapse the remainder into `+N`, a table detail row, or a drawer.
- Repeated structured records use `KDataTable` when comparison is the task. Detail-heavy records open in a drawer; compact cards are reserved for genuinely small summaries.
- Explanatory copy must justify its space. Empty-state guidance, error recovery, and evidence caveats remain; duplicated descriptions, implementation notes, and system logs do not belong in the business surface.
- Normal completion transitions directly from process UI to the business result. Do not add success Toasts, success banners, completion badges, or copy that merely announces that the result was generated.

## Display Text Boundary

- Machine identifiers, enum keys, class names, artifact paths, and relationship keys remain available for computation but are never display fallbacks.
- Backend public responses project user-facing fields into Simplified Chinese and sanitize historical artifacts at the response boundary. New LLM-produced artifacts also require Chinese display fields before persistence.
- Frontend display paths use `frontend/src/utils/displayText.js` as the final defensive boundary. An unknown English token, internal ID, numeric-only name, path, address, or punctuation-only fragment is omitted or replaced with a specific Chinese fallback; it is never returned unchanged.
- Map tooltips, graph details, risk evidence, region metadata, runtime narratives, analysis tabs, progress messages, and error states follow the same rule. Public responses drop traceback/debug fields, and public errors never expose exception classes, API paths, local paths, network addresses, or raw backend messages.
- Formal-report Markdown has a dedicated boundary: preserve headings, lists, paragraphs, and line breaks while removing tool-call blocks, fenced payloads, internal enum tokens, machine paths, and unsupported English fallbacks. Do not flatten an entire report into one paragraph as part of localization.
- Every JSON response from the simulation blueprint passes through the public display projection after the route handler. This safety net covers legacy response shapes for create/list/history, prepare, configuration, runtime control, injection, and analysis endpoints without changing their machine fields; traceback/debug fields are removed before serialization.
- Public report console/agent-log endpoints return projected Chinese status summaries only. Tool names, parameters, prompts, model responses, local paths, network addresses, exception classes, and internal IDs remain server diagnostics and never cross the public log contract.

## Effort Lifecycle

- Step 1 is the only place where the user chooses `Light / Medium / High / Extra High / Ultra`; these are intentional English product labels, not leaked backend copy. The stored machine values remain `light / medium / high / extra_high / ultra`, and `High` is the default display level. The compact `分析强度` control stays beside the bottom-right background-generation action and reads its visible text from the explicit frontend display mapping rather than directly rendering an API value.
- The first accepted background-generation request returns and locks `effort_snapshot_id`, `effort_level`, `profile_version`, and `content_hash`. Route queries are not a persistence mechanism.
- Retry, regeneration, back navigation, and every later step reuse the same snapshot. Step 2 shows the locked analysis-investment level in Chinese and rejects a missing or conflicting reference.
- Mid-flow or runtime Effort changes are intentionally not supported in this release. A future migration/rebuild design is required before that capability may be added.

## Step 2 Rules

- Configuration, generation, and review are mutually exclusive user-facing states.
- Configuration follows one task order: scenario goal summary, disaster event chain, policy measures, automatic-plan summary, optional advanced corrections, and a fixed confirm action.
- Event input exposes only name, description, order, and target regions/facilities. Policy input exposes only name, intent, and target regions/facilities. Compound sentences may be split into an editable ordered event chain.
- Templates, quick/deep search, mechanism sample count, Agent target count, event start/duration, and raw numeric intensity are not ordinary user choices. The mechanism architecture is fixed for new requests; `deep_search` survives only as an internal compatibility field.
- Time stages, propagation latency/duration, derived intensity, and policy-effective windows are automatic. Advanced correction is limited to time/coverage, event windows/intensity, and region/facility targets; it cannot change Effort, Token limits, Agent count, or relationship-search parameters.
- Do not show zero-count risk, region, agent, or relationship result cards before generation completes.
- The confirm-and-generate action stays outside the scrolling form.
- Generation replaces the form with progress and the actual sequence: compound-event parsing, mechanism/propagation graph construction, temporal/spatial planning, role-capability extraction, Agent/relationship generation, and final assembly/validation. Any left-graph update is labeled as a generation preview.
- Review uses peer tabs for risk definitions, region structure, Agents, and relationship network. Only the active result view is rendered.
- Risk review uses a compact horizontal selector above one full-width selected detail. Selector items contain only identity, family/mode, the primary state, and the two comparison scores; explanations, mechanism chains, affected subjects/regions, evidence, and metrics belong only to the selected detail. When all items fit, no navigation buttons are rendered. Only actual horizontal overflow introduces two small previous/next buttons while retaining trackpad and touch scrolling.
- The frontend renders the complete risk collection returned by the current contract and must not use a fixed `.slice(0, 8)` or an Effort-based display cap. The current V2 backend may still limit active objects to eight, while dormant/history records and future contracts can produce a larger visible collection; the UI must remain usable for ten or more items.
- Risk details use flat rows and dividers. Vertical risk-card walls, blue nested panels, tag walls, machine identifiers, and narrow split columns that force the causal chain to wrap into unreadable fragments are not valid review layouts.
- Agent review is comparison-first. Large generated sets use a compact paginated table with a bounded number of rows; they must never render hundreds of Agent cards into one scroll surface.
- Locked inputs are available through a separate read-only entrance.
- `ScenarioPlanner` outputs an event mechanism graph, temporal plan, `PolicyPlan`, `RoleDemand`, assumptions, and compatibility metadata. Assumptions remain available in the planning artifact for audit but are not shown as a standalone “本次自动规划采用的假设” block. `PolicyPlan` does not select a concrete executor; `RoleDemand` never contains Agent IDs or a target count.
- The reviewed event mechanism graph and temporal plan remain authoritative during configuration assembly and runtime initialization. Legacy hazard templates and transport families are projections for old consumers; they cannot collapse a compound scene to one hazard or one propagation medium.
- Agent generation crosses one boundary: `ScenarioPlanningInput -> AgentPlanningPort`. The current `LegacyAgentPlanningAdapter` preserves the existing generator and marks its source; Agent V2 may later replace the port without redefining Step 2.
- Preparing the same planning hash twice reuses the active task. A conflicting hash is rejected until the active task finishes, preventing concurrent writes to one simulation.
- Historical `injected_variables` remain readable through compatibility conversion and are never rewritten automatically.
- System logs are internal diagnostics and do not belong in the Step 2 business surface.
- This release does not include Agent V2, policy-executor binding, Step 3 runtime decisions, runtime variable injection, chat clarification, mid-flow Effort changes, or Step 4 report redesign.

## Step 3 Rules

The runtime surface has three layers:

1. Persistent transport: one progress rail, one percentage, and one play/pause action. Round, stage, scenario state, and simulated time are represented by the rail and downstream observations instead of four duplicate status cards.
2. Peer observation views: `运行脉冲`, `状态与行动`, `扩散与反馈`, `代理工作台`, and `关系与风险`.
3. Runtime intervention drawer: create an intervention, inspect active interventions, and review history.

Only the active observation view scrolls. The left runtime graph and compact transport remain visible. Previous/next/latest, millisecond speed, and generic state-dimension controls are not normal user choices. System logs are internal diagnostics and do not belong in the business interface.

`状态与行动` currently uses recorded agent interactions/actions. Do not label it “决策” until the runtime contract includes explicit decision candidates, selected decisions, and rationales.

## Step 4 Rules

Step 4 has five stable primary views:

1. `结论总览`: a real summary derived from the report overview and round narratives.
2. `演化复盘`: round narrative, region state, role lens, and feedback-chain subviews.
3. `风险与机制`: risk counts, mechanism variables, mechanism chains, relation samples, and reasoning records.
4. `证据探索`: graph-linked node context, provenance, evidence references, deep exploration, and follow-up questions.
5. `正式报告`: the generated Markdown deliverable and its generation state.

On desktop, the Step 4 hero and primary navigation remain visible while only the active view scrolls. Mobile falls back to normal document scrolling.

Step 4 reads as one continuous analysis sheet. The hero, lead conclusion, evidence sections, replay sections, exploration wrappers, and formal-report wrapper are flat sections separated by rules. Repeated records such as a region metric or feedback item may retain a compact item surface, but a section wrapper cannot become another card around those records. The formal report renders directly into the active reading surface rather than inside both a report-shell card and a report-panel card.

The four `演化复盘` views are navigation, not a data filter. They must remain visible as one horizontal text-tab row at every width and may scroll horizontally when space is tight; they must never collapse into a native select. `角色透镜` uses flat comparison rows for the four role groups, showing node count, core state averages, and the leading affected region without representative-node tag walls or nested cards.

`风险与机制` is a continuous analysis sheet. Counts are inline metadata, the scenario summary is plain lead text, and non-empty data groups are separated by rules rather than surface cards. State variables are shown in full as rows (`变量 / 方向 / 说明`); mechanism edges, relation samples, and reasoning rounds may show a clearly labelled bounded preview. Empty groups are omitted, so a fixture with mechanism edges but no variables or reasoning records does not produce zero-count containers.

Analysis availability and report completion are different states. Runtime artifacts may make analysis available while the formal report is still `pending`, `planning`, or `generating`; Step 4 is only marked complete when the formal report reaches `completed`. The report surface polls its current report and progress until `completed` or `failed`, clears polling when unmounted, and reloads the final Markdown without requiring a tab switch or page refresh.

Legacy query values `narrative`, `feedback`, `regions`, and `roles` continue to open the matching `演化复盘` subview. The `/report/:reportId` and `/interaction/:reportId` redirects continue to open `正式报告` and `证据探索` respectively.

Role-lens region summaries render only resolved Chinese region names. Internal region IDs and placeholders such as `未命名区域` are omitted; when no real region can be resolved, the whole subsection is hidden rather than presenting invented analysis detail.

## Graph Meaning By Step

- Step 1: map and real-world evidence.
- Step 2: generated scenario-definition network.
- Step 3: runtime evolution network.
- Step 4: result and evidence graph.

Each surface should make its graph meaning clear and keep right-side selections linked to left-side highlights.

## Maintenance Entry

- Shared UI design system: `docs/modules/ui-design-system.md`
- Workflow navigation: `frontend/src/store/workflowNavigation.js`
- Step 2: `frontend/src/components/KaleidoStep2.vue`
- Step 2 planner and Agent compatibility port: `backend/app/services/scenario_planner.py`
- Shared Effort contract: `backend/app/services/effort_contract.py`
- Step 3: `frontend/src/components/KaleidoStep3.vue`
- Step 3 shell: `frontend/src/views/SimulationRunView.vue`
- Step 4: `frontend/src/views/AnalysisView.vue`
- Step 4 formal report: `frontend/src/components/Step4Report.vue`
- Shared workflow shell: `frontend/src/components/KaleidoWorkflowShell.vue`
- Shared workflow UI primitives: `frontend/src/components/ui/`
- Shared visual tokens: `frontend/src/styles/tokens.css`
- Frontend display-text boundary: `frontend/src/utils/displayText.js`
- Backend public-display projection: `backend/app/services/display_localization.py`
- Simulation-wide response boundary: `backend/app/api/simulation.py`
- Public report/log projection: `backend/app/api/report.py`
- Display-boundary regression tests: `frontend/scripts/display-text-regression.mjs`, `backend/tests/test_display_localization.py`, `backend/tests/test_generation_display_localization.py`

## History

- 2026-07-12: Standardized the four step names and documented the end-to-end data boundary.
- 2026-07-12: Rebuilt Step 2 around mutually exclusive configuration, generation, and review states.
- 2026-07-12: Rebuilt Step 3 around persistent runtime controls, five peer observation views, and a separate runtime-intervention drawer; removed system logs from the business UI.
- 2026-07-13: Reorganized Step 4 into five stable primary views, added a real conclusion overview, kept desktop context/navigation visible, and repaired formal-report polling so pending reports refresh into completed or failed states without a page reload.
- 2026-07-13: Fixed Effort as a Step 1-only, five-level locked snapshot and redefined Step 2 around compound event/policy input, mechanism and temporal planning, `PolicyPlan`, `RoleDemand`, and a replaceable Agent planning port. Mid-flow Effort changes and runtime variable injection remain deferred.
- 2026-07-13: Unified Step 1-4 around one workflow shell, green tokens, shared tabs/progress/tables, bottom action bars, outline metadata tags, and responsive split-pane rules. Added a strict display-text boundary so historical backend artifacts and unknown machine tokens cannot surface as raw English or internal IDs.
- 2026-07-13: Extended the display boundary to reject numeric-only names, punctuation fragments, exception/path/address leakage, and private traceback/debug fields. Added structure-preserving Markdown report cleanup so tool-call payloads and internal tokens are removed without collapsing report layout.
- 2026-07-13: Added a blueprint-wide simulation JSON response projection and safe report-log DTOs. Legacy configuration, prepare/start/stop/inject, list/history, and report-log paths can no longer bypass localization or return raw diagnostic payloads.
- 2026-07-13: Reduced Step 3 persistent transport to one progress rail, percentage, and play/pause action; removed duplicate runtime cards and implementation-level playback selectors so the observation workspace keeps its vertical space.
- 2026-07-13: Bounded large Step 2 Agent review behind a compact paginated table and removed unresolved Step 4 role-lens region placeholders from the visible analysis surface.
- 2026-07-13: Replaced the four-view Step 4 replay select with always-visible peer tabs, flattened role comparison and risk/mechanism content into row-based reading flows, removed empty mechanism sections, and fixed the six-variable fixture being truncated to five visible items.
- 2026-07-13: Replaced Step 2's vertical risk-card wall with an uncapped horizontal selector and one full-width selected detail, made carousel buttons conditional on real overflow, removed the visible assumptions block and nested tag-heavy risk panels, and standardized Steps 1-3 on the same non-floating workbench tail bar.
- 2026-07-13: Removed the decorative full-height rounded shell from Step 2 while preserving it as the single scroll boundary, and flattened Step 4 section/report wrappers into one divider-led reading surface. Item-level comparison cards remain only where they carry a real record.
- 2026-07-13: Added a shared seven-step typography scale for Step 1–4, removed browser-default 16px copy from workflow roots, capped primary workbench headlines at 20px, and documented the green theme, text roles, density rules, and browser verification contract.
- 2026-07-14: Completed all-tab browser QA for Step 1–4, weakened remaining Step 4 source badges to transparent outline tags, and added deterministic formal-report heading de-duplication so legacy Markdown cannot repeat the delivery title or a section title on consecutive lines.
