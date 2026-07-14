# Scene Composer

## Current Capability

The background generation entry gathers a map anchor, location or area label, steady-state description, optional variables, and advanced constraints, then generates a scene material report for the downstream simulation workflow.

## Key Rules

- All Step 1 business-semantic inputs follow `docs/modules/semantic-input.md`. The report generator consumes `semantic-input.v1`; it does not classify raw variables a second time while writing prose.
- Scene seeds persist `semantic_artifact_ref`, normalized event and policy inputs, scene semantics, and field-complete active variables. `sessionStorage` is only a navigation recovery cache.
- Revision instructions are semantic patches. They update the current artifact by input ID and create a new immutable revision before the report is rewritten.
- Step 1 follows the result-first output contract in `docs/modules/result-first-output.md`. Once a valid map, scene material, or report exists, the formal UI displays that artifact directly instead of adding “location recognized”, “background generated successfully”, or similar completion copy. Test and diagnostic surfaces retain the actual processing route and status.
- The report preview only renders a validated `report_markdown` artifact. In-progress placeholder prose, system narration, and draft text such as “正在整理成正式报告” must stay out of the formal report surface; while generation is running or failed, preserve the user's inputs and any previous valid report, then expose the next action.
- The user-facing background time selector has been removed.
- New background generation requests default `time_scope` to the browser's current local time at the moment the user starts generation.
- Old restored snapshots may still contain historical `timeScope` values, but new draft previews and submitted `time_scope` values ignore them.
- Map seed analysis remains the grounding source for location, radius, and region context.
- Area naming must be radius-aware: the same center point can resolve to a street/neighborhood, district, city sector, or Pearl River Estuary scale label depending on the selected analysis radius.
- Area naming is center-anchor first. If the selected center falls on a strong real-world anchor such as an airport, station, district, or landmark, that anchor should drive the label even when the analysis radius includes broader water or regional content. If the center is only open water or otherwise weakly identified, the naming logic may fall back to the strongest meaningful content inside the analysis range.
- Map seed feature nodes shown in Step 1 should stay inside the selected analysis radius, except the center weather-baseline node. Broader reference places can inform naming or reporting, but must not be rendered as if they are inside the selected area.
- Step 1 should surface the map seed scene classification as "区域类型分析" once the map seed is ready.
- The Step 1 right workbench keeps the same fixed panel frame before and after the background report appears. Once report mode starts, only the report body scrolls inside the card; the card border, rounded shell, revision input, and bottom actions remain anchored.
- Analysis strength keeps the Chinese control label `分析强度`, but the selectable level names render as `Light / Medium / High / Extra High / Ultra`.

## Maintenance Entry

- Frontend page: `frontend/src/views/SceneComposerView.vue`
- Scene material API: `backend/app/api/scene_material.py`
- Scene material generator: `backend/app/services/scene_material_generator.py`

## History

- 2026-07-14: Stopped the Step 1 report panel from rendering a synthetic pending report draft before `/api/scene/compose` returns a valid `report_markdown`; failed compose attempts now keep the report surface empty or preserve the previous valid report.
- 2026-07-13: Routed scene text, variables, documents, map context, and revision instructions through the versioned semantic-input boundary and preserved the resulting reference through Step 2.
- 2026-07-13: Locked the generated-report stage into the same fixed right-panel shell as the empty setup stage and restored English analysis-strength level labels.
- 2026-05-21: Removed the manual background time input and changed background generation to use current local time by default.
- 2026-05-21: Made map area labels radius-aware so large analysis radii no longer reuse a narrow district-level label.
- 2026-05-23: Changed area naming to prefer the selected center anchor first, with range-content fallback for weak centers such as open water.
- 2026-05-23: Scoped rendered map seed feature nodes to the analysis radius and restored the visible Step 1 region-type analysis panel.
