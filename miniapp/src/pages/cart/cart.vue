<template>
  <view class="cart-page">
    <view v-if="!auth.isLogin" class="empty">
      <view class="empty-icon">🛒</view>
      <view>登录后查看购物车</view>
      <button class="btn-primary login-btn" @tap="goLogin">去登录</button>
    </view>

    <template v-else-if="items.length">
      <view class="cart-head">
        <text>共 {{ items.length }} 种商品</text>
        <text class="clear" @tap="clearAll">清空</text>
      </view>

      <view v-for="item in items" :key="item.id" class="card cart-item">
        <view class="checkbox" :class="{ checked: item.checked }" @tap="toggle(item)">
          <text v-if="item.checked">✓</text>
        </view>
        <view class="item-pic" @tap="goDetail(item)">
          <image v-if="item.product?.image_url" class="item-img" :src="imageUrl(item.product.image_url)" mode="aspectFill" />
          <text v-else>{{ item.product?.image || '📦' }}</text>
        </view>
        <view class="item-main">
          <view class="item-name" @tap="goDetail(item)">{{ item.product?.name || '商品已失效' }}</view>
          <view v-if="item.variant" class="item-spec">版本：{{ item.variant.spec }}</view>
          <view class="item-bottom">
            <text class="item-price">¥{{ money(priceOf(item)) }}</text>
            <view class="stepper">
              <view class="step" @tap="changeQty(item, -1)">−</view>
              <text class="qty">{{ item.quantity }}</text>
              <view class="step" @tap="changeQty(item, 1)">+</view>
            </view>
          </view>
          <text class="remove" @tap="removeItem(item)">删除</text>
        </view>
      </view>

      <view class="checkout-bar">
        <view class="total">
          <text class="total-label">合计</text>
          <text class="total-price">¥{{ total }}</text>
          <text class="total-sub">已选 {{ checkedCount }} 件</text>
        </view>
        <button class="btn-primary checkout-btn" :disabled="!checkedCount" @tap="goCheckout">去结算</button>
      </view>
    </template>

    <view v-else-if="loaded" class="empty">
      <view class="empty-icon">🛒</view>
      <view>购物车还是空的</view>
      <button class="btn-ghost login-btn" @tap="goHome">去逛逛</button>
    </view>
  </view>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { http } from '../../api/request'
import { imageUrl, money, priceOf } from '../../utils/format'
import { useAuthStore } from '../../stores/auth'
import { refreshCartBadge } from '../../utils/cart'

const auth = useAuthStore()
const items = ref([])
const loaded = ref(false)

const checkedItems = computed(() => items.value.filter((i) => i.checked && i.product))
const checkedCount = computed(() => checkedItems.value.length)
const total = computed(() =>
  checkedItems.value
    .reduce((sum, i) => sum + priceOf(i) * i.quantity, 0)
    .toFixed(2),
)

async function loadCart() {
  if (!auth.isLogin) {
    items.value = []
    loaded.value = true
    return
  }
  try {
    const list = await http.get('/cart')
    const oldChecked = new Map(items.value.map((i) => [i.id, i.checked]))
    items.value = (list || []).map((i) => ({
      ...i,
      checked: oldChecked.get(i.id) ?? true,
    }))
  } catch {
    items.value = []
  } finally {
    loaded.value = true
    refreshCartBadge()
  }
}

function toggle(item) {
  item.checked = !item.checked
}

async function changeQty(item, delta) {
  const next = item.quantity + delta
  const max = item.stock ?? item.variant?.stock ?? item.product?.stock ?? 99
  if (next < 1 || next > max) return
  item.quantity = next
  try {
    await http.put(`/cart/items/${item.id}`, { quantity: next })
    refreshCartBadge()
  } catch {
    loadCart()
  }
}

function removeItem(item) {
  uni.showModal({
    title: '删除商品',
    content: `确认从购物车删除「${item.product?.name || '该商品'}」？`,
    success: async (res) => {
      if (!res.confirm) return
      try {
        await http.del('/cart/items', [item.id])
        items.value = items.value.filter((i) => i.id !== item.id)
        refreshCartBadge()
      } catch {
        loadCart()
      }
    },
  })
}

