import { defineStore } from 'pinia'
import { apiGet, apiPost, STAFF_TOKEN_KEY } from '../services/api'

// Old demo roles must never become authenticated sessions.
localStorage.removeItem('wms-user')

export const useAuthStore = defineStore('auth', {
  // Initialize the store state. Troubleshoot: initial user data and browser storage where used.
  state: () => ({ user: null }),
  getters: {
    // Check whether the store contains a user. Troubleshoot: login/restore when navigation is incorrect.
    isLoggedIn: (state) => !!state.user,
    // Check the role for the administrator UI. Troubleshoot: user.role and route permissions.
    isAdmin: (state) => state.user?.role === 'admin',
  },
  actions: {
    // Remove the user and staff token from the browser. Troubleshoot: local session cleanup starts here.
    clearSession() {
      this.user = null
      sessionStorage.removeItem(STAFF_TOKEN_KEY)
    },
    // Validate the saved staff token through /auth/me/. Troubleshoot: HTTP 401 responses and sessionStorage.
    async restore() {
      if (!sessionStorage.getItem(STAFF_TOKEN_KEY)) {
        this.user = null
        return
      }
      try {
        this.user = await apiGet('/auth/me/', { staff: true })
      } catch (error) {
        this.user = null
        if (error.status === 401) this.clearSession()
        throw error
      }
    },
    // Log in through /auth/login/ and save the token and user. Troubleshoot: credentials, response, and sessionStorage.
    async login({ username, password }) {
      this.clearSession()
      const session = await apiPost('/auth/login/', { username, password })
      sessionStorage.setItem(STAFF_TOKEN_KEY, session.token)
      this.user = session.user
    },
    // Log out and clear the session. Troubleshoot: auth.logout or /auth/logout/ if logout fails.
    async logout() {
      await apiPost('/auth/logout/', {}, { staff: true })
      this.clearSession()
    },
  },
})
