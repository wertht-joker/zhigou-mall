<template>
  <el-container class="admin-layout">
    <el-aside width="200px" class="aside">
      <div class="logo" @click="$router.push('/')">🛍️ 智购商家后台</div>
      <el-menu :default-active="activeMenu" router>
        <el-menu-item index="/admin/products">📦 商品管理</el-menu-item>
        <el-menu-item index="/admin/orders">🚚 订单管理</el-menu-item>
        <el-menu-item index="/admin/reviews">⭐ 评价管理</el-menu-item>
        <el-menu-item index="/admin/documents">📄 知识库管理</el-menu-item>
        <el-menu-item index="/admin/categories">🗂️ 知识分类</el-menu-item>
      </el-menu>
      <div class="user-box">
        <div class="user-info">
          <span class="username">👤 {{ user?.username }}</span>
          <span class="store">🏪 {{ tenant?.name || '未归属店铺' }}</span>
        </div>
        <div class="user-ops">
          <el-button text size="small" @click="$router.push('/')">回商城</el-button>
          <el-button text size="small" type="danger" @click="logout">退出</el-button>
        </div>
      </div>
    </el-aside>
    <el-main class="main">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getStoredUser, getStoredTenant, clearSession } from '../../api'

const route = useRoute()
const router = useRouter()
const activeMenu = computed(() => route.path)
const user = computed(() => getStoredUser())
const tenant = computed(() => getStoredTenant())

function logout() {
  clearSession()
  window.location.href = '/login'
}
</script>

<style>
.admin-layout { height: 100vh; }
.admin-layout .aside { background: #fff; border-right: 1px solid #eee; display: flex; flex-direction: column; }
.admin-layout .logo { font-size: 16px; font-weight: bold; color: #e1251b; padding: 20px 16px; cursor: pointer; }
.admin-layout .user-box {
  margin-top: auto; padding: 12px 16px; border-top: 1px solid #eee;
  display: flex; align-items: center; justify-content: space-between; gap: 4px;
}
.admin-layout .user-info { display: flex; flex-direction: column; gap: 2px; overflow: hidden; }
.admin-layout .username { font-size: 13px; color: #666; }
.admin-layout .store { font-size: 12px; color: #999; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.admin-layout .user-ops { display: flex; flex-direction: column; }
.admin-layout .main { padding: 0; background: #f5f6fa; }
</style>
