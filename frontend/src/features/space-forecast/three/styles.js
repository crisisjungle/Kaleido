export const EARTH_RADIUS = 3

export const SHELL_VISUAL_SCALE = 0.0017

export const PARTICLE_STYLE = {
  active_satellite: {
    color: '#38bdf8',
    size: 0.024,
    opacity: 0.82,
    label: '活跃卫星'
  },
  derelict_satellite: {
    color: '#facc15',
    size: 0.03,
    opacity: 0.9,
    label: '失效卫星'
  },
  large_debris: {
    color: '#fb923c',
    size: 0.024,
    opacity: 0.82,
    label: '大型碎片'
  },
  medium_debris: {
    color: '#cbd5e1',
    size: 0.018,
    opacity: 0.72,
    label: '中型碎片'
  },
  micro_debris: {
    color: '#64748b',
    size: 0.012,
    opacity: 0.5,
    label: '微小碎片'
  }
}

export const PARTICLE_LIMITS = {
  active_satellite: 2400,
  derelict_satellite: 300,
  large_debris: 500,
  medium_debris: 900,
  micro_debris: 1200
}

export const COLLISION_VISUAL_PRESET = {
  small: {
    label: '一级碰撞',
    burstParticles: 140,
    flashRadius: 0.05,
    shockwaveRadius: 0.12
  },
  iridium_like: {
    label: '二级碰撞',
    burstParticles: 320,
    flashRadius: 0.08,
    shockwaveRadius: 0.22
  },
  large_catastrophic: {
    label: '三级碰撞',
    burstParticles: 600,
    flashRadius: 0.12,
    shockwaveRadius: 0.35
  },
  asat_like: {
    label: '四级碰撞',
    burstParticles: 1000,
    flashRadius: 0.2,
    shockwaveRadius: 0.48
  }
}
