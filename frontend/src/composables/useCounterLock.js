import { onBeforeUnmount, ref, watch } from 'vue'
import { heartbeatCounterSession, releaseCounterSession, releaseCounterSessionOnExit } from '../services/counterSession.js'

const LOCK_TIMEOUT_SECONDS = 120

// Own lock timers and release state while the layout supplies the current ID and navigation.
export function useCounterLock(cycleCountId, leaveCounting) {
  const releasing = ref(false)
  const releaseError = ref('')
  const connectionLost = ref(false)
  const deviceOffline = ref(typeof navigator !== 'undefined' && navigator.onLine === false)
  const connectionRestored = ref(false)
  const lockExpired = ref(false)
  const lockSecondsRemaining = ref(LOCK_TIMEOUT_SECONDS)
  let heartbeatTimer = null
  let countdownTimer = null 
  let restoreTimer = null
  let heartbeatPending = false
  let lastConfirmedHeartbeat = Date.now()
  let disposed = false

  // Update the estimated lock time from the last successful server heartbeat.
  function updateCountdown() {
    if (!connectionLost.value) return
    const elapsedSeconds = Math.floor((Date.now() - lastConfirmedHeartbeat) / 1000)
    lockSecondsRemaining.value = Math.max(0, LOCK_TIMEOUT_SECONDS - elapsedSeconds)
    lockExpired.value = lockSecondsRemaining.value === 0
  }

  // Show an offline state immediately while retaining unsaved values on screen.
  function markDisconnected() {
    // navigator.onLine only classifies a failed API request; it never proves that WMS is reachable.
    if (typeof navigator !== 'undefined') deviceOffline.value = navigator.onLine === false
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
        deviceOffline.value = false
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
    lastConfirmedHeartbeat = Date.now()
    connectionLost.value = false
    connectionRestored.value = false
    lockExpired.value = false
    lockSecondsRemaining.value = LOCK_TIMEOUT_SECONDS
    heartbeatTimer = id ? window.setInterval(sendHeartbeat, 10000) : null
    countdownTimer = id ? window.setInterval(updateCountdown, 1000) : null
    if (previousId && !id) releaseCounterSessionOnExit(previousId)
  }, { immediate: true })

  // Browser events provide immediate hints; a heartbeat still confirms recovery with WMS.
  function handleOffline() {
    deviceOffline.value = true
    if (cycleCountId.value) markDisconnected()
  }
  function handleOnline() {
    deviceOffline.value = false
    return sendHeartbeat()
  }
  window.addEventListener?.('offline', handleOffline)
  window.addEventListener?.('online', handleOnline)

  // Stop scheduling requests and prevent late responses from updating layout state after unmount.
  onBeforeUnmount(() => {
    disposed = true
    if (heartbeatTimer) window.clearInterval(heartbeatTimer)
    if (countdownTimer) window.clearInterval(countdownTimer)
    if (restoreTimer) window.clearTimeout(restoreTimer)
    window.removeEventListener?.('offline', handleOffline)
    window.removeEventListener?.('online', handleOnline)
  })

  // Wait for server-confirmed unlock before navigation; retain the session and show errors on failure.
  async function showCycleCounts() {
    if (releasing.value || disposed) return
    releasing.value = true
    releaseError.value = ''
    try {
      await releaseCounterSession(cycleCountId.value)
      if (!disposed) await leaveCounting()
    } catch (error) {
      if (!disposed) releaseError.value = error.message
    } finally {
      releasing.value = false
    }
  }

  return {
    releasing, releaseError, showCycleCounts, connectionLost, deviceOffline,
    connectionRestored, lockExpired, lockSecondsRemaining,
  }
}
