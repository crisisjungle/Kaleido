export const SHELL_IDS = [
  '300-500',
  '500-600',
  '600-700',
  '700-900',
  '900-1200',
  '1200-1400'
]

export const COLLISION_TYPE_IDS = [
  'small',
  'iridium_like',
  'large_catastrophic',
  'asat_like'
]

export const DEFAULT_SIMULATION_PACING = {
  logicStepMonths: 1,
  visualTickMs: 800,
  monthsPerTick: 12,
  minVisualSecondsBeforeStop: 75,
  minSimMonthsBeforeThresholdStop: 72,
  followOnCollisionCooldownMonths: 12,
  hardLimitYears: 120
}

export const COLLISION_LABELS = {
  small: '一级碰撞',
  iridium_like: '二级碰撞',
  large_catastrophic: '三级碰撞',
  asat_like: '四级碰撞'
}

export const COLLISION_DESCRIPTIONS = {
  small: '小型航天器或碎片相撞，形成局部碎片云。',
  iridium_like: '类似 Iridium-Cosmos 卫星相撞，产生大量可追踪碎片。',
  large_catastrophic: '大型平台灾难性解体，风险开始向相邻壳层扩散。',
  asat_like: '类似 ASAT 反卫星高碎裂事件，形成高速跨壳层碎片云。'
}
