const hasOwn = (value, key) => (
  value != null && Object.prototype.hasOwnProperty.call(value, key)
)

const readProjectionField = (layout, fallbackProjection, key, fallbackValue) => {
  if (hasOwn(layout, key)) return layout[key]
  if (hasOwn(fallbackProjection, key)) return fallbackProjection[key]
  return fallbackValue
}

/**
 * Preserve spatial provenance while the Step 3 animation layout is projected
 * back into the map DTO. An explicit null map_seed_id is meaningful fixture
 * metadata and must not be silently rewritten to an empty string.
 */
export function readAnimationMapProjectionMetadata(layout = {}, fallbackProjection = {}) {
  const layoutMeta = layout?.meta && typeof layout.meta === 'object' ? layout.meta : {}
  const fallbackMeta = fallbackProjection?.meta && typeof fallbackProjection.meta === 'object'
    ? fallbackProjection.meta
    : {}
  return {
    source_mode: readProjectionField(layout, fallbackProjection, 'source_mode', 'animation_layout'),
    map_seed_id: readProjectionField(layout, fallbackProjection, 'map_seed_id', null),
    geographic_grounding: readProjectionField(layout, fallbackProjection, 'geographic_grounding', ''),
    data_quality: readProjectionField(layout, fallbackProjection, 'data_quality', {}),
    selection_summary: readProjectionField(layout, fallbackProjection, 'selection_summary', {}),
    meta: {
      ...fallbackMeta,
      ...layoutMeta,
    },
  }
}
