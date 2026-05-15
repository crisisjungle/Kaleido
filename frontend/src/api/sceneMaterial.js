import service, { requestWithRetry } from './index'

export const composeSceneMaterial = (data) => requestWithRetry(() => service.post('/api/scene/compose', data, {
  headers: data instanceof FormData ? { 'Content-Type': 'multipart/form-data' } : undefined
}), 2, 1000)

export const getSceneMaterialSeed = (sceneId) => service.get(`/api/scene/seed/${sceneId}`)
export const reviseSceneMaterial = (sceneId, data) => requestWithRetry(() => service.post(`/api/scene/seed/${sceneId}/revise`, data), 2, 1000)
