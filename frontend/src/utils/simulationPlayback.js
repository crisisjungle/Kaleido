const TIMELINE_CACHE = new WeakMap()
const MAX_RENDERED_EVENTS_PER_FRAME = 18
const MAX_CONCURRENT_WAVE_EVENTS = 6

const clamp = (value, min = 0, max = 1) => Math.min(Math.max(Number(value) || 0, min), max)

const asArray = value => (Array.isArray(value) ? value : [])

const asId = value => String(value || '').trim()

const asFiniteNumber = (value, fallback = 0) => {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

const firstId = (...values) => {
  for (const value of values) {
    if (Array.isArray(value)) {
      const nested = value.map(asId).find(Boolean)
      if (nested) return nested
      continue
    }
    const id = asId(value)
    if (id) return id
  }
  return ''
}

const collectIds = (...values) => {
  const ids = []
  const seen = new Set()
  values.forEach((value) => {
    const candidates = Array.isArray(value) ? value : [value]
    candidates.forEach((candidate) => {
      const id = asId(candidate)
      if (!id || seen.has(id)) return
      seen.add(id)
      ids.push(id)
    })
  })
  return ids
}

const hasOwn = (value, key) => Boolean(
  value
  && typeof value === 'object'
  && Object.prototype.hasOwnProperty.call(value, key),
)

const legacyEventEdgeIds = event => collectIds(
  event?.edge_id,
  event?.edge_ids,
  event?.relationship_id,
  event?.relation_id,
)

const eventPathEdgeIds = (event) => {
  // Presence of the split field is authoritative, including an explicit empty
  // list.  It means related/evidence edges must not be promoted to a route.
  if (hasOwn(event, 'path_edge_ids') || hasOwn(event, 'path_edge_id')) {
    return collectIds(event?.path_edge_id, event?.path_edge_ids)
  }
  const legacy = legacyEventEdgeIds(event)
  const orderedLegacyContract = event?.edge_ids_are_ordered_path === true
    || ['ordered_continuous_path.v1', 'ordered_contiguous_path.v1'].includes(
      asId(event?.path_contract || event?.edge_path_contract),
    )
  // Untyped legacy edge arrays were commonly frame focus/evidence sets.  Only
  // one edge, or an explicit ordered-path marker, is safe to animate as a path.
  if (legacy.length === 1 || orderedLegacyContract) return legacy
  return []
}

const eventRelatedEdgeIds = (event) => {
  const mechanismEdgeIds = collectIds(event?.mechanism_edge_id, event?.mechanism_edge_ids)
  if (hasOwn(event, 'related_edge_ids') || hasOwn(event, 'related_edge_id')) {
    return collectIds(event?.related_edge_id, event?.related_edge_ids, mechanismEdgeIds)
  }
  const legacy = legacyEventEdgeIds(event)
  const pathIds = new Set(eventPathEdgeIds(event))
  return collectIds(
    legacy.filter(edgeId => !pathIds.has(edgeId)),
    mechanismEdgeIds,
  )
}

const eventKind = event => asId(
  event?.kind
  || event?.phase
  || event?.event_type
  || event?.type
  || 'relationship',
)

const readEventTiming = event => {
  const timing = event?.timing && typeof event.timing === 'object' ? event.timing : {}
  return {
    startMs: Math.max(0, asFiniteNumber(event?.start_ms ?? timing.start_ms, Number.NaN)),
    durationMs: Math.max(0, asFiniteNumber(event?.duration_ms ?? timing.duration_ms, Number.NaN)),
  }
}

const normalizeEvent = (event, fallbackRound = 0, fallbackIndex = 0) => {
  const source = event?.source && typeof event.source === 'object' ? event.source : {}
  const target = event?.target && typeof event.target === 'object' ? event.target : {}
  const grounding = event?.grounding && typeof event.grounding === 'object' ? event.grounding : {}
  const display = event?.display && typeof event.display === 'object' ? event.display : {}
  const timing = readEventTiming(event)
  const round = Math.max(0, asFiniteNumber(event?.round ?? event?.round_num, fallbackRound))
  const kind = eventKind(event)
  const sourceNodeId = firstId(
    event?.source_node_id,
    event?.source_id,
    source?.node_ids,
    source?.region_node_ids,
    source?.node_id,
    source?.id,
    event?.source_region_id,
    event?.source_agent_id,
  )
  const targetNodeId = firstId(
    event?.target_node_id,
    event?.target_id,
    target?.node_ids,
    target?.region_node_ids,
    target?.node_id,
    target?.id,
    event?.target_region_id,
    event?.target_agent_id,
  )
  const pathEdgeIds = eventPathEdgeIds(event)
  const relatedEdgeIds = eventRelatedEdgeIds(event)
  const hasTypedEdgeReferences = hasOwn(event, 'path_edge_ids')
    || hasOwn(event, 'path_edge_id')
    || hasOwn(event, 'related_edge_ids')
    || hasOwn(event, 'related_edge_id')
  const edgeIds = collectIds(pathEdgeIds, relatedEdgeIds)
  const edgeId = pathEdgeIds[0] || relatedEdgeIds[0] || ''
  const eventId = firstId(
    event?.id,
    event?.event_id,
    `${round}:${kind}:${sourceNodeId}:${targetNodeId}:${edgeId}:${fallbackIndex}`,
  )

  return {
    ...event,
    event_id: eventId,
    round,
    kind,
    phase: asId(event?.phase || kind),
    source_node_id: sourceNodeId,
    target_node_id: targetNodeId,
    edge_id: edgeId,
    edge_ids: edgeIds,
    path_edge_ids: pathEdgeIds,
    related_edge_ids: relatedEdgeIds,
    has_typed_edge_references: hasTypedEdgeReferences,
    parent_event_ids: asArray(event?.parent_event_ids || event?.parents).map(asId).filter(Boolean),
    sequence: asFiniteNumber(event?.sequence ?? event?.order ?? event?.index, fallbackIndex),
    hop: Math.max(0, asFiniteNumber(event?.hop ?? event?.depth, 0)),
    intensity: clamp(event?.intensity ?? event?.transfer_intensity ?? event?.strength ?? 0.5),
    confidence: clamp(event?.confidence ?? event?.certainty ?? 0.5),
    grounding: asId(
      grounding?.mode
      || event?.grounding_mode
      || event?.spatial_grounding
      || (typeof event?.grounding === 'string' ? event.grounding : '')
      || 'legacy',
    ),
    grounding_detail: grounding,
    display_label: asId(display?.title_zh || event?.display_label || event?.label_zh),
    display_summary: asId(display?.summary_zh || event?.summary_zh || event?.summary),
    timing: {
      start_ms: timing.startMs,
      duration_ms: timing.durationMs,
    },
  }
}

const sortEvents = events => [...events].sort((left, right) => {
  if (left.round !== right.round) return left.round - right.round
  const leftExplicitStart = asFiniteNumber(left.timing?.start_ms, Number.NaN)
  const rightExplicitStart = asFiniteNumber(right.timing?.start_ms, Number.NaN)
  if (
    Number.isFinite(leftExplicitStart)
    && Number.isFinite(rightExplicitStart)
    && leftExplicitStart !== rightExplicitStart
  ) {
    return leftExplicitStart - rightExplicitStart
  }
  if (left.hop !== right.hop) return left.hop - right.hop
  const leftStart = Number.isFinite(leftExplicitStart) ? leftExplicitStart : 0
  const rightStart = Number.isFinite(rightExplicitStart) ? rightExplicitStart : 0
  if (leftStart !== rightStart) return leftStart - rightStart
  if (left.sequence !== right.sequence) return left.sequence - right.sequence
  return left.event_id.localeCompare(right.event_id)
})

const collectTimelineEvents = payload => {
  if (!payload || typeof payload !== 'object') return []
  const cached = TIMELINE_CACHE.get(payload)
  if (cached) return cached

  const timeline = payload.timeline && typeof payload.timeline === 'object' ? payload.timeline : {}
  const rawEvents = []
  asArray(timeline.events).forEach(event => rawEvents.push({ event }))
  asArray(timeline.rounds).forEach(roundEntry => {
    const round = asFiniteNumber(roundEntry?.round ?? roundEntry?.round_num, 0)
    asArray(roundEntry?.events).forEach(event => rawEvents.push({ event, round }))
  })

  const seen = new Set()
  const events = sortEvents(rawEvents
    .map(({ event, round }, index) => normalizeEvent(event, round, index))
    .filter(event => {
      if (!event.event_id || seen.has(event.event_id)) return false
      seen.add(event.event_id)
      return true
    }))
  TIMELINE_CACHE.set(payload, events)
  return events
}

const frameEvents = (payload, frame) => {
  const round = Math.max(0, asFiniteNumber(frame?.round ?? frame?.round_num, 0))
  const direct = asArray(
    frame?.propagation_events
    || frame?.timeline_events
    || frame?.events,
  )
  if (direct.length) {
    return sortEvents(direct.map((event, index) => normalizeEvent(event, round, index)))
  }
  const timelineEvents = collectTimelineEvents(payload)
  const eventIds = new Set(asArray(frame?.timeline_event_ids).map(asId).filter(Boolean))
  if (eventIds.size) return timelineEvents.filter(event => eventIds.has(event.event_id))
  return timelineEvents.filter(event => event.round === round)
}

const selectRenderableEvents = (events, limit = MAX_RENDERED_EVENTS_PER_FRAME) => {
  const unique = []
  const seen = new Set()
  events.forEach((event) => {
    if (!event.source_node_id && !event.target_node_id && !event.edge_id) return
    const pathEdgeIds = eventPathEdgeIds(event)
    const relatedEdgeIds = eventRelatedEdgeIds(event)
    const key = [
      pathEdgeIds.length
        ? `path:${pathEdgeIds.join(',')}`
        : relatedEdgeIds.length
          ? `related:${relatedEdgeIds.join(',')}`
          : `${event.source_node_id}->${event.target_node_id}`,
      event.kind,
      event.phase,
    ].join(':')
    if (seen.has(key)) return
    seen.add(key)
    unique.push(event)
  })
  if (unique.length <= limit) return unique

  const phaseOrder = []
  const byPhase = new Map()
  unique.forEach((event) => {
    const phase = event.phase || 'relationship'
    if (!byPhase.has(phase)) {
      byPhase.set(phase, [])
      phaseOrder.push(phase)
    }
    byPhase.get(phase).push(event)
  })

  const selected = []
  const selectedIds = new Set()
  phaseOrder.forEach((phase) => {
    byPhase.get(phase).slice(0, 2).forEach((event) => {
      selected.push(event)
      selectedIds.add(event.event_id)
    })
  })
  unique.forEach((event) => {
    if (selected.length >= limit || selectedIds.has(event.event_id)) return
    selected.push(event)
    selectedIds.add(event.event_id)
  })
  return sortEvents(selected).slice(0, limit)
}

const scheduleFrameEvents = (events, durationMs) => {
  if (!events.length) return []
  const duration = Math.max(800, asFiniteNumber(durationMs, 1600))
  const maxHop = Math.max(0, ...events.map(event => event.hop))
  const hopSpan = duration * 0.68 / Math.max(1, maxHop + 1)
  const perHopCounts = new Map()
  const perHopIndexes = new Map()

  events.forEach(event => perHopCounts.set(event.hop, (perHopCounts.get(event.hop) || 0) + 1))

  const denseTimeline = events.length > 6
  const waveWidth = 3
  const waveCount = Math.max(1, Math.ceil(events.length / waveWidth))
  const denseStep = Math.max(240, (duration - 520) / Math.max(1, waveCount - 1))
  const denseEventDuration = Math.max(420, Math.min(720, denseStep * 1.45))

  const scheduled = events.map((event, index) => {
    const explicitStart = asFiniteNumber(event.timing?.start_ms, Number.NaN)
    const explicitDuration = asFiniteNumber(event.timing?.duration_ms, Number.NaN)
    const hopIndex = perHopIndexes.get(event.hop) || 0
    perHopIndexes.set(event.hop, hopIndex + 1)
    const siblings = Math.max(1, perHopCounts.get(event.hop) || 1)
    const fallbackStart = (event.hop * hopSpan) + ((hopIndex / siblings) * Math.min(hopSpan * 0.42, 180))
    const fallbackDuration = Math.max(360, Math.min(duration * 0.44, 760))
    const denseStart = Math.floor(index / waveWidth) * denseStep + (index % waveWidth) * 34
    const startMs = Number.isFinite(explicitStart)
      ? Math.max(0, explicitStart)
      : denseTimeline
      ? clamp(denseStart, 0, Math.max(0, duration - 240))
      : clamp(fallbackStart, 0, Math.max(0, duration - 120))
    const eventDuration = Number.isFinite(explicitDuration) && explicitDuration > 0
      ? explicitDuration
      : denseTimeline
      ? denseEventDuration
      : fallbackDuration
    const renderedDuration = Number.isFinite(explicitDuration) && explicitDuration > 0
      ? explicitDuration
      : Math.min(eventDuration, Math.max(240, duration - startMs))

    return {
      ...event,
      sequence: asFiniteNumber(event.sequence, index),
      timing: {
        ...event.timing,
        source_start_ms: Number.isFinite(explicitStart) ? explicitStart : undefined,
        source_duration_ms: Number.isFinite(explicitDuration) ? explicitDuration : undefined,
        start_ms: Math.round(startMs),
        duration_ms: Math.round(renderedDuration),
      },
    }
  })

  // Only legacy events with no explicit start may be shifted by the client.
  // Their fallback wave must not begin before an explicitly linked parent has
  // finished.  Backend-authored start/duration values remain authoritative and
  // are never replaced merely because the frame is dense or spans many hops.
  const scheduledById = new Map(scheduled.map(event => [event.event_id, event]))
  return scheduled.map((event) => {
    if (Number.isFinite(event?.timing?.source_start_ms)) return event
    const parentEnd = asArray(event.parent_event_ids).reduce((latest, parentId) => {
      const parent = scheduledById.get(asId(parentId))
      if (!parent) return latest
      const end = asFiniteNumber(parent?.timing?.start_ms, 0)
        + Math.max(1, asFiniteNumber(parent?.timing?.duration_ms, 1))
      return Math.max(latest, end)
    }, 0)
    if (parentEnd <= asFiniteNumber(event?.timing?.start_ms, 0)) return event
    return {
      ...event,
      timing: {
        ...event.timing,
        start_ms: Math.round(parentEnd),
      },
    }
  })
}

const currentEventsAt = (events, elapsedMs) => {
  if (!events.length) return []
  const elapsed = Math.max(0, asFiniteNumber(elapsedMs, 0))
  const active = events.filter(event => {
    const start = asFiniteNumber(event.timing?.start_ms, 0)
    const end = start + Math.max(1, asFiniteNumber(event.timing?.duration_ms, 1))
    return elapsed >= start && elapsed < end
  })
  if (active.length <= MAX_CONCURRENT_WAVE_EVENTS) return active

  // Keep long-running causal fronts alive until they finish. A latest-start
  // slice made an outbreak/diffusion path vanish mid-route as soon as several
  // later Agent events became active. Round-robin selection across phases
  // preserves the environment -> response -> relationship story while still
  // enforcing the six-wave readability ceiling.
  const phaseOrder = []
  const byPhase = new Map()
  active.forEach((event) => {
    const phase = asId(event.phase || event.kind || 'relationship')
    if (!byPhase.has(phase)) {
      byPhase.set(phase, [])
      phaseOrder.push(phase)
    }
    byPhase.get(phase).push(event)
  })

  const selected = []
  let added = true
  while (selected.length < MAX_CONCURRENT_WAVE_EVENTS && added) {
    added = false
    phaseOrder.forEach((phase) => {
      if (selected.length >= MAX_CONCURRENT_WAVE_EVENTS) return
      const next = byPhase.get(phase)?.shift()
      if (!next) return
      selected.push(next)
      added = true
    })
  }
  return selected
}

const eventPathProgress = (event, elapsedMs) => {
  const start = Math.max(0, asFiniteNumber(event?.timing?.start_ms, 0))
  const duration = Math.max(1, asFiniteNumber(event?.timing?.duration_ms, 1))
  const rawProgress = clamp((Math.max(0, asFiniteNumber(elapsedMs, 0)) - start) / duration)
  return clamp((rawProgress - 0.14) / 0.6)
}

const eventEdgeSegments = (event, elapsedMs) => {
  const edgeIds = eventPathEdgeIds(event)
  if (!edgeIds.length) return []
  const pathProgress = eventPathProgress(event, elapsedMs)
  const start = Math.max(0, asFiniteNumber(event?.timing?.start_ms, 0))
  const duration = Math.max(1, asFiniteNumber(event?.timing?.duration_ms, 1))
  const segmentDuration = (duration * 0.6) / edgeIds.length
  return edgeIds.map((edgeId, index) => ({
    edgeId,
    index,
    count: edgeIds.length,
    progress: clamp((pathProgress * edgeIds.length) - index),
    startMs: start + (duration * 0.14) + (segmentDuration * index),
    durationMs: segmentDuration,
  }))
}

export const buildPlaybackFrame = (
  payload,
  frame,
  {
    elapsedMs = 0,
    durationMs = 1600,
    isPlaying = false,
  } = {},
) => {
  if (!frame || typeof frame !== 'object') return frame || null
  const duration = Math.max(800, asFiniteNumber(durationMs, frame.playback_duration_ms || 1600))
  const elapsed = clamp(elapsedMs, 0, duration)
  const events = scheduleFrameEvents(selectRenderableEvents(frameEvents(payload, frame)), duration)
  if (!events.length) {
    return {
      ...frame,
      playback_elapsed_ms: elapsed,
      playback_duration_ms: duration,
      playback_is_playing: Boolean(isPlaying),
    }
  }

  const activeEvents = currentEventsAt(events, elapsed)
  const nodeIds = new Set()
  const edgeIds = new Set()
  activeEvents.forEach(event => {
    if (event.source_node_id) nodeIds.add(event.source_node_id)
    const start = Math.max(0, asFiniteNumber(event?.timing?.start_ms, 0))
    const duration = Math.max(1, asFiniteNumber(event?.timing?.duration_ms, 1))
    const rawProgress = clamp((elapsed - start) / duration)
    // Keep the destination quiet until the propagation wave actually reaches
    // its response phase.  Lighting both endpoints at event start makes the
    // animation read as a refresh rather than a causal journey.
    if (event.target_node_id && rawProgress > 0.72) nodeIds.add(event.target_node_id)
    eventEdgeSegments(event, elapsed)
      .filter(segment => segment.progress > 0 && segment.progress < 1)
      .forEach(segment => edgeIds.add(segment.edgeId))
  })

  const originalFocus = frame.focus_ids && typeof frame.focus_ids === 'object' ? frame.focus_ids : {}
  return {
    ...frame,
    playback_elapsed_ms: elapsed,
    playback_duration_ms: duration,
    playback_is_playing: Boolean(isPlaying),
    timeline_contract_version: asId(
      payload?.timeline?.contract_version
      || payload?.timeline?.version
      || payload?.meta?.timeline_contract_version
      || 'legacy',
    ),
    propagation_events: events,
    active_propagation_event_ids: activeEvents.map(event => event.event_id),
    focus_ids: {
      ...originalFocus,
      // Timeline playback owns focus. During the short gap between two waves
      // the base graph remains visible, but no legacy frame-wide focus is
      // allowed to light the whole cluster back up.
      node_ids: [...nodeIds],
      edge_ids: [...edgeIds],
    },
  }
}

export const getFrameTimelineDuration = (payload, frame, fallbackMs = 1600) => {
  const fallback = Math.max(800, asFiniteNumber(fallbackMs, 1600))
  const events = frameEvents(payload, frame)
  const latestEnd = events.reduce((maxEnd, event) => {
    const start = asFiniteNumber(event?.timing?.start_ms, Number.NaN)
    const duration = asFiniteNumber(event?.timing?.duration_ms, Number.NaN)
    if (!Number.isFinite(start) || !Number.isFinite(duration) || duration <= 0) return maxEnd
    return Math.max(maxEnd, start + duration)
  }, 0)
  return Math.max(fallback, latestEnd > 0 ? Math.ceil(latestEnd + 80) : fallback)
}

const statusRank = status => ({ hidden: 0, steady: 1, faded: 2, new: 3, active: 4 }[status] || 0)

/**
 * Resolve the non-pulsing layer underneath Timeline V2 propagation.
 *
 * Timeline events own the transient `new` / `active` emphasis, but they do not
 * own entity existence.  Frame state and `first_seen_round` remain the
 * authoritative lifecycle watermark, so a future entity must stay hidden and
 * an expired relationship must stay faded instead of being promoted to the
 * stable background merely because the frame contains propagation events.
 */
export const buildTimelineBaseState = (
  state = null,
  {
    hasTimeline = false,
    currentRound = 0,
  } = {},
) => {
  if (!hasTimeline) return state || {
    status: 'hidden',
    raw_animation_status: 'hidden',
    animation_progress: 0,
    animation_due: false,
  }

  const source = state && typeof state === 'object' ? state : {}
  const rawStatus = asId(source.raw_animation_status || source.status || 'steady').toLowerCase()
  const firstSeenRound = asFiniteNumber(source.first_seen_round, Number.NaN)
  const frameRound = Math.max(0, asFiniteNumber(currentRound, 0))
  const isFuture = Number.isFinite(firstSeenRound) && firstSeenRound > frameRound
  const isHidden = rawStatus === 'hidden' || isFuture
  const baseStatus = isHidden
    ? 'hidden'
    : rawStatus === 'faded'
    ? 'faded'
    : 'steady'

  return {
    ...source,
    status: baseStatus,
    raw_animation_status: rawStatus,
    animation_progress: isHidden ? 0 : 1,
    animation_due: !isHidden,
  }
}

/**
 * Apply a current-wave pulse without crossing the authoritative lifecycle
 * watermark. A stale or inconsistent timeline may still name a future item;
 * that reference must never revive a base item that the committed frame keeps
 * hidden.
 */
export const mergeTimelinePulseState = (baseState = {}, pulseState = null) => {
  if (!pulseState) return baseState
  const baseStatus = asId(
    baseState?.status || baseState?.raw_animation_status || 'steady',
  ).toLowerCase()
  if (baseStatus === 'hidden') return baseState
  return {
    ...baseState,
    ...pulseState,
    first_seen_round: baseState.first_seen_round,
    last_active_round: baseState.last_active_round,
  }
}

const mergePulseState = (map, id, next) => {
  if (!id || !next) return
  const current = map.get(id)
  if (!current || statusRank(next.status) > statusRank(current.status)) {
    map.set(id, next)
    return
  }
  if (statusRank(next.status) === statusRank(current.status) && next.animation_progress > current.animation_progress) {
    map.set(id, next)
  }
}

export const buildPropagationState = frame => {
  const nodeStates = new Map()
  const edgeStates = new Map()
  const pairStates = new Map()
  const events = asArray(frame?.propagation_events)
  if (!events.length) return { nodeStates, edgeStates, pairStates, hasTimeline: false }

  const elapsed = Math.max(0, asFiniteNumber(frame?.playback_elapsed_ms, 0))
  const hasActiveSelection = Array.isArray(frame?.active_propagation_event_ids)
  const activeEventIds = new Set(asArray(frame?.active_propagation_event_ids).map(asId).filter(Boolean))
  events.forEach(event => {
    const start = Math.max(0, asFiniteNumber(event?.timing?.start_ms, 0))
    const duration = Math.max(1, asFiniteNumber(event?.timing?.duration_ms, 1))
    if (elapsed >= start + duration) return
    const rawProgress = clamp((elapsed - start) / duration)
    if (elapsed < start) return
    // buildPlaybackFrame applies the concurrency cap used by the right-side
    // "current wave" cards.  Render exactly that same event set on the graph
    // and map so a dense round cannot show twelve active paths while the
    // product says that only six events are currently propagating.
    if (hasActiveSelection && !activeEventIds.has(asId(event.event_id))) return
    const current = elapsed < start + duration
    const status = current ? 'active' : 'new'
    const common = {
      status,
      raw_animation_status: status,
      delay_ms: 0,
      timeline_delay_ms: start,
      animation_elapsed_ms: elapsed,
      propagation_event_id: asId(event.event_id),
      propagation_kind: eventKind(event),
      propagation_phase: asId(event.phase || event.kind),
      propagation_intensity: clamp(event.intensity ?? 0.5),
      propagation_confidence: clamp(event.confidence ?? 0.5),
      propagation_grounding: asId(event.grounding || 'legacy'),
      propagation_current: current,
    }

    const sourceProgress = clamp(rawProgress / 0.2)
    mergePulseState(nodeStates, asId(event.source_node_id), {
      ...common,
      id: asId(event.source_node_id),
      animation_progress: sourceProgress,
      animation_due: sourceProgress > 0,
      propagation_role: 'source',
    })

    const pathProgress = eventPathProgress(event, elapsed)
    if (pathProgress > 0) {
      const explicitEdgeIds = eventPathEdgeIds(event)
      const relatedEdgeIds = eventRelatedEdgeIds(event)
      const commonEdgeState = {
        ...common,
        source_node_id: asId(event.source_node_id),
        target_node_id: asId(event.target_node_id),
        animation_progress: pathProgress,
        animation_due: true,
        propagation_role: 'path',
      }
      eventEdgeSegments(event, elapsed).forEach((segment) => {
        if (segment.progress <= 0) return
        const segmentCurrent = current && segment.progress < 1
        mergePulseState(edgeStates, segment.edgeId, {
          ...commonEdgeState,
          id: segment.edgeId,
          edge_ids: explicitEdgeIds,
          status: segmentCurrent ? 'active' : 'new',
          raw_animation_status: segmentCurrent ? 'active' : 'new',
          timeline_delay_ms: Math.round(segment.startMs),
          animation_progress: segment.progress,
          propagation_current: segmentCurrent,
          propagation_path_index: segment.index,
          propagation_path_count: segment.count,
        })
      })
      // Pair matching exists only for legacy events that have no relationship
      // identifier at all.  Once the backend names one or more concrete edges,
      // expanding the pulse to parallel edges with the same endpoints would
      // invent paths that are not part of the event contract.
      if (
        explicitEdgeIds.length === 0
        && relatedEdgeIds.length === 0
        && (
          ['spread_applied', 'agent_interaction'].includes(eventKind(event))
          || event?.has_typed_edge_references !== true
        )
        && commonEdgeState.source_node_id
        && commonEdgeState.target_node_id
      ) {
        mergePulseState(
          pairStates,
          `${commonEdgeState.source_node_id}->${commonEdgeState.target_node_id}`,
          {
            ...commonEdgeState,
            id: '',
            status: current && pathProgress < 1 ? 'active' : 'new',
            raw_animation_status: current && pathProgress < 1 ? 'active' : 'new',
            propagation_current: current && pathProgress < 1,
            // This is only a neutral visual bridge.  It is not evidence that
            // any concrete business relationship carried the event.
            propagation_grounding: 'schematic/partial',
          },
        )
      }
    }

    const targetProgress = clamp((rawProgress - 0.72) / 0.28)
    if (targetProgress > 0) {
      mergePulseState(nodeStates, asId(event.target_node_id), {
        ...common,
        id: asId(event.target_node_id),
        animation_progress: targetProgress,
        animation_due: true,
        propagation_role: 'target',
      })
    }
  })

  return { nodeStates, edgeStates, pairStates, hasTimeline: true }
}

const visualEdgeId = edge => asId(edge?.uuid || edge?.id || edge?.edge_id)
const visualEdgeSourceId = edge => asId(edge?.source_node_uuid || edge?.source || edge?.from)
const visualEdgeTargetId = edge => asId(edge?.target_node_uuid || edge?.target || edge?.to)

const visualEntityStatus = entity => asId(entity?.attributes?.animation_status).toLowerCase() || 'steady'

const visualEdgeFallbackKey = edge => [
  visualEdgeSourceId(edge),
  visualEdgeTargetId(edge),
  asId(edge?.fact_type || edge?.name || edge?.type || 'related').toLowerCase(),
].join('::')

/**
 * Keep graph inspection state inside the current playback watermark.
 *
 * The graph payload deliberately retains future entities as `hidden` so the
 * renderer can update in place. A selection made in a later round therefore
 * cannot be trusted after the user scrubs backwards: it must be reconciled
 * against the newly projected graph before labels or the detail panel render.
 */
export const reconcileVisibleGraphSelection = (selection, graphData) => {
  if (!selection || typeof selection !== 'object') return null
  const nodes = asArray(graphData?.nodes)
  const edges = asArray(graphData?.edges)
  const visibleNodeById = new Map(
    nodes
      .filter(node => visualEntityStatus(node) !== 'hidden')
      .map(node => [asId(node?.uuid || node?.id), node])
      .filter(([id]) => Boolean(id)),
  )

  if (selection.type === 'node') {
    const selectedId = asId(selection?.data?.uuid || selection?.data?.id)
    if (!selectedId) return null
    const current = visibleNodeById.get(selectedId)
    if (!current) return null
    return {
      ...selection,
      data: { ...current },
    }
  }

  if (selection.type !== 'edge') return null
  const selectedData = selection.data && typeof selection.data === 'object'
    ? selection.data
    : {}
  const groupKey = Array.isArray(selectedData.selfLoopEdges)
    ? 'selfLoopEdges'
    : Array.isArray(selectedData.parallelEdges)
      ? 'parallelEdges'
      : ''
  const selectedMembers = groupKey ? selectedData[groupKey] : [selectedData]
  const currentById = new Map(
    edges
      .map(edge => [visualEdgeId(edge), edge])
      .filter(([id]) => Boolean(id)),
  )
  const currentByFallback = new Map()
  edges.forEach((edge) => {
    const key = visualEdgeFallbackKey(edge)
    if (key && !currentByFallback.has(key)) currentByFallback.set(key, edge)
  })

  const currentMembers = []
  const seen = new Set()
  selectedMembers.forEach((member) => {
    const memberId = visualEdgeId(member)
    const current = memberId
      ? currentById.get(memberId)
      : currentByFallback.get(visualEdgeFallbackKey(member))
    const currentId = visualEdgeId(current) || visualEdgeFallbackKey(current)
    const sourceId = visualEdgeSourceId(current)
    const targetId = visualEdgeTargetId(current)
    const sourceNode = visibleNodeById.get(sourceId)
    const targetNode = visibleNodeById.get(targetId)
    if (
      !current
      || visualEntityStatus(current) === 'hidden'
      || !sourceNode
      || !targetNode
      || seen.has(currentId)
    ) return
    seen.add(currentId)
    currentMembers.push({
      ...current,
      source_name: current?.source_name || sourceNode?.name || '',
      target_name: current?.target_name || targetNode?.name || '',
    })
  })
  if (!currentMembers.length) return null

  if (!groupKey) {
    return {
      ...selection,
      data: { ...currentMembers[0] },
    }
  }

  const first = currentMembers[0]
  if (groupKey === 'selfLoopEdges') {
    return {
      ...selection,
      data: {
        isSelfLoopGroup: true,
        source_node_uuid: visualEdgeSourceId(first),
        target_node_uuid: visualEdgeTargetId(first),
        source_name: first.source_name,
        target_name: first.target_name,
        selfLoopCount: currentMembers.length,
        selfLoopEdges: currentMembers,
        attributes: {
          ...(first.attributes || {}),
          aggregate_count: currentMembers.length,
          is_self_loop_group: true,
        },
      },
    }
  }

  const firstLabel = first.name || first.fact_type || first.type || 'RELATED'
  return {
    ...selection,
    data: {
      ...first,
      name: currentMembers.length > 1 ? `${firstLabel}（${currentMembers.length}）` : firstLabel,
      isParallelGroup: true,
      parallelEdges: currentMembers,
      attributes: {
        ...(first.attributes || {}),
        aggregate_count: currentMembers.length,
        is_parallel_group: true,
      },
    },
  }
}

export const selectPairFallbackEdgeIds = (edges, pairStates) => {
  const activePairs = pairStates instanceof Map ? pairStates : new Map()
  if (!activePairs.size) return new Set()
  const selected = new Map()
  asArray(edges).forEach((edge, index) => {
    const id = visualEdgeId(edge)
    const pairKey = `${visualEdgeSourceId(edge)}->${visualEdgeTargetId(edge)}`
    if (!id || !activePairs.has(pairKey)) return
    const candidate = { id, index }
    const current = selected.get(pairKey)
    if (
      !current
      || candidate.id < current.id
      || (candidate.id === current.id && candidate.index < current.index)
    ) {
      selected.set(pairKey, candidate)
    }
  })
  return new Set([...selected.values()].map(candidate => candidate.id))
}

const frameRound = frame => {
  const round = Number(frame?.round ?? frame?.round_num)
  return Number.isFinite(round) ? round : null
}

const mergeFramesByRound = (currentFrames, incomingFrames) => {
  const merged = []
  const seenRounds = new Set()
  const append = (frame) => {
    if (!frame || typeof frame !== 'object') return
    const round = frameRound(frame)
    if (round !== null) {
      if (seenRounds.has(round)) return
      seenRounds.add(round)
    }
    merged.push({ frame, round, order: merged.length })
  }
  asArray(currentFrames).forEach(append)
  asArray(incomingFrames).forEach(append)
  return merged
    .sort((left, right) => {
      if (left.round === null && right.round === null) return left.order - right.order
      if (left.round === null) return 1
      if (right.round === null) return -1
      return left.round - right.round || left.order - right.order
    })
    .map(item => item.frame)
}

export const mergeAnimationPayload = (currentPayload, incomingPayload) => {
  if (!currentPayload || !incomingPayload) return incomingPayload || currentPayload
  const currentTimeline = currentPayload.timeline && typeof currentPayload.timeline === 'object'
    ? currentPayload.timeline
    : {}
  const incomingTimeline = incomingPayload.timeline && typeof incomingPayload.timeline === 'object'
    ? incomingPayload.timeline
    : {}
  const eventById = new Map()
  ;[
    ...asArray(currentTimeline.events),
    ...asArray(incomingTimeline.events),
  ].forEach((event, index) => {
    if (!event || typeof event !== 'object') return
    const id = asId(event.id || event.event_id || `timeline-event-${index}`)
    if (!eventById.has(id)) eventById.set(id, event)
  })
  const events = [...eventById.values()].sort((left, right) => {
    const roundDelta = asFiniteNumber(left?.round, 0) - asFiniteNumber(right?.round, 0)
    if (roundDelta !== 0) return roundDelta
    const sequenceDelta = asFiniteNumber(left?.sequence, 0) - asFiniteNumber(right?.sequence, 0)
    if (sequenceDelta !== 0) return sequenceDelta
    return asId(left?.id || left?.event_id).localeCompare(asId(right?.id || right?.event_id))
  })
  const grouped = new Map()
  events.forEach((event) => {
    const round = asFiniteNumber(event?.round, 0)
    if (!grouped.has(round)) grouped.set(round, [])
    grouped.get(round).push(event)
  })
  const rounds = [...grouped.entries()]
    .sort((left, right) => left[0] - right[0])
    .map(([round, items]) => ({
      round,
      event_ids: items.map(item => asId(item?.id || item?.event_id)).filter(Boolean),
      start_sequence: asFiniteNumber(items[0]?.sequence, 0),
      end_sequence: asFiniteNumber(items[items.length - 1]?.sequence, 0),
    }))

  return {
    ...currentPayload,
    ...incomingPayload,
    frames: mergeFramesByRound(currentPayload.frames, incomingPayload.frames),
    timeline: {
      ...currentTimeline,
      ...incomingTimeline,
      events,
      rounds,
    },
  }
}

export const getTimelineEvents = payload => collectTimelineEvents(payload)
