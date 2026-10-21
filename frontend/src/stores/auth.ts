import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ApiError } from '../services/api'
import { getCurrentUser, loginAccount, logoutAccount, registerAccount } from '../services/auth'
import type { AuthUser, Credentials } from '../services/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<AuthUser | null>(null)
  const initialized = ref(false)
  const busy = ref(false)

  async function restore() {
    if (initialized.value) return user.value
    try {
      user.value = await getCurrentUser()
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error
      user.value = null
    } finally {
      initialized.value = true
    }
    return user.value
  }

  async function login(credentials: Credentials) {
    busy.value = true
    try {
      user.value = await loginAccount(credentials)
      initialized.value = true
      return user.value
    } finally {
      busy.value = false
    }
  }

  async function register(credentials: Credentials) {
    busy.value = true
    try {
      user.value = await registerAccount(credentials)
      initialized.value = true
      return user.value
    } finally {
      busy.value = false
    }
  }

  async function logout() {
    busy.value = true
    try {
      await logoutAccount()
    } finally {
      user.value = null
      initialized.value = true
      busy.value = false
    }
  }

  return { user, initialized, busy, restore, login, register, logout }
})
