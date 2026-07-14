const coordinatePair = (value) => {
  if (!Array.isArray(value) || value.length < 2) return null
  const lon = Number(value[0])
  const lat = Number(value[1])
  return Number.isFinite(lon) && Number.isFinite(lat) ? [lon, lat] : null
}

export const CURATED_FIXTURE_GROUNDING = 'curated_deterministic_fixture'

const normalizedToken = value => String(value || '').trim().toLowerCase()

export function normalizeMapAnimationStatus(value) {
  const status = normalizedToken(value)
  return ['hidden', 'new', 'steady', 'active', 'faded'].includes(status) ? status : 'steady'
}

export function isCuratedFixtureNode(node) {
  const attrs = node?.attributes || {}
  const rawLat = attrs.lat ?? node?.lat
  const rawLon = attrs.lon ?? node?.lon
  const lat = rawLat === '' || rawLat == null ? Number.NaN : Number(rawLat)
  const lon = rawLon === '' || rawLon == null ? Number.NaN : Number(rawLon)
  const grounding = normalizedToken(
    attrs.coordinate_grounding
    || attrs.geographic_grounding
    || node?.coordinate_grounding
    || node?.geographic_grounding,
  )
  const placement = normalizedToken(attrs.placement || node?.placement)
  return Number.isFinite(lat)
    && Number.isFinite(lon)
    && lat >= -90
    && lat <= 90
    && lon >= -180
    && lon <= 180
    && grounding === CURATED_FIXTURE_GROUNDING
    && placement === 'curated_fixture'
    && attrs.coordinates_observed !== true
    && node?.coordinates_observed !== true
}

export function isCuratedFixtureRouteEdge(edge) {
  const attrs = edge?.attributes || {}
  const factType = normalizedToken(edge?.fact_type || edge?.name)
  const grounding = normalizedToken(
    attrs.route_grounding
    || attrs.geographic_grounding
    || edge?.route_grounding
    || edge?.geographic_grounding,
  )
  return factType === 'transport_edge'
    && attrs.is_route_edge === true
    && grounding === CURATED_FIXTURE_GROUNDING
    && attrs.route_observed !== true
    && edge?.route_observed !== true
}

const mapNodeKind = node => {
  const explicit = normalizedToken(node?.kind || node?.attributes?.map_kind)
  if (explicit) return explicit
  const id = normalizedToken(node?.uuid || node?.id)
  if (id.startsWith('subregion::')) return 'subregion'
  if (id.startsWith('region::')) return 'region'
  return ''
}

/**
 * Return a decision only when at least one endpoint explicitly belongs to a
 * curated fixture.  A primary wave requires two fixture-coordinate endpoints
 * plus an explicitly fixture-grounded transport route.  Other fixture region
 * links remain schematic; Agent/mixed links are omitted.
 */
export function resolveCuratedFixtureEdgeGrounding(sourceNode, targetNode, edge) {
  const sourceIsFixture = isCuratedFixtureNode(sourceNode)
  const targetIsFixture = isCuratedFixtureNode(targetNode)
  if (!sourceIsFixture && !targetIsFixture) return ''
  if (sourceIsFixture && targetIsFixture && isCuratedFixtureRouteEdge(edge)) {
    return 'curated_fixture'
  }
  const regionKinds = new Set(['region', 'subregion'])
  return regionKinds.has(mapNodeKind(sourceNode)) && regionKinds.has(mapNodeKind(targetNode))
    ? 'schematic'
    : 'omit'
}

const normalizeLineCoordinates = (value) => {
  if (!Array.isArray(value)) return []
  return value.map(coordinatePair).filter(Boolean)
}

export function normalizeEdgeGeometryCandidate(candidate) {
  let geometry = candidate
  if (typeof geometry === 'string') {
    try {
      geometry = JSON.parse(geometry)
    } catch {
      return null
    }
  }
  if (geometry?.type === 'FeatureCollection') {
    geometry = (geometry.features || []).find((feature) => (
      feature?.geometry?.type === 'LineString' || feature?.geometry?.type === 'MultiLineString'
    ))?.geometry
  }
  if (geometry?.type === 'Feature') geometry = geometry.geometry
  if (!geometry || typeof geometry !== 'object') return null
  if (geometry.type === 'LineString') {
    const coordinates = normalizeLineCoordinates(geometry.coordinates)
    return coordinates.length >= 2 ? { type: 'LineString', coordinates } : null
  }
  if (geometry.type === 'MultiLineString' && Array.isArray(geometry.coordinates)) {
    const coordinates = geometry.coordinates.map(normalizeLineCoordinates).filter((line) => line.length >= 2)
    return coordinates.length ? { type: 'MultiLineString', coordinates } : null
  }
  return null
}

