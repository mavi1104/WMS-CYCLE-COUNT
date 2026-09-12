import { onBeforeUnmount, ref, watch } from 'vue'
import { heartbeatCounterSession, releaseCounterSession, releaseCounterSessionOnExit } from '../services/counterSession.js'

const LOCK_TIMEOUT_SECONDS = 10
const HEARTBEAT_INTERVAL_MS = 3 * 1000
const IDLE_WARNING_MS = 10 * 60 * 1000
const IDLE_EXIT_MS = 15 * 60 * 1000

// Own lock timers and release state while the layout supplies the current ID and navigation.
export function useCounterLock(cycleCountId, leaveCounting) {
  const releasing = ref(false)
  const releaseError = ref('')
  const connectionLost = ref(false)
  const deviceOffline = ref(typeof navigator !== 'undefined' && navigator.onLine === false)
  const connectionRestored = ref(false)
  const lockExpired = ref(false)
  const lockSecondsRemaining = ref(LOCK_TIMEOUT_SECONDS)
  const idleWarning = ref(false)
  const idleSecondsRemaining = ref((IDLE_EXIT_MS - IDLE_WARNING_MS) / 1000)
  let heartbeatTimer = null
  let countdownTimer = null
  let restoreTimer = null
  let idleWarningTimer = null
  let idleExitTimer = null
  let idleCountdownTimer = null
  let heartbeatPending = false
  let lastConfirmedHeartbeat = Date.now()
  let lastActivityAt = Date.now()
  let disposed = false

  // Cancel inactivity timers without affecting the server heartbeat or lock countdown.
  function clearIdleTimers() {
    if (idleWarningTimer) window.clearTimeout(idleWarningTimer)
    if (idleExitTimer) window.clearTimeout(idleExitTimer)
    if (idleCountdownTimer) window.clearInterval(idleCountdownTimer)
    idleWarningTimer = null
    idleExitTimer = null
    idleCountdownTimer = null
  }

  // Show the grace period before an idle session is released.
  function showIdleWarning() {
    if (!cycleCountId.value || releasing.value || disposed) return
    idleWarning.value = true
    updateIdleCountdown()
    idleCountdownTimer = window.setInterval(updateIdleCountdown, 1000)
  }

  function updateIdleCountdown() {
    const elapsed = Date.now() - lastActivityAt
    idleSecondsRemaining.value = Math.max(0, Math.ceil((IDLE_EXIT_MS - elapsed) / 1000))
  }

  // Start one inactivity window for the active counting route.
  function scheduleIdleTimers() {
    clearIdleTimers()
    if (!cycleCountId.value || releasing.value || disposed) return
    lastActivityAt = Date.now()
    idleWarning.value = false
    idleSecondsRemaining.value = (IDLE_EXIT_MS - IDLE_WARNING_MS) / 1000
    idleWarningTimer = window.setTimeout(showIdleWarning, IDLE_WARNING_MS)
    idleExitTimer = window.setTimeout(showCycleCounts, IDLE_EXIT_MS)
  }

  // Touch, pointer, keyboard, and form activity all keep the counting session active.
  function continueCounting() {
    scheduleIdleTimers()
  }

  // Update the estimated lock time from the last successful server heartbeat.
  function updateCountdown() {
    if (!connectionLost.value) return
    const elapsedSeconds = Math.floor((Date.now() - lastConfirmedHeartbeat) / 1000)
    lockSecondsRemaining.value = Math.max(0, LOCK_TIMEOUT_SECONDS - elapsedSeconds)
    lockExpired.value = lockSecondsRemaining.value === 0
  }

  // Show an offline state immediately while retaining unsaved values on screen.
  function markDisconnected() {
    connectionLost.value = true
    connectionRestored.value = false
    updateCountdown()
  }

  // Skip overlapping heartbeats and ignore responses from a previous route or an unmounted layout.
  async function sendHeartbeat() {
    const id = cycleCountId.value
    if (!id || releasing.value || heartbeatPending || disposed) return
    heartbeatPending = true
    try {
      const sent = await heartbeatCounterSession(id)
      if (sent && !disposed && !releasing.value && cycleCountId.value === id) {
        const recovered = connectionLost.value
        lastConfirmedHeartbeat = Date.now()
        lockSecondsRemaining.value = LOCK_TIMEOUT_SECONDS
        lockExpired.value = false
        connectionLost.value = false
        releaseError.value = ''
        if (recovered) {
          connectionRestored.value = true
          if (restoreTimer) window.clearTimeout(restoreTimer)
          restoreTimer = window.setTimeout(() => { connectionRestored.value = false }, 3000)
        }
      }
    } catch (error) {
      if (!disposed && !releasing.value && cycleCountId.value === id) {
        markDisconnected()
      }
    } finally {
      heartbeatPending = false
    }
  }

  // Keep the existing 30-second interval and release the previous count on return to selection.
  watch(cycleCountId, (id, previousId) => {
    if (heartbeatTimer) window.clearInterval(heartbeatTimer)
    if (countdownTimer) window.clearInterval(countdownTimer)
    clearIdleTimers()
    lastConfirmedHeartbeat = Date.now()
    connectionLost.value = false
    connectionRestored.value = false
    lockExpired.value = false
    lockSecondsRemaining.value = LOCK_TIMEOUT_SECONDS
    heartbeatTimer = id ? window.setInterval(sendHeartbeat, HEARTBEAT_INTERVAL_MS) : null
    countdownTimer = id ? window.setInterval(updateCountdown, 1000) : null
    if (id) scheduleIdleTimers()
    else idleWarning.value = false
    if (previousId && !id) releaseCounterSessionOnExit(previousId)
  }, { immediate: true })

  // Browser events provide immediate hints; a heartbeat still confirms recovery with WMS.
  function handleOffline() {
    deviceOffline.value = true
    if (cycleCountId.value) markDisconnected()
  }
  function handleOnline() {
    deviceOffline.value = false
    sendHeartbeat()
  }
  window.addEventListener?.('offline', handleOffline)
  window.addEventListener?.('online', handleOnline)
  window.addEventListener?.('pointerdown', continueCounting)
  window.addEventListener?.('touchstart', continueCounting, { passive: true })
  window.addEventListener?.('keydown', continueCounting)
  window.addEventListener?.('input', continueCounting)

  // Stop scheduling requests and prevent late responses from updating layout state after unmount.
  onBeforeUnmount(() => {
    disposed = true
    if (heartbeatTimer) window.clearInterval(heartbeatTimer)
    if (countdownTimer) window.clearInterval(countdownTimer)
    if (restoreTimer) window.clearTimeout(restoreTimer)
    clearIdleTimers()
    window.removeEventListener?.('offline', handleOffline)
    window.removeEventListener?.('online', handleOnline)
    window.removeEventListener?.('pointerdown', continueCounting)
    window.removeEventListener?.('touchstart', continueCounting)
    window.removeEventListener?.('keydown', continueCounting)
    window.removeEventListener?.('input', continueCounting)
  })

  // Wait for server-confirmed unlock before navigation; retain the session and show errors on failure.
  async function showCycleCounts() {
    if (releasing.value || disposed) return
    let releaseFailed = false
    releasing.value = true
    releaseError.value = ''
    clearIdleTimers()
    idleWarning.value = false
    try {
      await releaseCounterSession(cycleCountId.value)
      if (!disposed) await leaveCounting()
    } catch (error) {
      if (!disposed) {
        releaseError.value = error.message
        releaseFailed = true
      }
    } finally {
      releasing.value = false
      if (releaseFailed) scheduleIdleTimers()
    }
  }

  return {
    releasing, releaseError, showCycleCounts, connectionLost, deviceOffline,
    connectionRestored, lockExpired, lockSecondsRemaining,
    idleWarning, idleSecondsRemaining, continueCounting,
  }
}
