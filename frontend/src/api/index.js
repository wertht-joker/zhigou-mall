import axios from 'axios'

const request = axios.create({ baseURL: '/api/v1' })

export const TOKEN_KEY = 'zg_token'
export const USER_KEY = 'zg_user'
export const TENANT_KEY = 'zg_tenant'

// 请求拦截器：自动带 token
request.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = 'Bearer ' + token
  return config
})

function toLogin() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  localStorage.removeItem(TENANT_KEY)
  if (window.location.pathname !== '/login') window.location.href = '/login'
}

// 响应拦截器：
// 成功 → 解包统一结构 {code, message, data} 的 data
// 失败 → 后端已返回真实 HTTP 状态码（400/401/403/404/409/500），
//        401 跳登录，其它取响应体 message 抛出
request.interceptors.response.use(
  (res) => {
    const body = res.data
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code === 200) return body.data
      return Promise.reject(new Error(body.message || '请求失败'))
    }
    return body
  },
  (err) => {
    const status = err.response?.status
    if (status === 401) toLogin()
    const msg = err.response?.data?.message || err.response?.data?.detail || err.message || '请求失败'
    return Promise.reject(new Error(msg))
  },
)

// ===== 登录态助手 =====

export function saveSession(data) {
  localStorage.setItem(TOKEN_KEY, data.token)
  localStorage.setItem(USER_KEY, JSON.stringify(data.user))
  localStorage.setItem(TENANT_KEY, JSON.stringify(data.tenant))
}

export function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
  } catch {
    return null
  }
}

export function getStoredTenant() {
  try {
    return JSON.parse(localStorage.getItem(TENANT_KEY) || 'null')
  } catch {
    return null
  }
}

export function isMerchant() {
  const user = getStoredUser()
  return !!user && (user.role === 'admin' || user.role === 'editor')
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  localStorage.removeItem(TENANT_KEY)
}

export default request
