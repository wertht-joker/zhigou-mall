<template>
  <el-container class="admin-layout">
    <el-aside width="236px" class="aside">
      <div class="brand" @click="$router.push('/')">
        <div class="brand-mark">🛍️</div>
        <div>
          <div class="brand-name">智购商家中心</div>
          <div class="brand-sub">MERCHANT CONSOLE</div>
        </div>
      </div>

      <div class="store-card">
        <div class="store-label">当前店铺</div>
        <div class="store-name">{{ tenant?.name || '未归属店铺' }}</div>
        <div class="store-meta">
          <span class="store-code">{{ tenant?.code || '-' }}</span>
          <el-tag size="small" :type="isSelf ? 'success' : 'info'" effect="dark">
            {{ isSelf ? '自营' : '第三方' }}
          </el-tag>
        </div>
      </div>

      <div class="menu-label">经营</div>
      <el-menu :default-active="activeMenu" router class="menu">
        <el-menu-item index="/admin/products"><span class="mi">📦</span>商品管理</el-menu-item>
        <el-menu-item index="/admin/orders"><span class="mi">🚚</span>订单发货</el-menu-item>
      </el-menu>

      <div class="menu-label">服务</div>
      <el-menu :default-active="activeMenu" router class="menu">
        <el-menu-item index="/admin/aftersale"><span class="mi">🧾</span>售后处理</el-menu-item>
        <el-menu-item index="/admin/reviews"><span class="mi">⭐</span>评价管理</el-menu-item>
      </el-menu>

      <div class="user-box">
        <div class="avatar">{{ initial }}</div>
        <div class="user-text">
          <div class="username">{{ user?.username }}</div>
          <div class="role">店铺管理员</div>
        </div>
        <el-button text class="logout" @click="logout">退出</el-button>
      </div>
    </el-aside>

    <el-main class="main">
      <div class="topbar">
        <div class="crumb">
          <span class="crumb-root">商家后台</span>
          <span class="crumb-sep">/</span>
          <span>{{ pageTitle }}</span>
        </div>
        <div class="top-actions">
          <el-button text @click="$router.push('/')">← 回商城</el-button>
        </div>
      </div>
      <div class="content">
        <router-view />
      </div>
    </el-main>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { getStoredUser, getStoredTenant, clearSession } from '../../api'

const route = useRoute()
const activeMenu = computed(() => route.path)
const user = computed(() => getStoredUser())
const tenant = computed(() => getStoredTenant())
const isSelf = computed(() => tenant.value?.code === 'default')
const initial = computed(() => (user.value?.username || 'M').slice(0, 1).toUpperCase())

const PAGE_TITLES = {
  '/admin/products': '商品管理',
  '/admin/orders': '订单发货',
  '/admin/aftersale': '售后处理',
  '/admin/reviews': '评价管理',
}
const pageTitle = computed(() => PAGE_TITLES[route.path] || '商家后台')

function logout() {
  clearSession()
  window.location.href = '/login'
}
</script>

<style scoped>
.admin-layout { min-height: 100vh; background: #f5f7fb; }

.aside {
  background:
    radial-gradient(360px 220px at 10% 0%, rgba(255, 122, 89, .18), transparent 65%),
    #0f172a;
  color: rgba(255, 255, 255, .82);
  display: flex;
  flex-direction: column;
  padding: 18px 14px 14px;
  position: sticky;
  top: 0;
  height: 100vh;
}
.brand {
  display: flex; align-items: center; gap: 12px;
  padding: 6px 8px 20px; cursor: pointer;
}
.brand-mark {
  width: 42px; height: 42px; border-radius: 13px;
  display: flex; align-items: center; justify-content: center;
  font-size: 22px; background: var(--brand-gradient);
  box-shadow: 0 8px 18px rgba(255, 95, 87, .3);
}
.brand-name { font-size: 16px; font-weight: 800; color: #fff; letter-spacing: -.01em; }
.brand-sub { margin-top: 2px; font-size: 9px; letter-spacing: .18em; color: rgba(255, 255, 255, .36); }

.store-card {
  padding: 13px 14px; margin: 0 4px 18px;
  border-radius: 14px;
  background: rgba(255, 255, 255, .06);
  border: 1px solid rgba(255, 255, 255, .08);
}
.store-label { font-size: 10px; color: rgba(255, 255, 255, .4); letter-spacing: .08em; }
.store-name {
  margin-top: 5px; font-size: 14px; font-weight: 700; color: #fff;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.store-meta { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; }
.store-code { font-size: 11px; color: rgba(255, 255, 255, .5); }

.menu-label {
  padding: 10px 12px 6px; font-size: 10px; letter-spacing: .14em;
  color: rgba(255, 255, 255, .32);
}
.menu { border: none; background: transparent; }
.menu :deep(.el-menu-item) {
  height: 42px; margin: 2px 4px; padding-left: 12px !important;
  border-radius: 11px; color: rgba(255, 255, 255, .66);
  font-size: 13.5px; background: transparent;
}
.menu :deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, .07); color: #fff;
}
.menu :deep(.el-menu-item.is-active) {
  color: #fff; font-weight: 700;
  background: var(--brand-gradient);
  box-shadow: 0 8px 18px rgba(255, 95, 87, .22);
}
.mi { margin-right: 9px; font-size: 15px; }

.user-box {
  margin-top: auto; display: flex; align-items: center; gap: 10px;
  padding: 12px 8px 4px; border-top: 1px solid rgba(255, 255, 255, .08);
}
.avatar {
  width: 34px; height: 34px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  background: rgba(255, 255, 255, .12); color: #fff; font-weight: 700;
}
.user-text { flex: 1; min-width: 0; }
.username { font-size: 12.5px; color: #fff; overflow: hidden; text-overflow: ellipsis; }
.role { font-size: 10.5px; color: rgba(255, 255, 255, .4); margin-top: 2px; }
.logout { color: rgba(255, 255, 255, .5) !important; font-size: 12px; }
.logout:hover { color: #ff8a80 !important; }

.main { padding: 0; min-width: 0; background: #f5f7fb; }
.topbar {
  height: 58px; padding: 0 26px;
  display: flex; align-items: center; justify-content: space-between;
  background: rgba(255, 255, 255, .86);
  backdrop-filter: blur(14px);
  border-bottom: 1px solid rgba(23, 24, 28, .06);
  position: sticky; top: 0; z-index: 20;
}
.crumb { font-size: 13px; color: #4b5563; font-weight: 600; }
.crumb-root { color: #9aa1ae; font-weight: 500; }
.crumb-sep { margin: 0 8px; color: #cbd0d8; }
.top-actions :deep(.el-button) { color: #6b7280; }
.content { padding: 22px 26px 40px; max-width: 1360px; margin: 0 auto; }

@media (max-width: 900px) {
  .aside { width: 200px !important; }
  .brand-sub, .store-code { display: none; }
  .content { padding: 16px; }
  .topbar { padding: 0 16px; }
}
</style>
