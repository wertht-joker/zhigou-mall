<template>
  <view class="login-page">
    <view class="brand">
      <view class="logo">智购</view>
      <view class="brand-title">智购商城</view>
      <view class="brand-sub">网页版与小程序共用一套账号与订单</view>
    </view>

    <view class="login-card">
      <view class="card-title">登录</view>
      <view class="field">
        <text class="label">账号</text>
        <input v-model="form.username" class="input" placeholder="请输入用户名" />
      </view>
      <view class="field">
        <text class="label">密码</text>
        <input v-model="form.password" class="input" password placeholder="请输入密码" />
      </view>
      <button class="btn-primary submit" :loading="loading" @tap="submit">登录</button>
      <view class="tip">
        演示账号：demo / demo123
        <text class="tip-sub">商家与平台账号请使用网页后台</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { http } from '../../api/request'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

async function submit() {
  if (!form.username.trim() || !form.password) {
    return uni.showToast({ title: '请输入账号和密码', icon: 'none' })
  }
  loading.value = true
  try {
    const data = await http.post('/auth/login', {
      username: form.username.trim(),
      password: form.password,
    })
    if (data.user?.role !== 'customer') {
      auth.clear()
      uni.showModal({
        title: '提示',
        content: '小程序为顾客端，请使用 demo / demo123 登录；商家和平台管理员请使用网页后台。',
        showCancel: false,
      })
      return
    }
    auth.save(data)
    uni.showToast({ title: '登录成功', icon: 'success' })
    setTimeout(() => {
      uni.switchTab({ url: '/pages/index/index' })
    }, 400)
  } catch {
    // 错误提示已由请求层统一处理
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  padding: 80rpx 40rpx;
  background: linear-gradient(160deg, #d81e14 0%, #f04b2f 40%, #f7a072 100%);
}

.brand {
  color: #fff;
  text-align: center;
  margin-bottom: 56rpx;
}

.logo {
  width: 120rpx;
  height: 120rpx;
  margin: 0 auto 24rpx;
  border-radius: 32rpx;
  background: rgba(255, 255, 255, 0.16);
  border: 1rpx solid rgba(255, 255, 255, 0.4);
  font-size: 44rpx;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-title {
  font-size: 48rpx;
  font-weight: 800;
  letter-spacing: 4rpx;
}

.brand-sub {
  margin-top: 12rpx;
  font-size: 24rpx;
  opacity: 0.86;
}

.login-card {
  background: #fff;
  border-radius: 32rpx;
  padding: 40rpx 36rpx;
  box-shadow: 0 24rpx 60rpx rgba(120, 20, 10, 0.18);
}

.card-title {
  font-size: 34rpx;
  font-weight: 700;
  margin-bottom: 28rpx;
}

.field {
  margin-bottom: 24rpx;
}

.label {
  display: block;
  margin-bottom: 10rpx;
  font-size: 24rpx;
  color: #6b7280;
}

.input {
  height: 84rpx;
  padding: 0 24rpx;
  border-radius: 16rpx;
  background: #f5f6f8;
  border: 1rpx solid #eef0f3;
  font-size: 28rpx;
}

.submit {
  margin-top: 12rpx;
  height: 88rpx;
  line-height: 88rpx;
}

.tip {
  margin-top: 28rpx;
  text-align: center;
  font-size: 22rpx;
  color: #9aa0aa;
  line-height: 1.8;
}

.tip-sub {
  display: block;
}
</style>
