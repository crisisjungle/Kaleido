const PROVIDER_LABELS = {
  overpass: 'OSM 地点与边界',
  worldcover: 'ESA WorldCover 地表覆盖'
}

function normalizedStatus(provider = {}) {
  return String(provider.status || '').trim().toLowerCase()
}

function attemptCount(provider = {}) {
  const attempts = Array.isArray(provider.live_attempts)
    ? provider.live_attempts
    : (Array.isArray(provider.attempts) ? provider.attempts : [])
  return attempts.filter((item) => String(item?.status || '').toLowerCase() === 'failed').length
}

function failureReason(provider = {}) {
  const text = String(provider.live_error || provider.error || '').trim().toLowerCase()
  const httpCode = text.match(/(?:http(?: error)?\s*)?(4\d\d|5\d\d)/)?.[1]

  if (/out of memory|maxsize|resource limit|memory limit/.test(text)) {
    return '查询范围超过公开服务的资源上限'
  }
  if (/timed?\s*out|timeout/.test(text)) return '请求超时'
  if (/429|too many requests|rate.?limit/.test(text)) return '公开服务触发限流'
  if (/remote end closed|connection reset|connection aborted|broken pipe|eof/.test(text)) {
    return '远端服务中断了连接'
  }
  if (/name or service not known|temporary failure in name resolution|nodename nor servname|dns/.test(text)) {
    return '域名解析失败'
  }
  if (/ssl|certificate|tls/.test(text)) return '安全连接建立失败'
  if (/no overpass endpoint configured/.test(text)) return '系统尚未配置可用的地点数据服务'
  if (/urlopen error|connection refused|network is unreachable/.test(text)) return '当前网络无法连接该服务'
  if (httpCode) return `空间数据服务暂时不可用（状态码 ${httpCode}）`
  return '服务请求未成功'
}

function attemptsSuffix(provider = {}) {
  const count = attemptCount(provider)
  return count > 0 ? `，已尝试 ${count} 次` : ''
}

function describeOverpass(provider = {}, formalReady = false) {
  const status = normalizedStatus(provider)
  if (status === 'completed' || status === 'ready') {
    if (formalReady) return '已取得可用于本轮判断的具名地点与边界。'
    return '服务已返回数据，但经过分析范围、用户关注点和尺度筛选后，没有留下可用于正式判断的地点或边界。'
  }
  if (status === 'empty') {
    return '服务可以连接，但没有返回当前范围内可用于正式判断的具名地点或边界。'
  }
  if (status === 'cached') {
    if (formalReady) return '实时连接未成功，当前使用有效缓存中的具名地点与边界。'
    return `实时连接未成功，缓存中也没有适合本轮判断的地点或边界（${failureReason(provider)}${attemptsSuffix(provider)}）。`
  }
  if (status === 'partial') {
    if (formalReady) {
      return `已取得可用于本轮判断的地点或边界；部分主题数据未返回${attemptsSuffix(provider)}。`
    }
    return `仅返回了部分数据，但没有留下可用于正式判断的地点或边界${attemptsSuffix(provider)}。`
  }
  return `${failureReason(provider)}${attemptsSuffix(provider)}，未取得具名地点与边界。`
}

function describeWorldCover(provider = {}) {
  const status = normalizedStatus(provider)
  if (status === 'completed' || status === 'ready' || status === 'cached') {
    return '已取得地表覆盖背景；该覆盖图层只用于显示，不作为地点、边界或代理体的正式依据。'
  }
  if (status === 'empty') {
    return '服务可以连接，但没有返回可显示的地表覆盖；该来源本身也不负责地点识别。'
  }
  return `${failureReason(provider)}${attemptsSuffix(provider)}。该来源即使恢复，也只补充地表背景，不负责地点识别。`
}

export function isSpatialEvidenceUnavailable(dataQuality) {
  return dataQuality?.formal_ready === false
}

export function buildSpatialProviderRows(dataQuality) {
  const providers = dataQuality?.providers || {}
  const failures = Array.isArray(dataQuality?.provider_failures)
    ? dataQuality.provider_failures
    : []
  const failureFor = (providerNames) => failures.find((item) => (
    providerNames.includes(String(item?.provider || '').trim().toLowerCase())
  )) || {}
  const overpass = Object.keys(providers.overpass || {}).length
    ? providers.overpass
    : failureFor(['overpass', 'osm', 'osm_overpass'])
  const worldcover = Object.keys(providers.worldcover || {}).length
    ? providers.worldcover
    : failureFor(['worldcover', 'worldcover_wms', 'esa_worldcover'])
  const formalReady = dataQuality?.formal_ready === true
  return [
    {
      key: 'overpass',
      label: PROVIDER_LABELS.overpass,
      detail: describeOverpass(overpass, formalReady),
      formalSource: true
    },
    {
      key: 'worldcover',
      label: PROVIDER_LABELS.worldcover,
      detail: describeWorldCover(worldcover),
      formalSource: false
    }
  ]
}
