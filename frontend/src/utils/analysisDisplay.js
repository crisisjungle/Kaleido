import { safeDisplayText } from './displayText.js'

const REGION_PLACEHOLDER_RE = /^(?:区域|子区域|未命名(?:区域|子区域)?|未知(?:区域|子区域)?|待识别(?:区域|子区域)?|待确认(?:区域|子区域)?|暂无(?:区域|子区域)?|其他(?:区域|子区域)?)$/
const CHINESE_TEXT_RE = /[\u3400-\u9fff]/

const validRegionName = (value) => {
  const text = safeDisplayText(value, '').trim()
  if (!text || !CHINESE_TEXT_RE.test(text) || REGION_PLACEHOLDER_RE.test(text)) return ''
  return text
}

/**
 * 将角色透镜的区域影响项收敛为可展示数据。
 *
 * 报告数据可能只携带区域 ID，也可能被旧数据清洗为“未命名区域”。
 * ID 会优先交给调用方的真实区域查表解析；解析不到有效中文地名时，
 * 该项不进入界面，避免用占位词伪装成分析结论。
 */
export function normalizeDominantRegions(regions, resolveName = () => '') {
  if (!Array.isArray(regions)) return []

  const seen = new Set()
  const result = []

  regions.forEach((region) => {
    if (!region || typeof region !== 'object') return

    const candidates = [region.region_name, region.name, region.region_id]
    let displayName = ''

    for (const candidate of candidates) {
      if (candidate === null || candidate === undefined || candidate === '') continue
      displayName = validRegionName(resolveName(candidate)) || validRegionName(candidate)
      if (displayName) break
    }

    if (!displayName || seen.has(displayName)) return
    seen.add(displayName)
    result.push({ ...region, display_name: displayName })
  })

  return result
}
