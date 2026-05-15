import service, { requestWithRetry } from './index'

export const generateOntology = (data) => requestWithRetry(() => service.post('/api/graph/ontology/generate', data, {
  headers: { 'Content-Type': 'multipart/form-data' }
}), 3, 1000)

export const buildGraph = (data) => requestWithRetry(() => service.post('/api/graph/build', data), 3, 1000)
export const getTaskStatus = (taskId) => service.get(`/api/graph/task/${taskId}`)
export const getGraphData = (graphId) => service.get(`/api/graph/data/${graphId}`)
export const getProject = (projectId) => service.get(`/api/graph/project/${projectId}`)
export const listProjects = () => service.get('/api/graph/project/list')
export const deleteProject = (projectId) => service.delete(`/api/graph/project/${projectId}`)
export const resetProject = (projectId) => service.post(`/api/graph/project/${projectId}/reset`)
