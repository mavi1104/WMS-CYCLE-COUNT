import { keepCycleCountLock, releaseCycleCountLock, releaseCycleCountLockOnExit } from './cycleCounts.js'

// Keep the existing per-count storage key so open browser sessions remain compatible.
function sessionKey(cycleCountId) {
  return `wms-counter-session-${cycleCountId}`
}

// Read the counter session; missing, malformed, or unavailable storage means no session.
export function readCounterSession(cycleCountId) {
  try {
    return JSON.parse(sessionStorage.getItem(sessionKey(cycleCountId)) || 'null')
  } catch {
    return null
  }
}

// Persist the verified API session without changing its token or profile fields.
export function saveCounterSession(cycleCountId, session) {
  sessionStorage.setItem(sessionKey(cycleCountId), JSON.stringify(session))
}

// Remove access for this count only; staff and other count sessions are unaffected.
export function clearCounterSession(cycleCountId) {
  sessionStorage.removeItem(sessionKey(cycleCountId))
}

// Refresh the lock using its stored token; report false when there is no active session.
export async function heartbeatCounterSession(cycleCountId) {
  const session = readCounterSession(cycleCountId)
  if (!session?.token) return false
  await keepCycleCountLock(cycleCountId, session.token)
  return true
}

// Clear the token only after a successful unlock, preserving access when the request fails.
export async function releaseCounterSession(cycleCountId) {
  const session = readCounterSession(cycleCountId)
  if (!session?.token) return
  await releaseCycleCountLock(cycleCountId, session.token)
  if (readCounterSession(cycleCountId)?.token === session.token) {
    clearCounterSession(cycleCountId)
  }
}

// Preserve the existing beacon fallback; true means queued, not server-confirmed delivery.
export function releaseCounterSessionOnExit(cycleCountId) {
  if (!cycleCountId) return false
  const session = readCounterSession(cycleCountId)
  if (!session?.token || !releaseCycleCountLockOnExit(cycleCountId, session.token)) return false
  clearCounterSession(cycleCountId)
  return true
}
