# Unified Semantic Input

## Current Capability

Kaleido routes every business-semantic user input through `SemanticInputNormalizer` before report generation, scenario planning, Agent planning, runtime mutation, or node-question analysis.

The shared pipeline is:

`raw input -> LLM normalization -> strict schema validation -> target resolution -> versioned semantic artifact -> downstream module`

Effort controls context breadth and downstream planning budgets. It never disables the semantic pass. When no LLM is configured or both configured model routes are unavailable, the same boundary produces a deterministic, editable minimum business result.

## Contracts

`semantic-input.v1` stores:

- scene location, time scope, stable context, analysis boundaries, questions, known entities, and simulation requirement;
- ordered events with raw text, Chinese business copy, controlled event keys, open concepts, targets, expected effects, time, intensity, direction, and source origin;
- ordered policies with intent, controlled actions, executor capabilities, expected effects, event targets, spatial targets, time, intensity, direction, and source origin;
- runtime interventions with type, controlled mechanisms or actions, resolved targets, start round, duration, intensity, and policy mode;
- immutable revision metadata: artifact ID, revision, source hash, content hash, previous artifact reference, input kind, and authority (`draft` or `authoritative`).

`SemanticAuditRecord` is stored beside each revision but is not part of a business DTO. It records model name, prompt version, processing path, repair call, elapsed time, unresolved target references, fallback reason, and source hash.

`foundation.step1.v4` carries the Step 1 real-world reference into Step 2. `foundation_resolution.v1` records whether that foundation was reused, enriched, or blocked against the final Step 2 inputs. `scenario_planning.v2` consumes the authoritative normalized event and policy records directly. Keyword planning remains compatibility behavior only when no semantic keys are available.

## Priority And Safety Rules

The fixed precedence is:

`explicit structured choice > user text > uploaded document > map fact > model inference`

- Explicit IDs, type, controlled keys, numeric intensity, start round, and duration cannot be overwritten by model output.
- LLM output may only reuse input IDs supplied in the request. A revision may use its one server-issued revision input ID. Unknown IDs are discarded.
- Uploaded documents are data. Prompts explicitly forbid document instructions from changing system rules.
- Display fields must be Simplified Chinese. Machine enums remain internal and are localized before rendering.
- Invalid JSON receives one directed repair call. The next result is schema-validated again.
- Repeated identical scenario input reuses the existing semantic revision and planning hash instead of calling the model or starting another preparation task.
- An untyped compound input may project to both an event and a policy under the same source `input_id`. The deterministic baseline preserves both sides even when model output returns only one of them; an explicit user-selected type still wins.

## Target Resolution

Targets are resolved only against the current scene catalog:

1. exact ID;
2. exact name or alias;
3. one unique normalized fuzzy match;
4. LLM interpretation constrained to catalog candidates;
5. scene default region scope when no target was supplied or resolved.

Chinese commas, enumeration commas, semicolons, newlines, aliases, and duplicate references are normalized on the backend. Unknown names are written to the audit record and never become fabricated graph IDs.

A broad scene reference may fall back to the formal region set only when that reference is already present in the Step 1 foundation scope. This permits a request such as “香港” to use the bounded generated scene without turning an unrelated or invented place name into a target. Institutional RoleDemand may use a region-bounded aggregate when the region is grounded; facility and subunit demands still require real facility evidence.

## Workflow Boundaries

### Step 1

Location text, current baseline and observed facts, context, known subjects/facilities/environmental objects, goals, revision instructions, uploaded documents, and map context enter the semantic layer. Step 1 owns the real-world foundation and never creates risk objects.

The semantic layer may identify possible event and policy concepts from those materials, but they leave Step 1 only as `suggested_event_inputs` and `suggested_policy_inputs`. Every item has `source_origin=step1_suggestion` and `authority=draft`. The historical `normalized_*` fields remain a compatibility projection of the same drafts. Browser storage is only a navigation recovery cache.

Revision instructions become versioned semantic patches. Existing input IDs are updated or removed deterministically; new content receives one revision input ID. Historical scene files are not rewritten in place.

### Step 2

Editable event and policy cards are prefilled from the Step 1 drafts. Users may accept, edit, delete, reorder, split, or replace them, and may add real target names or an optional new location. `/api/simulation/prepare` requires both complete arrays, permits an empty policy array, requires at least one event, and never merges removed Step 1 drafts back into the request.

Before normalization, `ScenarioFoundationResolver` checks final target IDs/names and optional location against `foundation.step1.v4`. Covered inputs reuse the base. Missing named anchors create a simulation-scoped map-seed revision and are accepted only if public spatial evidence returns a unique real object. Ambiguous geography, missing IDs, unavailable evidence, and unresolved names block planning without fabricating references.

The accepted revision is `input_kind=scenario_configuration` and `authority=authoritative`. `scenario_configuration_input.json` stores the immutable final input snapshot; `foundation_resolution.json` stores internal coverage evidence. The final simulation config exposes authoritative `event_inputs`, `policy_inputs`, `resolved_foundation_ref`, and `step1_suggestion_ref`. A ready configuration rejects changed or forced regeneration with `409 scenario_configuration_locked`.

