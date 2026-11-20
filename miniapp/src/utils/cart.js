import { http } from '../api/request'
import { useAuthStore } from '../stores/auth'

export async function refreshCartBadge() {
  const auth = useAuthStore()
  try {
    if (!auth.isLogin) {
      uni.removeTabBarBadge({ index: 1 })
      return
    }
    const list = await http.get('/cart')
    const count = list.reduce((sum, item) => sum + Number(item.quantity || 0), 0)
    if (count > 0) {
      uni.setTabBarBadge({ index: 1, text: count > 99 ? '99+' : String(count) })
    } else {
      uni.removeTabBarBadge({ index: 1 })
    }
  } catch {
    // 角标失败不影响主流程
  }
}
