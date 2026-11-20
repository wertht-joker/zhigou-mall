<template>
  <div class="login-page">
    <div class="login-shell">
      <!-- 左侧品牌区：大屏展示，小屏隐藏 -->
      <aside class="brand">
        <div class="brand-glow brand-glow-a"></div>
        <div class="brand-glow brand-glow-b"></div>
        <div class="brand-top">
          <span class="brand-logo">🛍️</span>
          <span class="brand-name">智购商城</span>
        </div>
        <div class="brand-copy">
          <h1>让好物<br />更快到达</h1>
          <p>多商家正品好物 · AI 客服全程在线</p>
        </div>
        <ul class="brand-points">
          <li><span>🚚</span>自营发货，物流全程可查</li>
          <li><span>🤖</span>AI 客服，售后秒级响应</li>
          <li><span>🏬</span>多商家入驻，店铺数据隔离</li>
        </ul>
        <div class="brand-foot">智购自营 · 星辰数码 等店铺已入驻</div>
      </aside>

      <!-- 右侧表单区 -->
      <section class="form-side">
        <div class="form-head">
          <h2>{{ tab === 'login' ? '欢迎回来' : '创建账号' }}</h2>
          <p>{{ tab === 'login' ? '登录后继续逛智购商城' : '注册即享新人优惠与专属客服' }}</p>
        </div>

        <div class="segmented">
          <span class="seg-thumb" :class="{ right: tab === 'register' }"></span>
          <button type="button" :class="{ active: tab === 'login' }" @click="switchTab('login')">登录</button>
          <button type="button" :class="{ active: tab === 'register' }" @click="switchTab('register')">注册</button>
        </div>

        <el-form class="login-form" @submit.prevent="submit">
          <div v-if="tab === 'register'" class="role-switch">
            <button
              v-for="role in roles"
              :key="role.value"
              type="button"
              class="role-item"
              :class="{ active: registerType === role.value }"
              @click="registerType = role.value"
            >
              <b>{{ role.title }}</b>
              <small>{{ role.desc }}</small>
            </button>
          </div>

          <el-form-item v-if="tab === 'register' && registerType === 'merchant'">
            <el-input v-model.trim="form.merchant_name" size="large" maxlength="30" placeholder="店铺名称，如：星辰数码旗舰店">
              <template #prefix>
                <svg class="inp-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M4 9l1-5h14l1 5" /><path d="M4 9h16v11H4z" /><path d="M9 20v-6h6v6" />
                </svg>
              </template>
            </el-input>
          </el-form-item>

          <el-form-item>
            <el-input
              v-model.trim="form.username"
              size="large"
              placeholder="请输入用户名"
              autocomplete="username"
              @keyup.enter="submit"
            >
              <template #prefix>
                <svg class="inp-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 3.6-6 8-6s8 2 8 6" />
                </svg>
              </template>
            </el-input>
          </el-form-item>

          <el-form-item>
            <el-input
              v-model="form.password"
              type="password"
              size="large"
              placeholder="请输入密码"
              show-password
              autocomplete="current-password"
              @keyup.enter="submit"
            >
              <template #prefix>
                <svg class="inp-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="4" y="10" width="16" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" />
                </svg>
              </template>
            </el-input>
          </el-form-item>

          <el-button type="primary" size="large" class="login-submit" :loading="loading" native-type="submit">
            {{ submitLabel }}
          </el-button>
        </el-form>

        <div class="demo-block">
          <div class="demo-title">
            <span>演示账号</span>
            <em>点击自动填充</em>
          </div>
          <div class="demo-grid">
            <button
              v-for="item in demos"
              :key="item.account"
              type="button"
              class="demo-item"
              @click="fillDemo(item)"
            >
              <b>{{ item.label }}</b>
              <span>{{ item.account }} / {{ item.password }}</span>
            </button>
          </div>
        </div>

        <button type="button" class="back-home" @click="router.push('/')">← 返回商城首页</button>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import request, { saveSession, isMerchant, isPlatformAdmin } from '../api'

const route = useRoute()
const router = useRouter()
const tab = ref(route.query.tab === 'register' ? 'register' : 'login')
const registerType = ref('customer')
const loading = ref(false)
const form = ref({ username: '', password: '', merchant_name: '' })

const roles = [
  { value: 'customer', title: '我要买东西', desc: '注册即成为顾客' },
  { value: 'merchant', title: '我要开店', desc: '入驻自动建店' },
]

