import service, { requestWithRetry } from './index'

/**
 * 开始报告生成
 * @param {Object} data - { simulation_id, force_regenerate? }
 */
export const generateReport = (data) => {
  return requestWithRetry(() => service.post('/api/report/generate', data), 3, 1000)
}

/**
 * 获取报告生成状态
 * @param {string} reportId
 */
export const getReportStatus = (reportId) => {
  return service.get(`/api/report/generate/status`, { params: { report_id: reportId } })
}

/**
 * 获取 Agent 日志（增量）
 * @param {string} reportId
 * @param {number} fromLine - 从第几行开始获取
 */
export const getAgentLog = (reportId, fromLine = 0) => {
  return service.get(`/api/report/${reportId}/agent-log`, { params: { from_line: fromLine } })
}

/**
 * 获取控制台日志（增量）
 * @param {string} reportId
 * @param {number} fromLine - 从第几行开始获取
 */
export const getConsoleLog = (reportId, fromLine = 0) => {
  return service.get(`/api/report/${reportId}/console-log`, { params: { from_line: fromLine } })
}

/**
 * 获取报告详情
 * @param {string} reportId
 */
export const getReport = (reportId) => {
  return service.get(`/api/report/${reportId}`)
}

/**
 * 获取结果分析总览
 * @param {string} reportId
 */
export const getReportAnalysisOverview = (reportId) => {
  return service.get(`/api/report/${reportId}/analysis/overview`)
}

/**
 * 获取结果分析标签数据
 * @param {string} reportId
 * @param {string} tabId
 */
export const getReportAnalysisTab = (reportId, tabId) => {
  return service.get(`/api/report/${reportId}/analysis/tab/${tabId}`)
}

/**
 * 获取结果分析图谱
 * @param {string} reportId
 */
export const getReportAnalysisGraph = (reportId) => {
  return service.get(`/api/report/${reportId}/analysis/graph`)
}

/**
 * 获取节点上下文
 * @param {string} reportId
 * @param {Object} data - { node_id, round_range? }
 */
export const getReportNodeContext = (reportId, data) => {
  return requestWithRetry(() => service.post(`/api/report/${reportId}/analysis/node/context`, data), 2, 600)
}

/**
 * 节点深度探索
 * @param {string} reportId
 * @param {Object} data - { node_id, round_range? }
 */
export const exploreReportNode = (reportId, data) => {
  return requestWithRetry(() => service.post(`/api/report/${reportId}/analysis/node/explore`, data), 2, 800)
}

/**
 * 节点上下文追问
 * @param {string} reportId
 * @param {Object} data - { node_id, message, chat_history?, round_range? }
 */
export const chatWithReportNode = (reportId, data) => {
  return requestWithRetry(() => service.post(`/api/report/${reportId}/analysis/node/chat`, data), 2, 800)
}

/**
 * 与 Report Agent 对话
 * @param {Object} data - { simulation_id, message, chat_history? }
 */
export const chatWithReport = (data) => {
  return requestWithRetry(() => service.post('/api/report/chat', data), 3, 1000)
}
