<template>
  <view class="profile">
    <view class="user-card">
      <view class="avatar">{{ avatarText }}</view>
      <view class="user-info">
        <view class="username">{{ auth.user?.username || '未登录' }}</view>
        <view class="user-sub">{{ auth.isLogin ? '已登录 · 顾客账号' : '登录后同步购物车与订单' }}</view>
      </view>
      <button v-if="!auth.isLogin" class="mini-btn" @tap="goLogin">登录</button>
    </view>

    <view class="order-entry card" @tap="goOrders">
      <view>
        <view class="entry-title">我的订单</view>
        <view class="entry-sub">查看物流、确认收货、继续支付</view>
      </view>
      <text class="arrow">›</text>
    </view>

    <view class="menu card">
      <view class="menu-item" @tap="goCart">
        <text class="menu-icon">🛒</text>
        <text class="menu-text">购物车</text>
        <text class="arrow">›</text>
      </view>
      <view class="menu-item" @tap="goChat">
        <text class="menu-icon">🤖</text>
        <text class="menu-text">AI 客服</text>
        <text class="menu-sub">售后政策 · 查订单 · 推荐</text>
        <text class="arrow">›</text>
      </view>
      <view class="menu-item" @tap="goWeb">
        <text class="menu-icon">💻</text>
        <text class="menu-text">网页版</text>
        <text class="menu-sub">商家 / 平台后台</text>
        <text class="arrow">›</text>
      </view>
    </view>

    <button v-if="auth.isLogin" class="logout" @tap="logout">退出登录</button>
    <view class="version">智购商城小程序 v1.0.0</view>
  </view>
</template>

<script setup>
import { computed } from 'vue'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const avatarText = computed(() => (auth.user?.username || '游').slice(0, 1).toUpperCase())

function goLogin() {
  uni.navigateTo({ url: '/pages/login/login' })
}

function goOrders() {
  uni.switchTab({ url: '/pages/orders/orders' })
}

function goCart() {
  uni.switchTab({ url: '/pages/cart/cart' })
}

function goChat() {
  uni.navigateTo({ url: '/pages/chat/chat' })
}

function goWeb() {
  uni.showModal({
    title: '网页版入口',
    content: '商家后台与平台后台请使用浏览器访问 http://localhost:5173',
    showCancel: false,
  })
}

function logout() {
  uni.showModal({
    title: '退出登录',
    content: '确认退出当前账号？',
    success(res) {
      if (!res.confirm) return
      auth.clear()
      uni.removeTabBarBadge({ index: 1 })
      uni.showToast({ title: '已退出', icon: 'none' })
    },
  })
}
</script>

<style scoped>
.profile {
  min-height: 100vh;
  padding: 24rpx;
}

.user-card {
  padding: 34rpx 30rpx;
  border-radius: 28rpx;
  background: linear-gradient(135deg, #d81e14, #f05432);
  color: #fff;
  display: flex;
  align-items: center;
  gap: 22rpx;
  box-shadow: 0 14rpx 34rpx rgba(225, 37, 27, 0.22);
}

.avatar {
  width: 96rpx;
  height: 96rpx;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  border: 1rpx solid rgba(255, 255, 255, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 38rpx;
  font-weight: 800;
}

.user-info {
  flex: 1;
}

.username {
  font-size: 34rpx;
  font-weight: 700;
}

.user-sub {
  margin-top: 8rpx;
  font-size: 22rpx;
  opacity: 0.86;
}

.mini-btn {
  margin: 0;
  padding: 0 26rpx;
  height: 60rpx;
  line-height: 60rpx;
  border-radius: 999rpx;
  background: #fff;
  color: #e1251b;
  font-size: 24rpx;
  font-weight: 600;
}

.mini-btn::after {
  border: none;
}

.order-entry {
  margin-top: 24rpx;
  padding: 28rpx 30rpx;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.entry-title {
  font-size: 30rpx;
  font-weight: 700;
}

.entry-sub {
  margin-top: 8rpx;
  font-size: 22rpx;
  color: #9aa0aa;
}

.arrow {
  color: #c4c9d1;
  font-size: 36rpx;
}

.menu {
  margin-top: 24rpx;
  padding: 0 30rpx;
}

.menu-item {
  display: flex;
  align-items: center;
  min-height: 96rpx;
  border-bottom: 1rpx solid #f4f5f7;
}

.menu-item:last-child {
  border-bottom: none;
}

.menu-icon {
  width: 56rpx;
  font-size: 34rpx;
}

.menu-text {
  font-size: 28rpx;
  color: #1f2937;
}

.menu-sub {
  flex: 1;
  text-align: right;
  margin-right: 12rpx;
  font-size: 21rpx;
  color: #9aa0aa;
}

.menu-item .arrow {
  margin-left: auto;
}

.logout {
  margin-top: 40rpx;
  background: #fff;
  color: #e1251b;
  border-radius: 20rpx;
  font-size: 28rpx;
}

.logout::after {
  border: 1rpx solid #ffd8d3;
  border-radius: 20rpx;
}

.version {
  margin-top: 32rpx;
  text-align: center;
  font-size: 21rpx;
  color: #b0b5bd;
}
</style>
