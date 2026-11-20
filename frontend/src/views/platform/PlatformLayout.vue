<template>
  <el-container class="platform-layout">
    <el-aside width="232px" class="pf-aside">
      <div class="pf-logo" @click="$router.push('/platform/dashboard')">
        <span class="pf-logo-mark">智</span>
        <div>
          <div class="pf-logo-title">智购平台管理</div>
          <div class="pf-logo-sub">PLATFORM CONSOLE</div>
        </div>
      </div>

      <el-menu :default-active="activeMenu" router class="pf-menu">
        <el-menu-item index="/platform/dashboard">📊 平台概览</el-menu-item>
        <el-menu-item index="/platform/insights">🧠 智能洞察</el-menu-item>
        <el-menu-item index="/platform/tenants">🏬 商家管理</el-menu-item>
        <el-menu-item-group title="交易监管">
          <el-menu-item index="/platform/products">📦 商品监管</el-menu-item>
          <el-menu-item index="/platform/orders">🧾 订单监管</el-menu-item>
          <el-menu-item index="/platform/categories">🗂️ 商品分类</el-menu-item>
          <el-menu-item index="/platform/customers">👥 用户管理</el-menu-item>
        </el-menu-item-group>
        <el-menu-item-group title="内容运营">
          <el-menu-item index="/platform/knowledge">📚 知识库管理</el-menu-item>
          <el-menu-item index="/platform/knowledge-categories">🗂️ 知识分类</el-menu-item>
          <el-menu-item index="/platform/feedback">💬 反馈分析</el-menu-item>
        </el-menu-item-group>
        <el-menu-item-group title="系统">
          <el-menu-item index="/platform/audit">🧭 操作审计</el-menu-item>
        </el-menu-item-group>
      </el-menu>

      <div class="pf-aside-foot">
        <div class="pf-role">平台管理员</div>
        <div class="pf-user">👤 {{ user?.username }}</div>
      </div>
    </el-aside>

    <el-container class="pf-body">
      <el-header class="pf-header">
        <div class="pf-header-title">{{ pageTitle }}</div>
        <div class="pf-header-ops">
          <el-button text @click="$router.push('/')">回商城</el-button>
          <el-button text type="danger" @click="logout">退出登录</el-button>
        </div>
      </el-header>
      <el-main class="pf-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getStoredUser, clearSession } from '../../api'

const route = useRoute()
const router = useRouter()
const user = computed(() => getStoredUser())
const activeMenu = computed(() => route.path)
const pageTitle = computed(() => route.meta.title || '平台管理')

function logout() {
  clearSession()
  window.location.href = '/login'
}
</script>

<style scoped>
.platform-layout { min-height: 100vh; background: #f3f5fa; }
.pf-aside {
  background: #0f172a; color: #fff; display: flex; flex-direction: column;
  position: sticky; top: 0; height: 100vh;
}
.pf-logo {
  display: flex; align-items: center; gap: 12px; padding: 22px 20px;
  cursor: pointer; border-bottom: 1px solid rgba(255, 255, 255, .08);
}
.pf-logo-mark {
  width: 40px; height: 40px; border-radius: 12px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 18px; color: #06121f;
  background: linear-gradient(135deg, #5eead4 0%, #60a5fa 100%);
}
.pf-logo-title { font-size: 15px; font-weight: 700; letter-spacing: .02em; }
.pf-logo-sub { margin-top: 3px; font-size: 9px; letter-spacing: .16em; color: rgba(255, 255, 255, .38); }

.pf-menu { border-right: none; background: transparent; padding: 12px 10px; flex: 1; overflow-y: auto; }
.pf-menu :deep(.el-menu-item-group__title) {
  padding: 14px 12px 6px !important; font-size: 10px; letter-spacing: .12em;
  color: rgba(255, 255, 255, .3); text-transform: uppercase;
}
.pf-menu :deep(.el-menu-item) {
  height: 46px; line-height: 46px; margin-bottom: 4px; border-radius: 10px;
  color: rgba(255, 255, 255, .66); font-size: 14px;
}
.pf-menu :deep(.el-menu-item:hover) { background: rgba(255, 255, 255, .06); color: #fff; }
.pf-menu :deep(.el-menu-item.is-active) {
  background: linear-gradient(135deg, rgba(94, 234, 212, .18), rgba(96, 165, 250, .18));
  color: #7dd3fc; font-weight: 600;
}
.pf-aside-foot {
  padding: 16px 20px 20px; border-top: 1px solid rgba(255, 255, 255, .08);
}
.pf-role { font-size: 11px; color: #5eead4; letter-spacing: .08em; }
.pf-user { margin-top: 4px; font-size: 13px; color: rgba(255, 255, 255, .62); }

.pf-body { min-width: 0; }
.pf-header {
  height: 64px; display: flex; align-items: center; justify-content: space-between;
  padding: 0 28px; background: rgba(255, 255, 255, .82); backdrop-filter: blur(14px);
  border-bottom: 1px solid rgba(15, 23, 42, .07); position: sticky; top: 0; z-index: 10;
}
.pf-header-title { font-size: 17px; font-weight: 700; color: #0f172a; }
.pf-main { padding: 24px 28px 40px; }
</style>

<style>
/* 平台后台通用页面样式（供各子页面复用） */
.pf-page { display: flex; flex-direction: column; gap: 18px; }
.pf-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.pf-title { font-size: 20px; font-weight: 800; color: #0f172a; letter-spacing: -.01em; }
.pf-sub { margin-top: 6px; font-size: 13px; color: #7c8598; }
.pf-toolbar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.pf-card {
  background: #fff; border-radius: 16px; padding: 20px;
  border: 1px solid rgba(15, 23, 42, .06);
  box-shadow: 0 10px 30px rgba(15, 23, 42, .05);
}
.pf-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.pf-stat {
  background: #fff; border-radius: 16px; padding: 20px;
  border: 1px solid rgba(15, 23, 42, .06);
  box-shadow: 0 10px 30px rgba(15, 23, 42, .05);
  position: relative; overflow: hidden;
}
.pf-stat::after {
  content: ''; position: absolute; right: -30px; top: -30px;
  width: 90px; height: 90px; border-radius: 50%;
  background: radial-gradient(circle, rgba(47, 107, 255, .12), transparent 70%);
}
.pf-stat-label { font-size: 13px; color: #7c8598; }
.pf-stat-value { margin-top: 10px; font-size: 28px; font-weight: 800; color: #0f172a; letter-spacing: -.02em; }
.pf-stat-hint { margin-top: 6px; font-size: 12px; color: #98a1b3; }
.pf-money { color: #0f172a; font-weight: 700; }
.pf-muted { color: #98a1b3; font-size: 12px; }
@media (max-width: 1100px) {
  .pf-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 700px) {
  .pf-grid { grid-template-columns: 1fr; }
  .pf-main { padding: 16px; }
}
</style>