const demos = [
  { label: '顾客', account: 'demo', password: 'demo123' },
  { label: '平台管理员', account: 'admin', password: 'admin123' },
  { label: '自营店长', account: 'self', password: 'self123' },
  { label: '第三方商家', account: 'shop', password: 'shop123' },
]

const submitLabel = computed(() => {
  if (tab.value === 'login') return '登 录'
  return registerType.value === 'merchant' ? '入驻并进入商家后台' : '注册并进入商城'
})

function switchTab(next) {
  tab.value = next
}

function fillDemo(item) {
  tab.value = 'login'
  registerType.value = 'customer'
  form.value.username = item.account
  form.value.password = item.password
}

// 只接受站内路径，避免 ?redirect=//evil.com 之类的跳转
function safeRedirect(value, fallback = '/') {
  if (typeof value !== 'string') return fallback
  if (!value.startsWith('/') || value.startsWith('//')) return fallback
  return value
}

async function submit() {
  if (loading.value) return
  if (!form.value.username || !form.value.password) {
    return ElMessage.warning('请输入用户名和密码')
  }
  if (tab.value === 'register' && registerType.value === 'merchant' && !form.value.merchant_name) {
    return ElMessage.warning('请填写店铺名称')
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
      // 平台管理员进平台后台；商家进商家后台；顾客回商城
      if (isPlatformAdmin()) {
        router.push('/platform/dashboard')
      } else if (isMerchant()) {
        const redirect = safeRedirect(route.query.redirect, '')
        const target = redirect.startsWith('/admin') ? redirect : '/admin/products'
        router.push(target)
      } else {
        router.push(safeRedirect(route.query.redirect))
      }
    } else {
      const payload = { username: form.value.username, password: form.value.password }
      if (registerType.value === 'merchant') {
        payload.register_type = 'merchant'
        payload.merchant_name = form.value.merchant_name
      }
      // 注册成功直接返回 token，免二次登录
      const data = await request.post('/auth/register', payload)
      saveSession(data)
      ElMessage.success(
        registerType.value === 'merchant'
          ? `入驻成功！店铺编码 ${data.tenant.code}`
          : '注册成功，开始逛商城吧'
      )
      router.push(
        registerType.value === 'merchant'
          ? '/admin/products'
          : safeRedirect(route.query.redirect)
      )
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
  min-height: 100vh;
  padding: 32px 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(900px 420px at 12% 8%, rgba(225, 37, 27, .10), transparent 60%),
    radial-gradient(760px 400px at 92% 92%, rgba(255, 138, 61, .12), transparent 62%),
    #f7f4f2;
}

.login-shell {
  width: min(960px, 100%);
  min-height: 600px;
  display: grid;
  grid-template-columns: 46% 54%;
  background: #fff;
  border-radius: 24px;
  overflow: hidden;
  box-shadow: 0 30px 80px rgba(72, 30, 24, .16), 0 2px 8px rgba(72, 30, 24, .06);
  animation: rise .5s ease both;
}

@keyframes rise {
  from { opacity: 0; transform: translateY(14px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ===== 左侧品牌区 ===== */
.brand {
  position: relative;
  overflow: hidden;
  padding: 40px 38px;
  color: #fff;
  display: flex;
  flex-direction: column;
  background: linear-gradient(155deg, #8c1210 0%, #c81d18 46%, #ef4b2a 100%);
}

.brand-glow {
  position: absolute;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, .18);
  pointer-events: none;
}
.brand-glow-a { width: 320px; height: 320px; right: -140px; top: -120px; }
.brand-glow-b { width: 420px; height: 420px; left: -200px; bottom: -220px; }

.brand-top { display: flex; align-items: center; gap: 10px; font-size: 20px; font-weight: 700; letter-spacing: .5px; }
.brand-logo {
  width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center;
  background: rgba(255, 255, 255, .16); font-size: 22px;
}

.brand-copy { margin-top: 46px; }
.brand-copy h1 { font-size: 38px; line-height: 1.25; margin: 0; letter-spacing: 1px; }
.brand-copy p { margin: 14px 0 0; font-size: 14px; color: rgba(255, 255, 255, .78); }

.brand-points { list-style: none; padding: 0; margin: 40px 0 0; display: grid; gap: 16px; }
.brand-points li { display: flex; align-items: center; gap: 12px; font-size: 14px; color: rgba(255, 255, 255, .92); }
.brand-points span {
  width: 34px; height: 34px; border-radius: 10px; display: grid; place-items: center;
  background: rgba(255, 255, 255, .14); font-size: 17px;
}

.brand-foot { margin-top: auto; padding-top: 40px; font-size: 12px; color: rgba(255, 255, 255, .6); }

/* ===== 右侧表单区 ===== */
.form-side { padding: 44px 52px 32px; display: flex; flex-direction: column; }

.form-head h2 { margin: 0; font-size: 26px; color: #1f2329; letter-spacing: .5px; }
.form-head p { margin: 8px 0 22px; font-size: 13px; color: #8a9099; }

.segmented {
  position: relative;
  display: grid;
  grid-template-columns: 1fr 1fr;
  padding: 4px;
  border-radius: 12px;
  background: #f4f2f1;
  margin-bottom: 20px;
}
.segmented button {
  position: relative;
  z-index: 1;
  height: 38px;
  border: 0;
  background: transparent;
  font-size: 14px;
  color: #7b818a;
  cursor: pointer;
  border-radius: 9px;
  transition: color .2s;
}
.segmented button.active { color: #c81d18; font-weight: 600; }
.seg-thumb {
  position: absolute;
  z-index: 0;
  top: 4px; left: 4px;
  width: calc(50% - 4px);
  height: calc(100% - 8px);
  border-radius: 9px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(31, 35, 41, .08);
  transition: transform .25s ease;
}
.seg-thumb.right { transform: translateX(100%); }

.role-switch { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 16px; }
.role-item {
  text-align: left;
  padding: 10px 12px;
  border: 1px solid #ece9e7;
  border-radius: 10px;
  background: #fff;
  cursor: pointer;
  transition: border-color .2s, background .2s;
}
.role-item b { display: block; font-size: 13px; color: #1f2329; font-weight: 600; }
.role-item small { display: block; margin-top: 3px; font-size: 11px; color: #9aa0a8; }
.role-item.active { border-color: #e1251b; background: #fff6f4; }
.role-item.active b { color: #c81d18; }

.login-form :deep(.el-input__wrapper) {
  border-radius: 10px;
  box-shadow: 0 0 0 1px #e8e4e1 inset;
  padding: 2px 12px;
}
.login-form :deep(.el-input__wrapper.is-focus) { box-shadow: 0 0 0 1px #e1251b inset; }
.login-form :deep(.el-input__inner) { height: 40px; }
.inp-icon { width: 16px; height: 16px; color: #a3a8b0; }
.login-form :deep(.el-form-item) { margin-bottom: 16px; }

.login-submit {
  width: 100%;
  height: 48px;
  margin-top: 4px;
  border: 0;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 1px;
  background: linear-gradient(120deg, #d81e14, #ff5a36);
  box-shadow: 0 10px 22px rgba(225, 37, 27, .26);
}
.login-submit:hover { background: linear-gradient(120deg, #c81b12, #f04b28); }

.demo-block { margin-top: 20px; }
.demo-title { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.demo-title span { font-size: 12px; color: #6b7280; font-weight: 600; }
.demo-title em { font-style: normal; font-size: 11px; color: #b0b5bd; }
.demo-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.demo-item {
  text-align: left;
  padding: 8px 10px;
  border: 1px dashed #e8e4e1;
  border-radius: 8px;
  background: #fbfaf9;
  cursor: pointer;
  transition: border-color .2s, background .2s;
}
.demo-item b { display: block; font-size: 12px; color: #3f4650; font-weight: 600; }
.demo-item span { display: block; margin-top: 2px; font-size: 11px; color: #9aa0a8; }
.demo-item:hover { border-color: #e1251b; background: #fff6f4; }
.demo-item:hover b { color: #c81d18; }

.back-home {
  margin-top: auto;
  padding-top: 20px;
  border: 0;
  background: transparent;
  color: #9aa0a8;
  font-size: 12px;
  cursor: pointer;
  align-self: center;
}
.back-home:hover { color: #e1251b; }

/* ===== 小屏：收起品牌区 ===== */
@media (max-width: 860px) {
  .login-shell { grid-template-columns: 1fr; width: min(440px, 100%); min-height: auto; }
  .brand { display: none; }
  .form-side { padding: 34px 28px 24px; }
  .form-head h2 { font-size: 23px; }
}
</style>
