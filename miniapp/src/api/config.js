// 后端地址统一入口：默认 localhost，可用环境变量覆盖，避免真机调试改源码
// - H5 / 微信开发者工具：默认即可访问本机后端
// - 真机调试：在 miniapp/.env.local 写 VITE_API_BASE=http://<电脑局域网IP>:8000
// - 正式发布：必须是已备案的 HTTPS 域名，并在小程序后台配置 request 合法域名
const API_ORIGIN = import.meta.env?.VITE_API_BASE || 'http://localhost:8000'

export const BASE_URL = `${API_ORIGIN}/api/v1`
export const ASSET_BASE = API_ORIGIN
