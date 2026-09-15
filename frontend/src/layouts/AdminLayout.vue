<script setup>
import { ref, watch } from 'vue'
import {
  ClipboardList,
  ChevronLeft,
  ChevronRight,
  LogOut,
  Menu,
  ScrollText,
  UsersRound,
  X,
} from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import csIcon from '../assets/CS_ICO.ico'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const collapsed = ref(localStorage.getItem('wms-admin-sidebar') === 'collapsed')
const mobileOpen = ref(false)

// Close the mobile menu when the route changes.
watch(() => route.fullPath, () => {
  mobileOpen.value = false
})

// Toggle the sidebar and save the preference. Troubleshoot: wms-admin-sidebar in localStorage.
function toggleSidebar() {
  collapsed.value = !collapsed.value
  localStorage.setItem('wms-admin-sidebar', collapsed.value ? 'collapsed' : 'expanded')
}

const logoutError = ref('')
const loggingOut = ref(false)
// Log out and clear the session. Troubleshoot: auth.logout or /auth/logout/ if logout fails.
async function logout() {
  loggingOut.value = true
  logoutError.value = ''
  try {
    await auth.logout()
    await router.push('/login')
  } catch (error) {
    logoutError.value = error.message
  } finally {
    loggingOut.value = false
  }
}
</script>

<template>
  <div :class="['admin-shell', { collapsed, 'mobile-open': mobileOpen }]">
    <button
      v-if="mobileOpen"
      class="sidebar-backdrop"
      type="button"
      aria-label="Close navigation"
      @click="mobileOpen = false"
    ></button>

    <aside id="admin-sidebar" class="sidebar" aria-label="Admin navigation">
      <div class="logo">
        <div class="logo-icon"><img :src="csIcon" alt="" /></div>
        <div class="logo-copy"><strong>WMS WEB</strong><small>Cycle Count</small></div>
        <button class="mobile-close" type="button" aria-label="Close navigation" @click="mobileOpen = false"><X :size="21" /></button>
      </div>

      <button
        class="sidebar-toggle"
        type="button"
        :aria-label="collapsed ? 'Expand sidebar' : 'Collapse sidebar'"
        :title="collapsed ? 'Expand sidebar' : 'Collapse sidebar'"
        @click="toggleSidebar"
      >
        <ChevronRight v-if="collapsed" :size="20" stroke-width="2.5" />
        <ChevronLeft v-else :size="20" stroke-width="2.5" />
      </button>

      <nav>
        <RouterLink to="/admin/cycle-counts" title="Daily Cycle Count"><ClipboardList :size="20" /><span> Cycle Count</span></RouterLink>
        <RouterLink v-if="auth.user?.role === 'admin'" to="/admin/users" title="User Management"><UsersRound :size="20" /><span>User Management</span></RouterLink>
        <RouterLink to="/admin/activity-logs" title="Activity Logs"><ScrollText :size="20" /><span>Activity Logs</span></RouterLink>
      </nav>

      <button class="logout" type="button" title="Logout" :disabled="loggingOut" @click="logout"><LogOut :size="19" /><span>Logout</span></button>
      <p v-if="logoutError" role="alert">{{ logoutError }}</p>
    </aside>
    <section class="content">
      <header class="topbar">
        <button
          class="mobile-menu"
          type="button"
          aria-controls="admin-sidebar"
          :aria-expanded="mobileOpen"
          aria-label="Open navigation"
          @click="mobileOpen = true"
        ><Menu :size="22" /></button>
        <div class="user-pill" :title="auth.user?.name">{{ auth.user?.name }}</div>
      </header>
      <RouterView />
    </section>
  </div>
</template>

