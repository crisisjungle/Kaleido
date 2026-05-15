import service from './index'

export const generateReport = (data) => service.post('/api/report/generate', data)
export const getReport = (reportId) => service.get(`/api/report/${reportId}`)
export const getReportProgress = (reportId) => service.get(`/api/report/${reportId}/progress`)
export const getReportSections = (reportId) => service.get(`/api/report/${reportId}/sections`)
export const getReportConsoleLog = (reportId, fromLine = 0) => service.get(`/api/report/${reportId}/console-log`, { params: { from_line: fromLine } })
export const getReportAgentLog = (reportId, fromLine = 0) => service.get(`/api/report/${reportId}/agent-log`, { params: { from_line: fromLine } })

export const getReportAnalysisGraph = (reportId) => service.get(`/api/report/${reportId}/analysis/graph`)
export const getReportAnalysisOverview = (reportId) => service.get(`/api/report/${reportId}/analysis/overview`)
export const getReportAnalysisTab = (reportId, tabId) => service.get(`/api/report/${reportId}/analysis/tab/${tabId}`)
export const getReportNodeContext = (reportId, data) => service.post(`/api/report/${reportId}/analysis/node/context`, data)
export const exploreReportNode = (reportId, data) => service.post(`/api/report/${reportId}/analysis/node/explore`, data)
export const chatWithReportNode = (reportId, data) => service.post(`/api/report/${reportId}/analysis/node/chat`, data)