function clearAll() {
  uni.showModal({
    title: '清空购物车',
    content: '确认清空购物车？',
    success: async (res) => {
      if (!res.confirm) return
      try {
        await http.del('/cart/items', null)
        items.value = []
        refreshCartBadge()
      } catch {
        loadCart()
      }
    },
  })
}

function goDetail(item) {
  if (!item.product) return
  uni.navigateTo({ url: `/pages/product/detail?id=${item.product_id}` })
}

function goCheckout() {
  if (!checkedCount.value) return
  const ids = checkedItems.value.map((i) => i.id).join(',')
  uni.navigateTo({ url: `/pages/checkout/checkout?items=${ids}` })
}

function goLogin() {
  uni.navigateTo({ url: '/pages/login/login' })
}

function goHome() {
  uni.switchTab({ url: '/pages/index/index' })
}

onShow(loadCart)
</script>

<style scoped>
.cart-page {
  min-height: 100vh;
  padding: 24rpx 24rpx 180rpx;
}

.cart-head {
  display: flex;
  justify-content: space-between;
  padding: 4rpx 6rpx 18rpx;
  font-size: 23rpx;
  color: #8a8f99;
}

.clear {
  color: #e1251b;
}

.cart-item {
  display: flex;
  align-items: center;
  gap: 18rpx;
  padding: 22rpx;
  margin-bottom: 18rpx;
}

.checkbox {
  width: 40rpx;
  height: 40rpx;
  border-radius: 50%;
  border: 2rpx solid #d1d5db;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24rpx;
  color: #fff;
  flex-shrink: 0;
}

.checkbox.checked {
  background: #e1251b;
  border-color: #e1251b;
}

.item-pic {
  width: 140rpx;
  height: 140rpx;
  border-radius: 16rpx;
  background: #faf6f5;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 64rpx;
  overflow: hidden;
  flex-shrink: 0;
}

.item-img {
  width: 100%;
  height: 100%;
}

.item-main {
  flex: 1;
  min-width: 0;
}

.item-name {
  font-size: 27rpx;
  line-height: 1.4;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.item-spec {
  display: inline-block;
  margin-top: 8rpx;
  padding: 3rpx 12rpx;
  border-radius: 999rpx;
  background: #f3f4f6;
  color: #6b7280;
  font-size: 20rpx;
}

.item-bottom {
  margin-top: 14rpx;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.item-price {
  font-size: 30rpx;
  color: #e1251b;
  font-weight: 700;
}

.stepper {
  display: flex;
  align-items: center;
  border: 1rpx solid #e5e7eb;
  border-radius: 10rpx;
  overflow: hidden;
}

.step {
  width: 54rpx;
  height: 48rpx;
  line-height: 48rpx;
  text-align: center;
  background: #f8fafc;
  color: #4b5563;
  font-size: 28rpx;
}

.qty {
  width: 60rpx;
  text-align: center;
  font-size: 24rpx;
}

.remove {
  display: block;
  margin-top: 8rpx;
  text-align: right;
  font-size: 21rpx;
  color: #b0b5bd;
}

.checkout-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  height: 120rpx;
  padding: 0 24rpx;
  background: #fff;
  border-top: 1rpx solid #eef0f3;
  display: flex;
  align-items: center;
  gap: 20rpx;
  z-index: 20;
}

.total {
  flex: 1;
  display: flex;
  align-items: baseline;
  gap: 10rpx;
}

.total-label {
  font-size: 23rpx;
  color: #6b7280;
}

.total-price {
  font-size: 40rpx;
  color: #e1251b;
  font-weight: 800;
}

.total-sub {
  font-size: 20rpx;
  color: #9aa0aa;
}

.checkout-btn {
  width: 220rpx;
  height: 78rpx;
  line-height: 78rpx;
  font-size: 27rpx;
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
</style>
