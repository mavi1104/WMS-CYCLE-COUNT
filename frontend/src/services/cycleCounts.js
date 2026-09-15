import { apiGet, apiPatch, apiPost, apiUrl, fetchAllPages } from './api.js'

let countingHandoff = null

// Hold one freshly authorized count request during route navigation to avoid a duplicate API call.
export function saveCountingHandoff(cycleCountId, token, header, details) {
  countingHandoff = {
    cycleCountId: String(cycleCountId),
    token,
    header,
    details,
  }
}

// Consume the handoff once; stale or mismatched sessions must fetch from the API normally.
export function consumeCountingHandoff(cycleCountId, token) {
  const handoff = countingHandoff
  countingHandoff = null
  if (
    !handoff
    || handoff.cycleCountId !== String(cycleCountId)
    || handoff.token !== token
  ) return null
  return handoff
}

// Fetch cycle counts with type D and status 0. Troubleshoot: query filters when expected counts are missing.
export function getCycleCounts(scope = 'counter-selection') {
  return fetchAllPages('/cycle-counts/?cc_type=D&status_id=0', { cache: 'no-store', staff: scope === 'admin-cycle-counts' })
}

// Fetch the available active counters. Troubleshoot: /counter-access/counters/ response.
export function getCounterChoices() {
  return apiGet('/counter-access/counters/')
}

// Submit the cycle count, counter, and access code to create a session. Troubleshoot: HTTP 403 code errors or 409 lock conflicts.
export function verifyCounterAccess(cycleCountId, counterId, accessCode) {
  return apiPost('/counter-access/verify/', {
    cycleCountId,
    counterId,
    accessCode,
  })
}

// Fetch products using X-Counter-Session. Troubleshoot: cycle count ID and expired or invalid tokens.
export function getCycleCountDetails(id, token) {
  return apiGet(`/cycle-counts/${encodeURIComponent(id)}/details/`, {
    headers: { 'X-Counter-Session': token },
  })
}

// Send actualCs and actualPc to the backend. Troubleshoot: detail ID, whole-number counts, and counter token.
export function updateActualCount(detailId, actualCs, actualPc, token, cycleCountId, metadata = {}) {
  return apiPatch(
    `/cycle-count-details/${encodeURIComponent(detailId)}/actual-count/`,
    {
      actualCs,
      actualPc,
      productionDate: metadata.productionDate || null,
      expiryDate: metadata.expiryDate || null,
      lotNo: metadata.lotNo || null,
    },
    {
      headers: { 'X-Counter-Session': token },
    },
  )
}

// Request a lock release from the backend. Troubleshoot: /unlock/ response and counter session.
export function releaseCycleCountLock(cycleCountId, token) {
  return apiPost(
    `/cycle-counts/${encodeURIComponent(cycleCountId)}/unlock/`,
    {},
    {
      headers: { 'X-Counter-Session': token },
    },
  )
}

// Send a heartbeat to keep the lock active. Troubleshoot: /heartbeat/ request and token.
export function keepCycleCountLock(cycleCountId, token) {
  return apiPost(
    `/cycle-counts/${encodeURIComponent(cycleCountId)}/heartbeat/`,
    {},
    { timeoutMs: 5000, headers: { 'X-Counter-Session': token } },
  )
}

// Queue an unlock beacon. Troubleshoot: sendBeacon support and return value; true only confirms that the request was queued.
export function releaseCycleCountLockOnExit(cycleCountId, token) {
  if (!cycleCountId || !token || !navigator.sendBeacon) return false
  const body = new Blob(
    [JSON.stringify({ counterSession: token })],
    { type: 'application/json' },
  )
  return navigator.sendBeacon(
    apiUrl(`/cycle-counts/${encodeURIComponent(cycleCountId)}/unlock/`),
    body,
  )
}
