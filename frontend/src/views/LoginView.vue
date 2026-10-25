<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-logo"><span>🛍️</span> 智购商城</div>
      <el-tabs v-model="tab">
        <el-tab-pane label="登录" name="login" />
        <el-tab-pane label="注册" name="register" />
      </el-tabs>

      <!-- 注册：选择身份 -->
      <el-radio-group v-if="tab === 'register'" v-model="registerType" class="role-switch">
        <el-radio-button value="customer">我要买东西（顾客）</el-radio-button>
        <el-radio-button value="merchant">我要开店（商家入驻）</el-radio-button>
      </el-radio-group>

      <el-form>
        <el-form-item v-if="tab === 'register' && registerType === 'merchant'">
          <el-input v-model="form.merchant_name" placeholder="店铺名称，如：星辰数码旗舰店" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" placeholder="密码" show-password @keyup.enter="submit" />
        </el-form-item>
        <el-button type="primary" style="width:100%" :loading="loading" @click="submit">
          {{ tab === 'login' ? '登录' : (registerType === 'merchant' ? '入驻并登录' : '注册并登录') }}
        </el-button>
      </el-form>

      <div class="login-tip">
        演示账号：顾客 demo / demo123 · 平台管理员 admin / admin123 · 商家 shop / shop123
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import request, { saveSession } from '../api'

const route = useRoute()
const router = useRouter()
const tab = ref(route.query.tab === 'register' ? 'register' : 'login')
const registerType = ref('customer')
const loading = ref(false)
const form = ref({ username: '', password: '', merchant_name: '' })

async function submit() {
  if (!form.value.username || !form.value.password) {
    return ElMessage.warning('请输入用户名和密码')
  }
  loading.value = true
  try {
    if (tab.value === 'login') {
      const data = await request.post('/auth/login', {
        username: form.value.username,
        password: form.value.password,
      })
      saveSession(data)
      ElMessage.success(`欢迎回来，${data.user.username}`)
      router.push(route.query.redirect || '/')
    } else {
      const payload = { username: form.value.username, password: form.value.password }
      if (registerType.value === 'merchant') {
        payload.register_type = 'merchant'
        payload.merchant_name = form.value.merchant_name
        if (!payload.merchant_name?.trim()) {
          return ElMessage.warning('请填写店铺名称')
        }
      }
      // 注册成功直接返回 token，免二次登录
      const data = await request.post('/auth/register', payload)
      saveSession(data)
      ElMessage.success(
        registerType.value === 'merchant'
          ? `入驻成功！店铺编码 ${data.tenant.code}`
          : '注册成功'
      )
      router.push('/')
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex; justify-content: center; align-items: center; height: 100vh;
  background: linear-gradient(135deg, #e1251b 0%, #ff6e40 60%, #f7a072 100%);
}
.login-card {
  width: 400px; background: #fff; border-radius: 12px; padding: 32px;
  box-shadow: 0 8px 30px rgba(0,0,0,.15);
}
.login-logo { text-align: center; font-size: 22px; font-weight: bold; color: #e1251b; margin-bottom: 16px; }
.login-logo span { font-size: 26px; margin-right: 4px; }
.role-switch { width: 100%; margin-bottom: 16px; display: flex; }
.role-switch :deep(.el-radio-button) { flex: 1; }
.role-switch :deep(.el-radio-button__inner) { width: 100%; }
.login-tip { text-align: center; color: #999; font-size: 12px; margin-top: 16px; line-height: 1.6; }
</style>
