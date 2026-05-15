import service, { requestWithRetry } from './index'

export const geocodeMapLocation = (data) => service.post('/api/map/geocode', data)
export const reverseGeocodeMapLocation = (data) => service.post('/api/map/reverse-geocode', data)
export const createMapSeed = (data) => requestWithRetry(() => service.post('/api/map/seed', data), 2, 1000)
export const getMapSeedStatus = (data) => service.post('/api/map/seed/status', data)
export const getMapSeed = (seedId) => service.get(`/api/map/seed/${seedId}`)
export const getMapSeedLayers = (seedId) => service.get(`/api/map/seed/${seedId}/layers`)
export const convertMapSeedToSimulation = (seedId, data = {}) => service.post(`/api/map/seed/${seedId}/to-simulation`, data)
