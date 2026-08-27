import { createRouter, createWebHistory } from 'vue-router'
import TodayView from './views/TodayView.vue'
import UnderstandingView from './views/UnderstandingView.vue'
import RecoveryView from './views/RecoveryView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/today' },
    { path: '/today', component: TodayView },
    { path: '/study', component: UnderstandingView },
    { path: '/recovery', component: RecoveryView },
    { path: '/memories', redirect: '/today' },
    { path: '/review', redirect: '/recovery' },
    { path: '/evaluation', redirect: '/today' },
    { path: '/demo/:feature', redirect: '/recovery' },
    { path: '/:pathMatch(.*)*', redirect: '/today' },
  ],
})
