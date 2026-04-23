import service, { requestWithRetry } from './index'

export const createMapSeed = (data) => {
  return requestWithRetry(() => service.post('/api/map/seed', data), 3, 1000)
}

export const geocodeMapLocation = (data) => {
  return requestWithRetry(() => service.post('/api/map/geocode', data), 3, 1000)
}

export const reverseGeocodeMapLocation = (data) => {
  return requestWithRetry(() => service.post('/api/map/reverse-geocode', data), 3, 1000)
}

export const getMapSeedStatus = (data) => {
  return service.post('/api/map/seed/status', data)
}

export const getMapSeed = (seedId) => {
  return service.get(`/api/map/seed/${seedId}`)
}

export const getMapSeedLayers = (seedId) => {
  return service.get(`/api/map/seed/${seedId}/layers`)
}

export const convertMapSeedToSimulation = (seedId, data = {}) => {
  return requestWithRetry(
    () => service.post(`/api/map/seed/${seedId}/to-simulation`, data),
    3,
    1000
  )
}