const distanceSquared = (left, right) => {
  if (!left || !right) return Number.POSITIVE_INFINITY
  const dx = Number(left[0]) - Number(right[0])
  const dy = Number(left[1]) - Number(right[1])
  return dx * dx + dy * dy
}

export function orientGeometryFromSource(geometry, sourceCoordinate) {
  if (geometry.type === 'LineString') {
    const coordinates = [...geometry.coordinates]
    if (distanceSquared(coordinates.at(-1), sourceCoordinate) < distanceSquared(coordinates[0], sourceCoordinate)) {
      coordinates.reverse()
    }
    return { ...geometry, coordinates }
  }
  const lines = geometry.coordinates.map((line) => [...line])
  const first = lines[0]?.[0]
  const last = lines.at(-1)?.at(-1)
  if (distanceSquared(last, sourceCoordinate) < distanceSquared(first, sourceCoordinate)) {
    lines.reverse()
    lines.forEach((line) => line.reverse())
  }
  return { ...geometry, coordinates: lines }
}

export function resolveEdgeGeometry(source, target, edge) {
  const attrs = edge?.attributes || {}
  const candidates = [
    edge?.geometry,
    edge?.route_geometry,
    edge?.path_geometry,
    edge?.geojson_geometry,
    attrs.geometry,
    attrs.route_geometry,
    attrs.path_geometry,
    attrs.geojson_geometry
  ]
  for (const candidate of candidates) {
    const geometry = normalizeEdgeGeometryCandidate(candidate)
    if (geometry) return orientGeometryFromSource(geometry, [source.lon, source.lat])
  }

  const coordinateCandidates = [
    edge?.coordinates,
    edge?.route_coordinates,
    edge?.path_coordinates,
    attrs.coordinates,
    attrs.route_coordinates,
    attrs.path_coordinates
  ]
  for (const coordinates of coordinateCandidates) {
    const line = normalizeLineCoordinates(coordinates)
    if (line.length >= 2) {
      return orientGeometryFromSource({ type: 'LineString', coordinates: line }, [source.lon, source.lat])
    }
  }

  // Without route evidence, the honest fallback is the endpoint segment.
  // Never manufacture a bend that could look like an observed physical route.
  return {
    type: 'LineString',
    coordinates: [[source.lon, source.lat], [target.lon, target.lat]]
  }
}

const segmentLength = (start, end) => {
  const midLat = ((Number(start?.[1]) || 0) + (Number(end?.[1]) || 0)) * Math.PI / 360
  const dx = (Number(end?.[0]) - Number(start?.[0])) * Math.cos(midLat)
  const dy = Number(end?.[1]) - Number(start?.[1])
  return Math.sqrt(dx * dx + dy * dy)
}

const lineLength = (coordinates) => {
  let total = 0
  for (let index = 1; index < coordinates.length; index += 1) {
    total += segmentLength(coordinates[index - 1], coordinates[index])
  }
  return total
}

const sliceLineAtLength = (coordinates, requestedLength) => {
  if (!coordinates.length) return []
  if (coordinates.length === 1 || requestedLength <= 0) return [coordinates[0], coordinates[0]]
  const result = [coordinates[0]]
  let travelled = 0
  for (let index = 1; index < coordinates.length; index += 1) {
    if (requestedLength - travelled <= 1e-12) break
    const start = coordinates[index - 1]
    const end = coordinates[index]
    const length = segmentLength(start, end)
    if (travelled + length <= requestedLength || length <= 1e-12) {
      result.push(end)
      travelled += length
      continue
    }
    const ratio = Math.max(0, Math.min(1, (requestedLength - travelled) / length))
    result.push([
      start[0] + (end[0] - start[0]) * ratio,
      start[1] + (end[1] - start[1]) * ratio
    ])
    break
  }
  if (result.length === 1) result.push(result[0])
  return result
}

export function sliceGeometryByProgress(geometry, rawProgress) {
  const progress = Math.max(0, Math.min(1, Number(rawProgress) || 0))
  if (progress >= 1) return geometry
  if (geometry.type === 'LineString') {
    const total = lineLength(geometry.coordinates)
    return {
      ...geometry,
      coordinates: sliceLineAtLength(geometry.coordinates, total * progress)
    }
  }

  const lines = geometry.coordinates
  const lengths = lines.map(lineLength)
  let remaining = lengths.reduce((sum, value) => sum + value, 0) * progress
  const sliced = []
  for (let index = 0; index < lines.length; index += 1) {
    if (remaining <= 0) break
    const length = lengths[index]
    if (remaining >= length) {
      sliced.push(lines[index])
      remaining -= length
    } else {
      sliced.push(sliceLineAtLength(lines[index], remaining))
      remaining = 0
    }
  }
  if (!sliced.length && lines[0]?.length) sliced.push([lines[0][0], lines[0][0]])
  return { ...geometry, coordinates: sliced }
}
