import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Process from '../views/MainView.vue'
import MapSeedView from '../views/MapSeedView.vue'
import SimulationView from '../views/SimulationView.vue'
import SimulationRunView from '../views/SimulationRunView.vue'
import AnalysisView from '../views/AnalysisView.vue'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: Home
  },
  {
    path: '/process/:projectId',
    name: 'Process',
    component: Process,
    props: true
  },
  {
    path: '/map-seed/:seedId?',
    name: 'MapSeed',
    component: MapSeedView,
    props: true
  },
  {
    path: '/simulation/:simulationId',
    name: 'Simulation',
    component: SimulationView,
    props: true
  },
  {
    path: '/simulation/:simulationId/start',
    name: 'SimulationRun',
    component: SimulationRunView,
    props: true
  },
  {
    path: '/analysis/:reportId',
    name: 'Analysis',
    component: AnalysisView,
    props: true
  },
  {
    path: '/report/:reportId',
    name: 'Report',
    redirect: to => ({
      name: 'Analysis',
      params: { reportId: to.params.reportId },
      query: { ...to.query, tab: 'report' }
    })
  },
  {
    path: '/interaction/:reportId',
    name: 'Interaction',
    redirect: to => ({
      name: 'Analysis',
      params: { reportId: to.params.reportId },
      query: { ...to.query, tab: 'node-explore' }
    })
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
