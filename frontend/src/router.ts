import { createRouter, createWebHistory } from 'vue-router'
import TodayView from './views/TodayView.vue'
import UnderstandingView from './views/UnderstandingView.vue'
import RecoveryView from './views/RecoveryView.vue'
import ProfileView from './views/ProfileView.vue'
import FocusTimerView from './views/FocusTimerView.vue'
import TutorSessionView from './views/TutorSessionView.vue'

export const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(_, __, savedPosition) {
    if (savedPosition) return savedPosition
    if (_.hash) return { el: _.hash, behavior: 'smooth' }
    return { top: 0 }
  },
  routes: [
    { path: '/', redirect: '/today' },
    { path: '/today', component: TodayView },
    { path: '/study', component: UnderstandingView },
    { path: '/study/session', component: TutorSessionView },
    { path: '/focus', component: FocusTimerView },
    { path: '/recovery', component: RecoveryView },
    { path: '/memories', redirect: '/profile#memories' },
    { path: '/review', redirect: '/recovery' },
    { path: '/evaluation', redirect: '/today' },
    { path: '/profile', component: ProfileView },
    { path: '/demo/:feature', redirect: '/recovery' },
    { path: '/:pathMatch(.*)*', redirect: '/today' },
  ],
})
