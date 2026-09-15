const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

const REQUEST_TIMEOUT_MS = 30000
export const STAFF_TOKEN_KEY = 'wms-staff-token'

// Build the API URL. Troubleshoot: VITE_API_BASE_URL and the endpoint path.
export function apiUrl(path) {
  return `${API_BASE_URL}${path}`
}

// Read the staff Bearer token. Troubleshoot: wms-staff-token in sessionStorage.
function staffHeaders() {
  const token = sessionStorage.getItem(STAFF_TOKEN_KEY)
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// Clear the expired staff token and dispatch a session-expired event on HTTP 401.
function handleUnauthorized(response, options) {
  if (response.status === 401 && options.staff) {
    sessionStorage.removeItem(STAFF_TOKEN_KEY)
    window.dispatchEvent(new Event('wms-session-expired'))
  }
}

export class ApiError extends Error {
  // Create an ApiError with a message and HTTP status for UI error handling.
  constructor(message, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

// Send a JSON request and handle timeouts and API errors. Troubleshoot: Network tab, URL, headers, and response body.
async function apiRequest(path, options = {}) {
  let response
  const controller = new AbortController()
  const timeoutMs = options.timeoutMs ?? REQUEST_TIMEOUT_MS
  const { timeoutMs: _timeoutMs, ...requestOptions } = options
  // Abort after the request-specific or default timeout. Troubleshoot: network and server response time.
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs)

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...requestOptions,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(requestOptions.staff ? staffHeaders() : {}),
        ...(requestOptions.body ? { 'Content-Type': 'application/json' } : {}),
        ...requestOptions.headers,
      },
    })
  } catch (error) {
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      throw new ApiError('Wi-Fi connection lost. Please reconnect to the warehouse Wi-Fi network.')
    }
    if (error.name === 'AbortError') {
      throw new ApiError('WMS server is unavailable. Contact the IT Department.')
    }
    throw new ApiError(
      'WMS server is unavailable. Contact the IT Department.',
    )
  } finally {
    window.clearTimeout(timeoutId)
  }

  handleUnauthorized(response, requestOptions)
  if (!response.ok) {
    let detail = ''
    try {
      const body = await response.json()
      const firstFieldError = Object.values(body).flat().find(Boolean)
      detail = body.detail || firstFieldError || ''
    } catch {

      // Keep the generic HTTP error when the response is not JSON.
    }
    // Keep technical HTTP details in DevTools while showing users an actionable server-error notice.
    if (response.status >= 500) {
      console.error('WMS API server error', { path, status: response.status, detail })
      throw new ApiError('The WMS server encountered a problem. Contact the IT Department.', response.status)
    }
    throw new ApiError(detail || `WMS API request failed (${response.status}).`, response.status)
  }

  return response.json()
}

// Read data using GET. Troubleshoot: endpoint path and request options.
export function apiGet(path, options = {}) {
  return apiRequest(path, options)
}

// Send JSON using POST. Troubleshoot: payload and backend validation errors.
export function apiPost(path, data, options = {}) {
  return apiRequest(path, {
    ...options,
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// Update fields using PATCH. Troubleshoot: field names, values, and access token.
export function apiPatch(path, data, options = {}) {
  return apiRequest(path, {
    ...options,
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

// Delete using DELETE and handle an empty response. Troubleshoot: HTTP status, permissions, and timeout.
export async function apiDelete(path, options = {}) {
  let response
  const controller = new AbortController()
  // Abort the request after REQUEST_TIMEOUT_MS. Troubleshoot: network and server response time.
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      method: 'DELETE',
      signal: controller.signal,
      headers: { Accept: 'application/json',
        ...(options.staff ? staffHeaders() : {}), ...options.headers },
    })
  } catch (error) {
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      throw new ApiError('Wi-Fi connection lost. Please reconnect to the warehouse Wi-Fi network.')
    }
    if (error.name === 'AbortError') throw new ApiError('The database request timed out.')
    throw new ApiError('Cannot reach the WMS API. Make sure the Django backend is running.')
  } finally {
    window.clearTimeout(timeoutId)
  }

  handleUnauthorized(response, options)
  if (!response.ok) {
    let detail = ''
    try {
      const body = await response.json()
      detail = body.detail || Object.values(body).flat().find(Boolean) || ''
    } catch {
      // Keep the generic HTTP error when the response is not JSON.
    }
    // DELETE requests use the same user-friendly handling for backend failures.
    if (response.status >= 500) {
      console.error('WMS API server error', { method: 'DELETE', status: response.status, detail })
      throw new ApiError('The WMS server encountered a problem. Contact the IT Department.', response.status)
    }
    throw new ApiError(detail || `WMS API request failed (${response.status}).`, response.status)
  }
}

// Combine all API pages. Troubleshoot: results/next fields when records are missing.
export async function fetchAllPages(path, options = {}) {
  const records = []
  let nextPath = path

  while (nextPath) {
    const page = await apiGet(nextPath, options)
    if (Array.isArray(page)) return [...records, ...page]

    records.push(...(page.results || []))
    if (!page.next) break

    const nextUrl = new URL(page.next, window.location.origin)
    nextPath = `${nextUrl.pathname}${nextUrl.search}`.replace(/^\/api/, '')
  }

  return records
}
