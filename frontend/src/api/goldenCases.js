import service from './index'

export const listGoldenCases = () => service.get('/api/golden-cases')
export const restoreGoldenCase = (caseId, data = {}) => service.post(`/api/golden-cases/${caseId}/restore`, data)
export const getGoldenCaseArtifact = (caseId, artifactName) => service.get(`/api/golden-cases/${caseId}/artifacts/${artifactName}`)
