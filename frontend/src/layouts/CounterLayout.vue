<script setup>
import { computed, provide } from 'vue'
import { ChevronLeft, Clock3, ServerOff, UserCog, WifiOff } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import csIcon from '../assets/CS_ICO.ico'
import { useCounterLock } from '../composables/useCounterLock.js'

const route = useRoute()
const router = useRouter()
// Check for a cycleCount route parameter to control the counting layout and heartbeat.
const isCounting = computed(() => Boolean(route.params.cycleCount))
// Check whether the current route is the cycle-count selection page.
const isCycleCountSelection = computed(() => route.path === '/counter/cycle-counts')
// Use the query code or route ID as the displayed count number.
const cycleCountNumber = computed(() => route.query.code || route.params.cycleCount)
// Share session and lock handling while keeping this layout responsible for navigation.
const {
  releasing, releaseError, showCycleCounts, connectionLost, deviceOffline,
  connectionRestored, lockExpired, lockSecondsRemaining,
  idleWarning, idleSecondsRemaining, continueCounting,
} = useCounterLock(
  // Track the route ID so lock timers follow the active cycle count.
  computed(() => route.params.cycleCount),
  // Return to the existing selection route after a successful unlock.
  () => router.push('/counter/cycle-counts'),
)
provide('counterConnection', { connectionLost, lockExpired })

// Format the estimated lock expiry as m:ss for the connection banner.
const lockCountdown = computed(() => {
  const minutes = Math.floor(lockSecondsRemaining.value / 60)
  const seconds = String(lockSecondsRemaining.value % 60).padStart(2, '0')
  return `${minutes}:${seconds}`
})

// Show the remaining idle grace period as m:ss in the warning dialog.
const idleCountdown = computed(() => {
  const minutes = Math.floor(idleSecondsRemaining.value / 60)
  const seconds = String(idleSecondsRemaining.value % 60).padStart(2, '0')
  return `${minutes}:${seconds}`
})

</script>

<template>
  <div :class="['counter-shell', { 'cycle-count-selection': isCycleCountSelection, 'counting-active': isCounting }]">
    <header class="counter-header">
      <div class="counter-topbar">
        <div class="counter-brand">
          <div class="brand-icon"><img :src="csIcon" alt="" /></div>
          <div>
            <strong>WMS Cycle Count</strong>
            <small>Mobile Counter</small>
          </div>
        </div>
<RouterLink
  v-if="!isCounting"
  class="header-button admin-button"
  to="/login"
  title="Admin Login"
  aria-label="Admin Login"
>
  <UserCog :size="18" />
  <span>Admin</span>
</RouterLink>

      </div>

      <div v-if="isCounting" class="count-context">
        <button class="header-button change-button" type="button" :disabled="releasing" @click="showCycleCounts">
          <ChevronLeft :size="19" />
          <span class="desktop-back-label">{{ releasing ? 'Leaving...' : 'Cycle Counts' }}</span>
          <span class="mobile-back-label">{{ releasing ? 'Wait...' : 'Back' }}</span>
        </button>
        <dl>
          <div><dt>Cycle Count No.</dt><dd>{{ cycleCountNumber }}</dd></div>
        </dl>
      </div>
      <p v-if="releaseError" class="release-error" role="alert">{{ releaseError }}</p>
    </header>

    <div v-if="isCounting && connectionLost" class="connection-backdrop" aria-hidden="true"></div>
    <aside v-if="isCounting && connectionLost" :class="['connection-banner', { expired: lockExpired }]" role="alert">
      <WifiOff v-if="deviceOffline" class="connection-icon" :size="36" aria-hidden="true" />
      <ServerOff v-else class="connection-icon" :size="36" aria-hidden="true" />
      <strong>{{ deviceOffline ? 'No network connection.' : 'WMS server is unavailable.' }}</strong>
      <span v-if="deviceOffline && !lockExpired">Please reconnect to the warehouse network. Your Cycle Count lock may expire in {{ lockCountdown }}.</span>
      <span v-else-if="deviceOffline">Please reconnect to the warehouse network. Your Cycle Count lock may have expired.</span>
      <span v-else-if="!lockExpired">Contact the IT Department. Your Cycle Count lock may expire in {{ lockCountdown }}.</span>
      <span v-else>Contact the IT Department. Your Cycle Count lock may have expired.</span>
    </aside>
    <aside v-else-if="isCounting && connectionRestored" class="connection-banner restored" role="status">
      <strong>Connected.</strong><span>Your Cycle Count session is active.</span>
    </aside>

    <div v-if="isCounting && idleWarning && !releasing" class="idle-backdrop"></div>
    <aside v-if="isCounting && idleWarning && !releasing" class="idle-warning" role="alertdialog" aria-modal="true" aria-labelledby="idle-warning-title">
      <Clock3 :size="38" aria-hidden="true" />
      <strong id="idle-warning-title">Are you still counting?</strong>
      <span>No activity was detected. This session will return to Cycle Counts in {{ idleCountdown }}. Saved actual counts will remain.</span>
      <button class="btn btn-primary" type="button" autofocus @click="continueCounting">Continue Counting</button>
    </aside>

    <RouterView />
  </div>
