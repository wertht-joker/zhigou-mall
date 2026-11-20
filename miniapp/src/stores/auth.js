import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

const TOKEN_KEY = 'zg_token'
const USER_KEY = 'zg_user'
const TENANT_KEY = 'zg_tenant'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(uni.getStorageSync(TOKEN_KEY) || '')
  const user = ref(uni.getStorageSync(USER_KEY) || null)
  const tenant = ref(uni.getStorageSync(TENANT_KEY) || null)

  const isLogin = computed(() => !!token.value)
  const isCustomer = computed(() => user.value?.role === 'customer')

  function save(data) {
    token.value = data.token || ''
    user.value = data.user || null
    tenant.value = data.tenant || null
    uni.setStorageSync(TOKEN_KEY, token.value)
    uni.setStorageSync(USER_KEY, user.value)
    uni.setStorageSync(TENANT_KEY, tenant.value)
  }

  function clear() {
    token.value = ''
    user.value = null
    tenant.value = null
    uni.removeStorageSync(TOKEN_KEY)
    uni.removeStorageSync(USER_KEY)
    uni.removeStorageSync(TENANT_KEY)
  }

  return { token, user, tenant, isLogin, isCustomer, save, clear }
})
