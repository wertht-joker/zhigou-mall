<template>
  <div class="mall">
    <!-- 顶部通栏 -->
    <header class="topbar">
      <div class="topbar-inner">
        <div class="left-links">
          <router-link to="/">首页</router-link>
          <router-link v-if="isMerchant()" to="/admin/products">商家后台</router-link>
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
                  <el-dropdown-item v-if="isMerchant()" command="admin" divided>商家后台</el-dropdown-item>
                  <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
          <template v-else>
            <router-link to="/login">你好，请登录</router-link>
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
              <el-button type="primary" @click="doSearch">🔍 搜索</el-button>
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
import request, { TOKEN_KEY, getStoredUser, isMerchant, clearSession } from '../api'
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

/* 顶部通栏 */
.topbar { background: #e3e4e5; font-size: 12px; color: #666; }
.topbar-inner {
  max-width: 1190px; margin: 0 auto; padding: 6px 16px;
  display: flex; justify-content: space-between; align-items: center;
}
.topbar-inner a { color: #666; margin-right: 12px; }
.topbar-inner a:hover { color: #e1251b; }
.right-links { display: flex; align-items: center; gap: 4px; }
.hello { color: #e1251b; margin-right: 8px; }
.dropdown-trigger { font-size: 12px; color: #666; cursor: pointer; outline: none; }

/* 主导航 */
.mainbar { background: #fff; box-shadow: 0 2px 8px rgba(0,0,0,.04); }
.mainbar-inner {
  max-width: 1190px; margin: 0 auto; padding: 14px 16px;
  display: flex; align-items: center; gap: 32px;
}
.logo { display: flex; align-items: center; gap: 6px; }
.logo-icon { font-size: 30px; }
.logo-text { font-size: 22px; font-weight: 700; color: #e1251b; letter-spacing: 1px; }
.search-box { flex: 1; max-width: 560px; }
.cart-entry {
  display: flex; align-items: center; gap: 6px;
  border: 1px solid #e1251b; color: #e1251b;
  padding: 8px 16px; border-radius: 4px; font-size: 14px; cursor: pointer;
}
.cart-icon { font-size: 18px; }

.mall-main { flex: 1; width: 100%; max-width: 1190px; margin: 0 auto; padding: 16px; }

.footer {
  margin-top: 32px; padding: 24px 0 32px; text-align: center;
  color: #999; font-size: 12px; background: #fff; border-top: 1px solid #eee;
}
.footer-sub { margin-top: 6px; color: #c0c0c0; }
</style>

<style>
/* ===== 页面切换过渡动画 ===== */
.page-swap-enter-active { transition: opacity .28s ease, transform .28s ease; }
.page-swap-leave-active { transition: opacity .18s ease, transform .18s ease; }
.page-swap-enter-from { opacity: 0; transform: translateY(14px); }
.page-swap-leave-to { opacity: 0; transform: translateY(-8px); }
</style>