</template>

<style scoped>
.release-error{position:fixed;z-index:80;top:12px;left:50%;width:min(440px,calc(100% - 24px));transform:translateX(-50%);margin:0;padding:10px 12px;border:1px solid #fca5a5;border-radius:9px;background:#fef2f2;color:#991b1b;box-shadow:0 8px 24px rgba(15,23,42,.16);font-size:12px;font-weight:800;text-align:center}.change-button:disabled{opacity:.6;cursor:wait}
.connection-backdrop{position:fixed;z-index:74;inset:0;background:rgba(15,23,42,.16);-webkit-backdrop-filter:blur(2px);backdrop-filter:blur(2px)}
.connection-banner{position:fixed;z-index:75;top:50%;left:50%;width:min(500px,calc(100% - 28px));min-height:170px;transform:translate(-50%,-50%);display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px;border:1px solid #fb923c;border-radius:16px;background:#fff7ed;color:#9a3412;box-shadow:0 18px 48px rgba(15,23,42,.24);text-align:center}.connection-icon{flex:0 0 auto;margin-bottom:12px}.connection-banner strong,.connection-banner span{display:block}.connection-banner strong{font-size:18px}.connection-banner span{margin-top:8px;font-size:14px;font-weight:700;line-height:1.45}.connection-banner.expired{border-color:#f87171;background:#fff;color:#991b1b}.connection-banner.restored{top:calc(var(--counter-header-height,132px) + 8px);width:min(440px,calc(100% - 24px));min-height:0;transform:translateX(-50%);padding:10px 13px;border-color:#86efac;border-radius:10px;background:#f0fdf4;color:#166534}.connection-banner.restored strong{font-size:14px}.connection-banner.restored span{margin-top:2px;font-size:12px}
.idle-backdrop{position:fixed;z-index:76;inset:0;background:rgba(15,23,42,.42);-webkit-backdrop-filter:blur(2px);backdrop-filter:blur(2px)}.idle-warning{position:fixed;z-index:77;top:50%;left:50%;width:min(440px,calc(100% - 28px));transform:translate(-50%,-50%);display:flex;flex-direction:column;align-items:center;padding:24px;border:1px solid #86efac;border-radius:16px;background:#fff;color:#17351f;box-shadow:0 20px 56px rgba(15,23,42,.28);text-align:center}.idle-warning>svg{margin-bottom:10px;color:#15803d}.idle-warning strong{font-size:19px}.idle-warning span{margin-top:8px;color:#475569;font-size:14px;font-weight:700;line-height:1.5}.idle-warning .btn{width:100%;margin-top:18px;min-height:46px}
.counter-shell{--counter-header-height:132px;min-height:100vh;min-height:100dvh;background:#f4f7f4;overflow-x:clip}.counter-header{background:#fff;border-bottom:1px solid #dfe7e0;position:sticky;top:0;z-index:20;box-shadow:0 2px 12px rgba(15,23,42,.04)}.counter-topbar{min-height:68px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:10px max(24px,env(safe-area-inset-right)) 10px max(24px,env(safe-area-inset-left))}.counter-brand{display:flex;align-items:center;gap:10px;min-width:0}.brand-icon{width:42px;height:42px;flex:0 0 42px;border-radius:12px;background:#e7f6ea;color:#166534;display:grid;place-items:center;overflow:hidden}.brand-icon img{width:32px;height:32px;object-fit:contain}.counter-brand strong,.counter-brand small{display:block}.counter-brand strong{color:#17351f}.counter-brand small{font-size:12px;color:#64748b;margin-top:2px}.header-button{min-height:44px;border-radius:10px;border:1px solid #dce5de;background:#fff;color:#334155;display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:0 13px;font-weight:800;text-decoration:none}.header-button:hover{background:#f6faf7}.admin-button{flex:0 0 auto;color:#166534}.count-context{border-top:1px solid #edf1ed;padding:10px max(24px,env(safe-area-inset-right)) 10px max(24px,env(safe-area-inset-left));display:flex;align-items:center;gap:18px;background:#fbfdfb}.change-button{color:#166534;flex:0 0 auto}.mobile-back-label{display:none}.count-context dl{display:block;width:max-content;margin:0 0 0 auto;min-width:0;text-align:right}.count-context dl>div{min-width:0}.count-context dt{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#64748b;font-weight:800}.count-context dd{margin:2px 0 0;font-size:14px;color:#17211b;font-weight:900;overflow-wrap:anywhere}
@media(min-width:601px){.counter-shell.cycle-count-selection{height:100vh;min-height:0;display:flex;flex-direction:column;overflow:hidden}.cycle-count-selection>.counter-header{flex:0 0 auto}}
@media(max-width:700px){.counter-shell{--counter-header-height:119px}.counter-topbar{padding:9px 12px;min-height:62px}.counter-brand strong{font-size:15px}.counter-brand small{font-size:11px}.count-context{min-height:57px;padding:6px 12px;display:flex;justify-content:space-between;gap:10px}.change-button{width:auto;padding:0 11px}.desktop-back-label{display:none}.mobile-back-label{display:inline}.count-context dl{display:block;flex:1;margin-left:0;text-align:right}.count-context dt{font-size:9px}.count-context dd{margin-top:1px;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
@media(max-width:350px){.brand-icon{width:38px;height:38px;flex-basis:38px}.counter-brand{gap:8px}}
@media(max-width:420px){.admin-button span{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}.admin-button{width:44px;padding:0}}
@media(max-width:767px){.counter-shell.counting-active{height:100dvh;max-height:100dvh;min-height:0;display:flex;flex-direction:column;overflow:hidden}.counting-active>.counter-header{position:relative;flex:0 0 auto}.counting-active .counter-topbar{min-height:54px;padding:6px 10px}.counting-active .brand-icon{width:38px;height:38px;flex-basis:38px;border-radius:10px}.counting-active .brand-icon img{width:29px;height:29px}.counting-active .counter-brand strong{font-size:14px}.counting-active .counter-brand small{font-size:10px}.counting-active .count-context{min-height:48px;padding:4px 10px}.counting-active .header-button{min-height:40px;padding:0 11px}.counting-active .count-context dt{font-size:9px}.counting-active .count-context dd{font-size:12px}}
@media(max-width:767px) and (max-height:820px){.counting-active .counter-topbar{min-height:50px;padding-top:4px;padding-bottom:4px}.counting-active .brand-icon{width:35px;height:35px;flex-basis:35px}.counting-active .brand-icon img{width:27px;height:27px}.counting-active .count-context{min-height:44px;padding-top:3px;padding-bottom:3px}.counting-active .header-button{min-height:38px}}
@media(max-width:767px) and (max-height:700px){.counting-active .counter-topbar{min-height:50px;padding-top:4px;padding-bottom:4px}.counting-active .brand-icon{width:34px;height:34px;flex-basis:34px}.counting-active .brand-icon img{width:26px;height:26px}.counting-active .count-context{min-height:44px;padding-top:3px;padding-bottom:3px}.counting-active .header-button{min-height:36px}}
</style>
