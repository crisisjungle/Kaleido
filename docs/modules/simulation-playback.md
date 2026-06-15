# Simulation Playback

## Current Capability

Step 3 plays simulation rounds against the shared graph surface. The graph keeps a stable base layout during playback, while each frame updates node and edge animation state for new, active, steady, faded, or hidden relationships.

During animation playback, the visible surface is intentionally a focused pulse: only the current frame's new or active nodes and relationships should appear. Background graph items remain in the renderer for layout stability, but they should not visually clutter the pulse.

The playback panel shows round progress, connection deltas, and the most relevant new or active relationships so the user can see what changed in the current pulse without losing graph context.

## Key Rules

- Playback frame changes must not rebuild the 2D graph when the node and edge structure is unchanged.
- User zoom, pan, and drag state on the graph must remain usable while the animation is playing.
- The base graph should stay spatially stable; frame changes should update visual state and focus highlighting only.
- Hidden, steady, and faded animation states should stay out of sight during focused playback while remaining in the renderer for layout stability.
- Step 3 should prefer the animation payload layout while replaying frames so node and edge IDs match the frame state contract.
- Replay playback stops at the last frame. It should not loop back to the first frame automatically, because that reads as a sudden refresh.
- Wuhan frozen replay and normal generated simulations must use the same Step 3 playback behavior.

## Maintenance Entry

- Step 3 playback workbench: `frontend/src/components/KaleidoStep3.vue`
- Shared graph renderer: `frontend/src/components/GraphPanel.vue`
- Step 3 route shell and animation data adapter: `frontend/src/views/SimulationRunView.vue`
- Animation payload builder: `backend/app/services/simulation_animation_service.py`

## History

- 2026-05-23: Reworked Step 3 playback so round changes update graph animation styles in place instead of resetting the 2D graph. Added per-round connection deltas and stopped replay from jumping back to the first frame at the end.
- 2026-05-23: Tightened playback into a focused propagation pulse. Step 3 now uses animation layout IDs during replay, progressively reveals current-frame nodes and edges, and hides non-current background relationships in graph and map modes.
