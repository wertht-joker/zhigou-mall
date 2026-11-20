<template>
  <div class="mall">
    <!-- 顶部通栏 -->
    <header class="topbar">
      <div class="topbar-inner">
        <div class="left-links">
          <span class="promo-dot"></span>
          <span class="promo-text">AI 客服 24h 在线 · 售后问题直接办</span>
          <router-link to="/" class="nav-home">首页</router-link>
          <router-link v-if="isPlatformAdmin()" to="/platform/dashboard">平台后台</router-link>
          <router-link v-else-if="isMerchant()" to="/admin/products">商家后台</router-link>
        </div>
        <div class="right-links">
          <template v-if="user">
            <span class="hello">Hi，{{ user.username }}</span>
            <el-dropdown @command="onUserCommand">
              <span class="dropdown-trigger">我的账户 ▾</span>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="orders">我的订单</el-dropdown-item>
                  <el-dropdown-item command="addresses">地址管理</el-dropdown-item>
                  <el-dropdown-item command="cart">我的购物车</el-dropdown-item>
                  <el-dropdown-item v-if="isPlatformAdmin()" command="platform" divided>平台后台</el-dropdown-item>
                  <el-dropdown-item v-else-if="isMerchant()" command="admin" divided>商家后台</el-dropdown-item>
                  <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
          <template v-else>
            <router-link to="/login" class="login-link">登录</router-link>
            <router-link to="/login?tab=register" class="free-register">免费注册</router-link>
          </template>
        </div>
      </div>
    </header>

    <!-- 主导航：logo + 搜索框 + 购物车 -->
    <header class="mainbar">
      <div class="mainbar-inner">
        <router-link to="/" class="logo">
          <span class="logo-icon">🛍️</span>
          <span class="logo-text">智购商城</span>
        </router-link>
        <div class="search-box">
          <el-input
            v-model="keyword"
            placeholder="搜索商品，如：降噪耳机 / 空气净化器"
            size="large"
            clearable
            @keyup.enter="doSearch"
          >
            <template #append>
              <el-button type="primary" @click="doSearch">搜索</el-button>
            </template>
          </el-input>
        </div>
        <router-link to="/cart" class="cart-entry">
          <el-badge :value="cartCount" :hidden="!cartCount">
            <span class="cart-icon">🛒</span>
          </el-badge>
          <span>购物车</span>
        </router-link>
      </div>
    </header>

    <!-- 页面内容（带页面切换过渡动画） -->
    <main class="mall-main">
      <router-view v-slot="{ Component }">
        <transition name="page-swap" mode="out-in">
          <component :is="Component" @cart-updated="loadCartCount" />
        </transition>
      </router-view>
    </main>

    <footer class="footer">
      <div>智购商城 · 多商家入驻电商平台 + AI 智能客服（RAG + ReAct Agent）</div>
      <div class="footer-sub">演示项目 · 商品与订单均为演示数据</div>
    </footer>

    <!-- AI 智能客服悬浮窗 -->
    <ChatWidget v-if="user" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import request, { TOKEN_KEY, getStoredUser, isMerchant, isPlatformAdmin, clearSession } from '../api'
import ChatWidget from './ChatWidget.vue'

const router = useRouter()
const keyword = ref('')
const user = ref(getStoredUser())
const cartCount = ref(0)

async function loadCartCount() {
  if (!localStorage.getItem(TOKEN_KEY)) return
  try {
    const items = await request.get('/cart')
    cartCount.value = items.reduce((sum, i) => sum + i.quantity, 0)
  } catch (e) { /* 未登录等情况忽略 */ }
}

function doSearch() {
  router.push({ path: '/search', query: keyword.value.trim() ? { q: keyword.value.trim() } : {} })
}

function onUserCommand(cmd) {
  if (cmd === 'logout') {
    clearSession()
    window.location.href = '/login'
  } else if (cmd === 'platform') {
    router.push('/platform/dashboard')
  } else if (cmd === 'admin') {
    router.push('/admin/products')
  } else {
    router.push('/' + cmd)
  }
}

onMounted(loadCartCount)
</script>

<style scoped>
.mall { min-height: 100vh; display: flex; flex-direction: column; }

