import axios from 'axios'

const request = axios.create({ baseURL: '/api/v1' })

export const TOKEN_KEY = 'zg_token'
export const USER_KEY = 'zg_user'
export const TENANT_KEY = 'zg_tenant'

// 请求拦截器：统一注入登录态 —— 所有请求自动带 token，业务代码零感知
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

// 响应拦截器：整个前端唯一需要理解后端「统一响应契约」的地方
// 成功 → 解包 {code, message, data}，业务代码直接拿到 data（调用方零样板代码）
// 失败 → 后端返回真实 HTTP 状态码（400/401/403/404/409/429/500）：
//   401 = 身份失效 → 清会话跳登录（全局只处理一次）；
//   其它 → 抛 Error(message) 给业务层 toast 展示。
//   错误处理集中一处，各页面不用重复解析响应结构 —— 与后端全局异常处理器对称。
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

export function isPlatformAdmin() {
  const user = getStoredUser()
  return !!user && user.role === 'platform_admin'
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  localStorage.removeItem(TENANT_KEY)
}

export default request
