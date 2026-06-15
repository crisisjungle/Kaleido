import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'Home', component: () => import('../views/HomeView.vue') },
  { path: '/demo/wuhan', name: 'WuhanDemo', component: () => import('../views/WuhanDemoView.vue') },
  { path: '/history', name: 'History', component: () => import('../views/HistoryView.vue') },
  { path: '/scene-composer', name: 'SceneComposer', component: () => import('../views/SceneComposerView.vue') },
  { path: '/process/:projectId?', name: 'Process', component: () => import('../views/MainView.vue') },
  { path: '/simulation/:simulationId', name: 'Simulation', component: () => import('../views/SimulationView.vue') },
  { path: '/simulation/:simulationId/start', name: 'SimulationRun', component: () => import('../views/SimulationRunView.vue') },
  { path: '/analysis/:reportId', name: 'Analysis', component: () => import('../views/AnalysisView.vue') },
  { path: '/report/:reportId', redirect: to => ({ name: 'Analysis', params: to.params, query: { ...to.query, tab: 'report' } }) },
  { path: '/interaction/:reportId', redirect: to => ({ name: 'Analysis', params: to.params, query: { ...to.query, tab: 'node-explore' } }) },
  { path: '/space-forecast', name: 'SpaceForecast', component: () => import('../views/SpaceForecastView.vue') },
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  }
})

export default router
