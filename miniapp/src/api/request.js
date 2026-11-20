import { BASE_URL } from './config'
import { useAuthStore } from '../stores/auth'

let redirecting = false

function toLogin() {
  if (redirecting) return
  redirecting = true
  uni.navigateTo({
    url: '/pages/login/login',
    complete: () => setTimeout(() => { redirecting = false }, 800),
  })
}

function showError(message) {
  uni.showToast({ title: message || '请求失败', icon: 'none', duration: 2200 })
}

// GET 查询参数清洗：uni.request 会把 undefined/null/'' 序列化成字符串
// （如 keyword=undefined），导致后端校验失败返回 400
function cleanQuery(data) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return data
  return Object.fromEntries(
    Object.entries(data).filter(
      ([, v]) => v !== undefined && v !== null && v !== '',
    ),
  )
}

export function request(options) {
  const auth = useAuthStore()
  const method = options.method || 'GET'
  return new Promise((resolve, reject) => {
    uni.request({
      url: BASE_URL + options.url,
      method,
      data: method === 'GET' ? cleanQuery(options.data) : options.data,
      timeout: 20000,
      header: {
        'Content-Type': 'application/json',
        ...(auth.token ? { Authorization: 'Bearer ' + auth.token } : {}),
        ...(options.header || {}),
      },
      success(res) {
        const body = res.data
        if (res.statusCode === 401) {
          auth.clear()
          toLogin()
          reject(new Error('登录已过期，请重新登录'))
          return
        }
        if (body && typeof body === 'object' && 'code' in body) {
          if (body.code === 200) {
            resolve(body.data)
            return
          }
          const msg = body.message || '请求失败'
          showError(msg)
          reject(new Error(msg))
          return
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(body)
          return
        }
        const msg = body?.message || body?.detail || `请求失败（${res.statusCode}）`
        showError(msg)
        reject(new Error(msg))
      },
      fail(err) {
        showError('网络异常，请确认后端已启动')
        reject(new Error(err.errMsg || '网络异常'))
      },
    })
  })
}

export const http = {
  get(url, data) {
    return request({ url, method: 'GET', data })
  },
  post(url, data) {
    return request({ url, method: 'POST', data })
  },
  put(url, data) {
    return request({ url, method: 'PUT', data })
  },
  del(url, data) {
    return request({ url, method: 'DELETE', data })
  },
}
