import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import LoginView from '../views/auth/LoginView.vue'
import AdminLayout from '../layouts/AdminLayout.vue'
import CounterLayout from '../layouts/CounterLayout.vue'
import CycleCountListView from '../views/admin/CycleCountListView.vue'
import ActivityLogsView from '../views/admin/ActivityLogsView.vue'
import UserManagementView from '../views/admin/UserManagementView.vue'
import SelectWarehouseView from '../views/counter/SelectWarehouseView.vue'
import CountingView from '../views/counter/CountingView.vue'
import { readCounterSession } from '../services/counterSession.js'

const routes = [
  { path: '/', redirect: '/counter/cycle-counts' },
  { path: '/login', component: LoginView, meta: { guest: true } },
  {
    path: '/admin',
    component: AdminLayout,
    meta: { requiresAuth: true, roles: ['admin'] },
    children: [
      { path: '', redirect: '/admin/cycle-counts' },
      { path: 'cycle-counts', component: CycleCountListView },
      { path: 'users', component: UserManagementView, meta: { roles: ['admin'] } },
      { path: 'activity-logs', component: ActivityLogsView },
    ]
  },
  {
    path: '/counter',
    component: CounterLayout,
    children: [
      { path: '', redirect: '/counter/cycle-counts' },
      { path: 'cycle-counts', component: SelectWarehouseView },
      { path: 'select-warehouse', redirect: '/counter/cycle-counts' },
      // Redirect the old warehouse/count URL to the current count route using the cycleCount ID.
      { path: 'count/:warehouse/:cycleCount', redirect: to => `/counter/count/${to.params.cycleCount}` },
      { path: 'count/:cycleCount', component: CountingView },
    ]
  },
  { path: '/:pathMatch(.*)*', redirect: '/login' }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  // Reset scroll to the top on navigation. Troubleshoot: router scroll handling when the page position is incorrect.
  scrollBehavior() {
    return { top: 0, left: 0 }
  },
})
// Route guard: restore the staff session and check roles. Troubleshoot: redirect loops, /auth/me/, and route metadata.
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  // Check whether any matched route requires authentication.
  if (to.meta.guest || to.matched.some(r => r.meta.requiresAuth)) {
    try {
      await auth.restore()
    } catch {
      if (!to.meta.guest) return '/login'
    }
  }
  if (to.meta.guest && auth.isLoggedIn && auth.isAdmin) return '/admin'
  // Find the closest matched route that defines role permissions.
  const matchedRoles = [...to.matched].reverse().find(r => r.meta.roles)?.meta.roles || []
  // Check whether any matched route requires authentication.
  if (to.matched.some(r => r.meta.requiresAuth) && !auth.isLoggedIn) return '/login'
  if (matchedRoles.length && !matchedRoles.includes(auth.user?.role)) return auth.isAdmin ? '/admin' : '/counter'
  // Counting still requires the Counter PIN session created on the selection page.
  if (to.path.startsWith('/counter/count/') && !readCounterSession(to.params.cycleCount)?.token) {
    return '/counter/cycle-counts'
  }
})

// When the staff session expires, clear the auth store and redirect administrator pages to login.
window.addEventListener('wms-session-expired', () => {
  useAuthStore().clearSession()
  if (router.currentRoute.value.path.startsWith('/admin')) router.replace('/login')
})

export default router