<style scoped>
.admin-shell{min-height:100vh;min-height:100dvh;display:grid;grid-template-columns:250px minmax(0,1fr);transition:grid-template-columns .25s ease}.admin-shell.collapsed{grid-template-columns:84px minmax(0,1fr)}.sidebar{position:sticky;top:0;height:100vh;height:100dvh;z-index:30;background:#17251c;color:#fff;padding:20px;display:flex;flex-direction:column;gap:24px;transition:padding .25s ease,transform .25s ease,box-shadow .25s ease}.logo{display:flex;align-items:center;gap:11px;min-height:42px;white-space:nowrap}.logo-icon{width:42px;height:42px;flex:0 0 42px;border-radius:12px;background:#e9f7ec;color:#166534;display:grid;place-items:center;overflow:hidden}.logo-icon img{width:32px;height:32px;object-fit:contain}.logo strong,.logo small{display:block}.logo small{color:#9fb3a4;margin-top:2px}.logo-copy,nav a span,.logout span{overflow:hidden;transition:opacity .15s ease,width .25s ease}.sidebar-toggle{position:absolute;right:-39px;top:76px;width:40px;height:44px;border:1px solid #dce5de;border-left:0;border-radius:0 11px 11px 0;background:#fff;color:#166534;display:grid;place-items:center;box-shadow:5px 3px 12px rgba(15,23,42,.12);z-index:2;cursor:pointer;transition:color .18s ease,background .18s ease,box-shadow .18s ease}.sidebar-toggle:hover{background:#edf7ef;color:#14532d;box-shadow:5px 4px 15px rgba(15,23,42,.17)}.sidebar-toggle:focus-visible{outline:3px solid rgba(34,197,94,.3);outline-offset:2px}.mobile-close,.mobile-menu{display:none}nav{display:grid;gap:6px}nav a{min-height:44px;color:#cbd8ce;text-decoration:none;padding:11px 12px;border-radius:10px;display:flex;align-items:center;gap:10px;font-weight:700;white-space:nowrap}nav a svg{flex:0 0 auto}nav a:hover{background:rgba(255,255,255,.06);color:#fff}nav a.router-link-active{background:#255c36;color:#fff}.logout{margin-top:auto;min-height:44px;border:0;background:transparent;color:#d7e2da;padding:10px 12px;display:flex;gap:9px;align-items:center;font-weight:700;white-space:nowrap}.logout:hover{background:rgba(255,255,255,.06);color:#fff;border-radius:9px}.content{min-width:0}.topbar{height:68px;background:#fff;border-bottom:1px solid #e4e9e5;display:flex;align-items:center;justify-content:flex-end;padding:0 28px}.user-pill{max-width:260px;overflow:hidden;padding:8px 12px;border-radius:999px;background:#edf7ef;color:#166534;font-weight:800;font-size:13px;text-overflow:ellipsis;white-space:nowrap}.sidebar-backdrop{display:none}
.collapsed .sidebar{padding-left:14px;padding-right:14px}.collapsed .logo-copy,.collapsed nav a span,.collapsed .logout span{width:0;opacity:0}.collapsed nav a,.collapsed .logout{justify-content:center;padding-left:0;padding-right:0}.collapsed .logo{justify-content:center}
@media(max-width:800px){.admin-shell,.admin-shell.collapsed{display:block}.sidebar{position:fixed;left:0;top:0;width:min(280px,calc(100vw - 44px));padding:20px;height:100dvh;transform:translateX(-105%);box-shadow:none}.mobile-open .sidebar{transform:translateX(0);box-shadow:14px 0 35px rgba(15,23,42,.25)}.collapsed .sidebar{padding:20px}.collapsed .logo{justify-content:flex-start}.collapsed .logo-copy,.collapsed nav a span,.collapsed .logout span{width:auto;opacity:1}.collapsed nav a,.collapsed .logout{justify-content:flex-start;padding-left:12px;padding-right:12px}.sidebar-toggle{display:none}.mobile-close{margin-left:auto;width:44px;height:44px;border:0;border-radius:10px;background:rgba(255,255,255,.08);color:#fff;display:grid;place-items:center}.sidebar-backdrop{display:block;position:fixed;inset:0;z-index:25;border:0;background:rgba(15,23,42,.48);backdrop-filter:blur(2px)}.topbar{height:64px;padding:0 14px;position:sticky;top:0;z-index:20;justify-content:space-between}.mobile-menu{width:44px;height:44px;border:1px solid #dce5de;border-radius:10px;background:#fff;color:#166534;display:grid;place-items:center}.user-pill{max-width:min(180px,calc(100vw - 90px))}}
</style>
