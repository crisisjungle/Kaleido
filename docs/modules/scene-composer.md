# Scene Composer

## Current Capability

The background generation entry gathers a map anchor, location or area label, steady-state description, optional variables, and advanced constraints, then generates a scene material report for the downstream simulation workflow.

## Key Rules

- The user-facing background time selector has been removed.
- New background generation requests default `time_scope` to the browser's current local time at the moment the user starts generation.
- Old restored snapshots may still contain historical `timeScope` values, but new draft previews and submitted `time_scope` values ignore them.
- Map seed analysis remains the grounding source for location, radius, and region context.
- Area naming must be radius-aware: the same center point can resolve to a street/neighborhood, district, city sector, or Pearl River Estuary scale label depending on the selected analysis radius.
- Area naming is center-anchor first. If the selected center falls on a strong real-world anchor such as an airport, station, district, or landmark, that anchor should drive the label even when the analysis radius includes broader water or regional content. If the center is only open water or otherwise weakly identified, the naming logic may fall back to the strongest meaningful content inside the analysis range.
- Map seed feature nodes shown in Step 1 should stay inside the selected analysis radius, except the center weather-baseline node. Broader reference places can inform naming or reporting, but must not be rendered as if they are inside the selected area.
- Step 1 should surface the map seed scene classification as "区域类型分析" once the map seed is ready.

## Maintenance Entry

- Frontend page: `frontend/src/views/SceneComposerView.vue`
- Scene material API: `backend/app/api/scene_material.py`
- Scene material generator: `backend/app/services/scene_material_generator.py`

## History

- 2026-05-21: Removed the manual background time input and changed background generation to use current local time by default.
- 2026-05-21: Made map area labels radius-aware so large analysis radii no longer reuse a narrow district-level label.
- 2026-05-23: Changed area naming to prefer the selected center anchor first, with range-content fallback for weak centers such as open water.
- 2026-05-23: Scoped rendered map seed feature nodes to the analysis radius and restored the visible Step 1 region-type analysis panel.
