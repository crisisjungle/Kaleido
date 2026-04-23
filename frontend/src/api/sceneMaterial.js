import service, { requestWithRetry } from './index'

export const composeSceneMaterial = (formData) => {
  return requestWithRetry(
    () => service({
      url: '/api/scene/compose',
      method: 'post',
      data: formData,
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    }),
    2,
    1000
  )
}

export const getSceneMaterial = (sceneId) => {
  return service.get(`/api/scene/seed/${sceneId}`)
}

export const reviseSceneMaterial = (sceneId, data) => {
  return requestWithRetry(
    () => service.post(`/api/scene/seed/${sceneId}/revise`, data),
    2,
    1000
  )
}
