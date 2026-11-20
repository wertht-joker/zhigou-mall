<template>
  <view class="orders-page">
    <view v-if="!auth.isLogin" class="empty">
      <view class="empty-icon">📋</view>
      <view>登录后查看订单</view>
      <button class="btn-primary login-btn" @tap="goLogin">去登录</button>
    </view>

    <template v-else>
      <scroll-view scroll-x class="tabs" :show-scrollbar="false">
        <view
          v-for="tab in statusTabs"
          :key="tab.value"
          class="tab"
          :class="{ active: activeStatus === tab.value }"
          @tap="switchStatus(tab.value)"
        >
          {{ tab.label }}
        </view>
      </scroll-view>

      <view v-for="order in orders" :key="order.id" class="card order">
        <view class="order-head">
          <text class="order-no">{{ order.order_no }}</text>
          <text class="status" :class="statusClass(order.status)">{{ order.status }}</text>
        </view>
        <view class="order-time">{{ formatTime(order.created_at) }}</view>

        <view class="items">
          <view v-for="item in order.items" :key="item.id" class="item">
            <view class="item-pic">
              <image v-if="item.image_url" class="item-img" :src="imageUrl(item.image_url)" mode="aspectFill" />
              <text v-else>{{ item.image || '📦' }}</text>
            </view>
            <view class="item-info">
              <view class="item-name">{{ item.product_name }}</view>
              <view v-if="item.variant_spec" class="item-spec">版本：{{ item.variant_spec }}</view>
              <view class="item-price">¥{{ money(item.price) }} × {{ item.quantity }}</view>
            </view>
          </view>
        </view>

        <view v-if="order.logistics" class="logistics" @tap="toggleLogistics(order.id)">
          <view class="logi-top">
            <text class="logi-company">🚚 {{ order.logistics_company || '物流' }}</text>
            <text v-if="order.logistics_status" class="logi-status">{{ order.logistics_status }}</text>
          </view>
          <view class="logi-no">运单号：{{ order.tracking_no || order.logistics }}</view>
          <view v-if="expanded[order.id] && order.logistics_events?.length" class="timeline">
            <view v-for="(event, index) in order.logistics_events" :key="index" class="event">
              <view class="dot" :class="{ latest: index === 0 }"></view>
              <view class="event-main">
                <view class="event-status">{{ event.status }}</view>
                <view class="event-desc">{{ event.description }}</view>
                <view class="event-time">{{ formatTime(event.occurred_at) }} {{ event.location }}</view>
              </view>
            </view>
          </view>
          <text class="logi-toggle">{{ expanded[order.id] ? '收起轨迹' : '展开物流轨迹' }} ›</text>
        </view>

        <view class="order-foot">
          <view class="total">
            <text v-if="order.discount_amount > 0" class="cut">券已抵扣 ¥{{ money(order.discount_amount) }} · </text>
            <text>实付</text>
            <text class="total-price">¥{{ money(order.total_amount) }}</text>
          </view>
          <view class="actions">
            <button v-if="order.status === '待付款'" class="act ghost" @tap="cancel(order)">取消</button>
            <button v-if="order.status === '待付款'" class="act primary" @tap="pay(order)">去支付</button>
            <button v-if="order.status === '已发货'" class="act primary" @tap="confirmReceipt(order)">确认收货</button>
          </view>
        </view>
      </view>

      <view v-if="!loading && !orders.length" class="empty">暂无相关订单</view>

      <view v-if="orders.length && orders.length < total" class="load-more" @tap="loadMore">
        {{ loadingMore ? '加载中…' : '加载更多' }}
      </view>
      <view v-else-if="orders.length" class="load-end">— 没有更多了 —</view>
    </template>
  </view>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { onShow, onPullDownRefresh, onReachBottom } from '@dcloudio/uni-app'
import { http } from '../../api/request'
import { imageUrl, money, formatTime } from '../../utils/format'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const orders = ref([])
const loading = ref(false)
const loadingMore = ref(false)
const activeStatus = ref('')
const expanded = reactive({})
const page = ref(1)
const total = ref(0)
const PAGE_SIZE = 10

const statusTabs = [
  { label: '全部', value: '' },
  { label: '待付款', value: '待付款' },
  { label: '待发货', value: '待发货' },
  { label: '已发货', value: '已发货' },
  { label: '已完成', value: '已完成' },
]

function statusClass(status) {
  return {
    待付款: 'warn',
    待发货: 'primary',
    已发货: 'success',
    已完成: 'info',
    已取消: 'danger',
  }[status] || 'info'
}

