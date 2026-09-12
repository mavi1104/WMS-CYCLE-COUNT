import { apiDelete, apiPatch, apiPost, fetchAllPages } from './api'

// Fetch accounts for the administrator. Troubleshoot: /counter-accounts/ and the staff session.
export function getCounterAccounts() {
  return fetchAllPages('/counter-accounts/', { staff: true })
}

// Create an account in the backend. Troubleshoot: role, credentials, and duplicate-account responses.
export function createCounterAccount(account) {
  return apiPost('/counter-accounts/', account, { staff: true })
}

// Update an account by ID. Troubleshoot: changes payload and backend validation.
export function updateCounterAccount(id, changes) {
  return apiPatch(`/counter-accounts/${encodeURIComponent(id)}/`, changes, { staff: true })
}

// Delete an account by ID. Troubleshoot: HTTP 409 for the current account or an account with count history.
export function deleteCounterAccount(id) {
  return apiDelete(`/counter-accounts/${encodeURIComponent(id)}/`, { staff: true })
}

// Fetch activity logs for an optional inclusive date range. Troubleshoot: date format and administrator permissions.
export function getCounterCountLogs({ dateFrom = '', dateTo = '' } = {}) {
  const query = new URLSearchParams()
  if (dateFrom) query.set('date_from', dateFrom)
  if (dateTo) query.set('date_to', dateTo)
  const suffix = query.toString() ? `?${query}` : ''
  return fetchAllPages(`/counter-count-logs/${suffix}`, { staff: true })
}