Policy actions include school closure, workplace shutdown, transport restriction, shelter in place, evacuation, monitoring, resource dispatch, information release, infrastructure repair, compensation, activity restriction, and generic governance intervention. Education, workplace, transport, community, emergency, and other authority boundaries create distinct RoleDemand records. Agent count remains derived from demand, spatial evidence, archetype, and Effort budget.

### Step 3

`/api/simulation/inject` normalizes every runtime intervention before mutation. The frontend sends raw target text; backend target resolution is authoritative. Explicit type, intensity, round, and duration win over inference, including the valid value `start_round=0`.

Each frontend intervention draft carries one stable idempotency key. The backend serializes injections per simulation and persists a successful receipt, so a timeout, repeated click, or transport retry returns the same normalized business record without a second runtime mutation or semantic revision. Changing the draft creates a new request identity.

The simulation and project semantic references advance only after the runtime accepts the intervention. A rejected attempt remains available in audit and service logs but does not enter business history. Idempotency replay is recorded as `semantic.inject_replay` in system logs and is never presented as a special user-facing result.

A forced rerun must close the retained command environment before deleting runtime artifacts or starting a new process. Environment liveness is read from the persisted status and process identity, and an old monitor may release registry state only when it still owns that exact process. This keeps one IPC consumer per simulation so a stale runtime cannot reinterpret or duplicate a normalized intervention.

### Step 4

Scene revisions use semantic patches. Node questions use one LLM call to interpret and answer the question against deterministic node evidence. When the LLM route is unavailable, the endpoint returns a constrained evidence summary rather than a technical failure bubble.

## Persistence And Compatibility

- Artifacts live under `backend/uploads/semantic_inputs/<artifact_id>/revision_<n>.json`.
- Audit records use the adjacent `revision_<n>.audit.json` path.
- Old projects are backfilled from the existing scene seed, project requirement, active variables, extracted document text, and map graph when Step 2 first needs a semantic artifact.
- Unprepared historical projects may project `initial_variables` or old `normalized_*` records into Step 2 as editable drafts. Ready simulations and their reports are not migrated, recomputed, or overwritten.
- Backfill creates a new semantic artifact and reference; it does not mutate old scene or project history files.
- A stale frontend reference resolves to the latest revision of the same artifact before appending, preventing revision overwrite.
- The Wuhan frozen planning fixture remains unchanged during this main-flow input-authority rollout; demo artifact maintenance is deferred to a later unified pass.

## Result And Log Separation

Formal Step 1-4 pages follow `docs/modules/result-first-output.md`. They display editable business artifacts and never display model route, recognition status, repair status, fallback status, confidence, unresolved references, or internal errors.

Service logs retain `semantic.normalize`, `semantic.normalize.reuse`, `semantic.repair`, `semantic.fallback`, `semantic.target.resolve`, revision, timing, and content-hash evidence. Authorized diagnostic surfaces may display those records without reusing them as formal business copy.

## Verification

Focused tests cover:

- the four accepted Hong Kong T8 expressions;
- three school/workplace closure expressions and separate authority demands;
- LLM correction inside supplied input IDs and rejection of invented IDs;
- explicit structure overriding model output;
- one repair call for invalid JSON;
- Chinese punctuation, aliases, duplicates, unknown targets, and `start_round=0`;
- one runtime mutation for repeated requests carrying the same idempotency key;
- scene revision patches and runtime revision continuity;
- identical preparation input reusing its semantic artifact and active task.
- draft Step 1 suggestions versus authoritative Step 2 revisions;
- complete array validation, explicit empty policies, deleted suggestion non-revival, and ready-state lock;
- foundation reuse, named-target enrichment, dangling target rejection, and ambiguous-location blocking.

## Maintenance Entry

- Contracts and normalizer: `backend/app/services/semantic_input/`
- Step 1 report integration: `backend/app/services/scene_material_generator.py`
- Step 2 and Step 3 API integration: `backend/app/api/simulation.py`
- Scenario planning: `backend/app/services/scenario_planner.py`
- Foundation coverage and enrichment: `backend/app/services/scenario_foundation_resolver.py`
- Step 4 question integration: `backend/app/services/report_analysis.py`
- Frontend handoff: `frontend/src/store/sceneSeedBridge.js`
- Formal UI: `frontend/src/views/SceneComposerView.vue`, `frontend/src/components/KaleidoStep2.vue`, `frontend/src/components/KaleidoStep3.vue`, `frontend/src/views/AnalysisView.vue`

## History

- 2026-07-13: Added `semantic-input.v1`, strict LLM normalization with one repair call, deterministic business fallback, catalog-bounded target resolution, immutable revisions and private audit records across Step 1-4.
- 2026-07-14: Added compound event/policy projection, foundation-bounded scene scope, distinct region-bounded institutional agents, and idempotent Step 3 injection with exact zero-round preservation.
- 2026-07-14: Added explicit draft/authoritative input authority, Step 1 suggestion fields, complete Step 2 replacement semantics, grounded simulation-scoped foundation enrichment, final input snapshots, and immutable ready configurations. Wuhan remained untouched.
