import service from './index'

export const forceStopAll = (data = {}) => {
  return service.post('/api/control/force-stop', data)
}