async function loadOrders() {
  if (!auth.isLogin) {
    orders.value = []
    total.value = 0
    loading.value = false
    return
  }
  loading.value = true
  page.value = 1
  try {
    const data = await http.get('/orders', {
      status: activeStatus.value || undefined,
      page: 1,
      page_size: PAGE_SIZE,
    })
    orders.value = data.items || []
    total.value = data.total || 0
  } catch {
    orders.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (loading.value || loadingMore.value || orders.value.length >= total.value) return
  loadingMore.value = true
  try {
    const data = await http.get('/orders', {
      status: activeStatus.value || undefined,
      page: page.value + 1,
      page_size: PAGE_SIZE,
    })
    page.value += 1
    orders.value = orders.value.concat(data.items || [])
    total.value = data.total || total.value
  } catch {
    // 请求层已提示
  } finally {
    loadingMore.value = false
  }
}

function switchStatus(value) {
  activeStatus.value = value
  loadOrders()
}

function toggleLogistics(id) {
  expanded[id] = !expanded[id]
}

function goLogin() {
  uni.navigateTo({ url: '/pages/login/login' })
}

function pay(order) {
  const methods = [
    { label: '支付宝', value: 'alipay' },
    { label: '微信支付', value: 'wechat' },
    { label: '银联', value: 'unionpay' },
  ]
  uni.showActionSheet({
    itemList: methods.map((m) => m.label),
    success: async (sheet) => {
      const method = methods[sheet.tapIndex]
      try {
        uni.showLoading({ title: '创建支付单' })
        const payment = await http.post(`/orders/${order.id}/payments`, {
          method: method.value,
        })
        uni.hideLoading()
        uni.showModal({
          title: '模拟支付',
          content: `${payment.method_label} ¥${money(payment.amount)}\n演示环境：确认后模拟支付成功`,
          confirmText: '确认支付',
          success: async (modal) => {
            if (!modal.confirm) return
            try {
              uni.showLoading({ title: '支付中' })
              await http.post(`/payments/${payment.payment_no}/confirm`)
              uni.showToast({ title: '支付成功', icon: 'success' })
              loadOrders()
            } catch {
              // 请求层已提示
            } finally {
              uni.hideLoading()
            }
          },
        })
      } catch {
        uni.hideLoading()
      }
    },
  })
}

function cancel(order) {
  uni.showModal({
    title: '取消订单',
    content: '确认取消该订单？',
    success: async (res) => {
      if (!res.confirm) return
      try {
        await http.post(`/orders/${order.id}/cancel`)
        uni.showToast({ title: '订单已取消', icon: 'success' })
        loadOrders()
      } catch {
        // 请求层已提示
      }
    },
  })
}

function confirmReceipt(order) {
  uni.showModal({
    title: '确认收货',
    content: '请确认已收到商品，确认后订单完成。',
    success: async (res) => {
      if (!res.confirm) return
      try {
        await http.post(`/orders/${order.id}/confirm`)
        uni.showToast({ title: '已确认收货', icon: 'success' })
        loadOrders()
      } catch {
        // 请求层已提示
      }
    },
  })
}

onShow(loadOrders)

onReachBottom(() => {
  loadMore()
})

onPullDownRefresh(async () => {
  await loadOrders()
  uni.stopPullDownRefresh()
})
</script>

<style scoped>
.orders-page {
  min-height: 100vh;
  padding: 20rpx 24rpx 40rpx;
}

.tabs {
  white-space: nowrap;
  margin-bottom: 18rpx;
}

.tab {
  display: inline-block;
  margin-right: 14rpx;
  padding: 12rpx 28rpx;
  border-radius: 999rpx;
  background: #fff;
  color: #6b7280;
  font-size: 24rpx;
  border: 1rpx solid #eef0f3;
}

.tab.active {
  background: #fff1f0;
  color: #e1251b;
  border-color: #ffc9c2;
  font-weight: 600;
}

.order {
  margin-bottom: 20rpx;
  padding: 24rpx;
}

.order-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.order-no {
  font-size: 23rpx;
  color: #6b7280;
}

.status {
  padding: 4rpx 14rpx;
  border-radius: 999rpx;
  font-size: 21rpx;
}

.status.warn {
  background: #fff7e6;
  color: #d97706;
}

.status.primary {
  background: #eff6ff;
  color: #2563eb;
}

.status.success {
  background: #ecfdf5;
  color: #059669;
}

.status.info {
  background: #f3f4f6;
  color: #6b7280;
}

.status.danger {
  background: #fef2f2;
  color: #dc2626;
}

.order-time {
  margin-top: 6rpx;
  font-size: 20rpx;
  color: #b0b5bd;
}

.items {
  margin-top: 16rpx;
  padding-top: 8rpx;
  border-top: 1rpx solid #f4f5f7;
}

.item {
  display: flex;
  gap: 16rpx;
  padding: 14rpx 0;
}

.item-pic {
  width: 104rpx;
  height: 104rpx;
  border-radius: 14rpx;
  background: #faf6f5;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 50rpx;
  overflow: hidden;
  flex-shrink: 0;
}

.item-img {
  width: 100%;
  height: 100%;
}

.item-info {
  flex: 1;
  min-width: 0;
}

.item-name {
  font-size: 26rpx;
  line-height: 1.4;
}

.item-spec {
  display: inline-block;
  margin-top: 6rpx;
  padding: 2rpx 10rpx;
  border-radius: 999rpx;
  background: #f3f4f6;
  color: #6b7280;
  font-size: 19rpx;
}

.item-price {
  margin-top: 8rpx;
  font-size: 22rpx;
  color: #9aa0aa;
}

.logistics {
  margin-top: 6rpx;
  padding: 18rpx 20rpx;
  border-radius: 16rpx;
  background: #f8fafc;
  border: 1rpx solid #eef2f7;
}

.logi-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.logi-company {
  font-size: 24rpx;
  font-weight: 600;
  color: #334155;
}

.logi-status {
  padding: 2rpx 12rpx;
  border-radius: 999rpx;
  background: #ecfdf5;
  color: #059669;
  font-size: 19rpx;
}

.logi-no {
  margin-top: 8rpx;
  font-size: 21rpx;
  color: #8a8f99;
  word-break: break-all;
}

.logi-toggle {
  display: block;
  margin-top: 10rpx;
  text-align: right;
  font-size: 21rpx;
  color: #e1251b;
}

.timeline {
  margin-top: 14rpx;
  padding-top: 10rpx;
  border-top: 1rpx dashed #e2e8f0;
}

.event {
  position: relative;
  padding: 0 0 18rpx 28rpx;
}

.event:last-child {
  padding-bottom: 0;
}

.dot {
  position: absolute;
  left: 0;
  top: 8rpx;
  width: 12rpx;
  height: 12rpx;
  border-radius: 50%;
  background: #cbd5e1;
}

.dot.latest {
  background: #e1251b;
  box-shadow: 0 0 0 6rpx rgba(225, 37, 27, 0.12);
}

.event-status {
  font-size: 22rpx;
  font-weight: 600;
  color: #334155;
}

.event-desc {
  margin-top: 4rpx;
  font-size: 21rpx;
  color: #6b7280;
  line-height: 1.5;
}

.event-time {
  margin-top: 4rpx;
  font-size: 19rpx;
  color: #a8afb9;
}

.order-foot {
  margin-top: 16rpx;
  padding-top: 16rpx;
  border-top: 1rpx dashed #eef0f3;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.total {
  font-size: 23rpx;
  color: #6b7280;
}

.cut {
  color: #f59e0b;
}

.total-price {
  margin-left: 6rpx;
  font-size: 34rpx;
  color: #e1251b;
  font-weight: 800;
}

.actions {
  display: flex;
  gap: 12rpx;
}

.act {
  margin: 0;
  padding: 0 24rpx;
  height: 62rpx;
  line-height: 62rpx;
  border-radius: 999rpx;
  font-size: 23rpx;
}

.act::after {
  border: none;
}

.act.ghost {
  background: #fff;
  color: #6b7280;
  border: 1rpx solid #e5e7eb;
}

.act.primary {
  background: linear-gradient(120deg, #e1251b, #ff6a3d);
  color: #fff;
  font-weight: 600;
}

.empty-icon {
  font-size: 90rpx;
  margin-bottom: 16rpx;
}

.login-btn {
  margin-top: 28rpx;
  width: 260rpx;
  height: 76rpx;
  line-height: 76rpx;
  font-size: 26rpx;
}

.load-more {
  margin: 24rpx 0;
  text-align: center;
  font-size: 25rpx;
  color: #e1251b;
}

.load-end {
  margin: 24rpx 0;
  text-align: center;
  font-size: 22rpx;
  color: #b0b5bd;
}
</style>
