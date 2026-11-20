import { ASSET_BASE } from '../api/config'

export function imageUrl(url) {
  if (!url) return ''
  if (/^https?:\/\//.test(url)) return url
  return ASSET_BASE + url
}

export function money(value) {
  return Number(value || 0).toFixed(2)
}

export function formatTime(value) {
  if (!value) return ''
  return String(value).replace('T', ' ').slice(0, 19)
}

export function priceOf(item) {
  return item.unit_price ?? item.variant?.price ?? item.product?.price ?? 0
}

export function stockOf(item) {
  return item.stock ?? item.variant?.stock ?? item.product?.stock ?? 0
}