/* ===== 顶部通栏：深色细条，和内容区拉开层次 ===== */
.topbar {
  background: #17181c;
  color: rgba(255, 255, 255, .68);
  font-size: 12.5px;
}
.topbar-inner {
  max-width: 1240px; margin: 0 auto; padding: 9px 24px;
  display: flex; justify-content: space-between; align-items: center;
}
.left-links, .right-links { display: flex; align-items: center; gap: 14px; }
.topbar-inner a { color: rgba(255, 255, 255, .68); transition: color .2s ease; }
.topbar-inner a:hover { color: #fff; }
.promo-dot {
  width: 6px; height: 6px; border-radius: 50%; background: #4ade80;
  box-shadow: 0 0 0 4px rgba(74, 222, 128, .12);
}
.promo-text { letter-spacing: .02em; }
.nav-home { font-weight: 600; color: rgba(255, 255, 255, .9) !important; }
.login-link {
  color: #fff !important; font-weight: 600;
  background: rgba(255, 255, 255, .12);
  border: 1px solid rgba(255, 255, 255, .18);
  border-radius: 999px; padding: 5px 16px; line-height: 1;
  transition: background .2s ease, transform .2s ease;
}
.login-link:hover { background: var(--brand); border-color: var(--brand); transform: translateY(-1px); }
.free-register { color: rgba(255, 255, 255, .78) !important; }
.hello { color: #ffb4a8; margin-right: 2px; }
.dropdown-trigger {
  font-size: 12.5px; color: rgba(255, 255, 255, .78);
  cursor: pointer; outline: none;
}
.dropdown-trigger:hover { color: #fff; }

/* ===== 主导航：吸顶 + 毛玻璃 ===== */
.mainbar {
  position: sticky; top: 0; z-index: 100;
  background: rgba(247, 245, 242, .8);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  border-bottom: 1px solid var(--line);
}
.mainbar-inner {
  max-width: 1240px; margin: 0 auto; padding: 14px 24px;
  display: flex; align-items: center; gap: 30px;
}
.logo { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.logo-icon {
  width: 44px; height: 44px; border-radius: 14px;
  display: flex; align-items: center; justify-content: center;
  font-size: 23px; background: var(--brand-gradient);
  box-shadow: 0 8px 20px rgba(255, 95, 87, .28);
}
.logo-text {
  font-size: 22px; font-weight: 800; letter-spacing: -.02em;
  background: linear-gradient(120deg, #1c1d22 20%, #ff5f57 90%);
  -webkit-background-clip: text; background-clip: text; color: transparent;
}
.search-box { flex: 1; max-width: 620px; }
.search-box :deep(.el-input__wrapper) {
  border-radius: 999px 0 0 999px;
  padding-left: 20px;
  background: #fff;
  box-shadow: 0 6px 22px rgba(48, 28, 16, .06), 0 0 0 1px var(--line) inset;
}
.search-box :deep(.el-input-group__append) {
  background: #fff;
  border: none;
  border-radius: 0 999px 999px 0;
  box-shadow: 0 6px 22px rgba(48, 28, 16, .06), 0 0 0 1px var(--line) inset;
  padding: 4px;
}
.search-box :deep(.el-input-group__append .el-button) {
  height: 38px; padding: 0 24px; border-radius: 999px; border: none;
}
.cart-entry {
  display: flex; align-items: center; gap: 8px; flex-shrink: 0;
  padding: 11px 20px; border-radius: 999px;
  color: #fff; font-size: 14px; font-weight: 600;
  background: var(--brand-gradient);
  box-shadow: 0 10px 24px rgba(255, 95, 87, .24);
  transition: transform .2s ease, box-shadow .2s ease;
}
.cart-entry:hover { transform: translateY(-2px); box-shadow: 0 14px 30px rgba(255, 95, 87, .3); }
.cart-icon { font-size: 18px; }

.mall-main {
  flex: 1; width: 100%; max-width: 1240px;
  margin: 0 auto; padding: 24px;
}

.footer {
  margin-top: 48px; padding: 30px 24px 36px; text-align: center;
  color: rgba(255, 255, 255, .62); font-size: 12.5px;
  border-top: 3px solid transparent;
  background:
    linear-gradient(#17181c, #17181c) padding-box,
    var(--brand-gradient) border-box;
}
.footer-sub { margin-top: 8px; color: rgba(255, 255, 255, .34); }

@media (max-width: 900px) {
  .promo-text { display: none; }
  .mainbar-inner { flex-wrap: wrap; gap: 12px; padding: 12px 16px; }
  .search-box { order: 3; flex-basis: 100%; max-width: none; }
  .logo-text { font-size: 19px; }
  .cart-entry { margin-left: auto; padding: 10px 16px; }
  .mall-main { padding: 16px; }
  .topbar-inner { padding: 8px 16px; }
}
</style>

<style>
/* ===== 页面切换过渡动画 ===== */
.page-swap-enter-active { transition: opacity .28s ease, transform .28s ease; }
.page-swap-leave-active { transition: opacity .18s ease, transform .18s ease; }
.page-swap-enter-from { opacity: 0; transform: translateY(14px); }
.page-swap-leave-to { opacity: 0; transform: translateY(-8px); }
</style>
