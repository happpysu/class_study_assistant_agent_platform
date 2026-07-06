import { defineStore } from 'pinia'
import { getMe, login as apiLogin } from '../api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    token: localStorage.getItem('token') || '',
  }),
  getters: {
    isLoggedIn: (state) => Boolean(state.token),
  },
  actions: {
    async login(username, password) {
      const { data } = await apiLogin({ username, password })
      this.token = data.access_token
      this.user = data.user
      localStorage.setItem('token', data.access_token)
    },
    async fetchMe() {
      if (!this.token) return
      try {
        const { data } = await getMe()
        this.user = data
      } catch {
        this.logout()
      }
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('token')
    },
  },
})
