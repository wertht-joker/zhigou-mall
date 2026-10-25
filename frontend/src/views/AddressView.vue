<template>
  <div class="page">
    <div class="page-card">
      <div class="page-head">
        <h3>📍 收货地址管理</h3>
        <el-button type="primary" @click="openAdd">＋ 新增地址</el-button>
      </div>

      <div v-loading="loading" class="addr-grid">
        <div v-for="a in addresses" :key="a.id" class="addr-card" :class="{ default: a.is_default }">
          <div class="addr-top">
            <b class="receiver">{{ a.receiver }}</b>
            <span class="phone">{{ a.phone }}</span>
            <el-tag v-if="a.is_default" size="small" type="danger" effect="plain">默认</el-tag>
          </div>
          <div class="addr-region">📍 {{ a.region || '（未选择省市区）' }}</div>
          <div class="addr-detail">{{ a.detail }}</div>
          <div class="addr-ops">
            <el-button v-if="!a.is_default" size="small" text type="primary" @click="setDefault(a)">设为默认</el-button>
            <el-button size="small" text type="primary" @click="openEdit(a)">编辑</el-button>
            <el-button size="small" text type="danger" @click="remove(a)">删除</el-button>
          </div>
        </div>
        <div v-if="!loading && addresses.length === 0" class="empty">
          <el-empty description="还没有收货地址，添加一个吧">
            <el-button type="primary" @click="openAdd">＋ 新增地址</el-button>
          </el-empty>
        </div>
      </div>

      <div class="locate-tip">💡 新增/编辑地址时支持「📍 定位」一键填入当前位置（浏览器会请求定位权限）</div>
    </div>

    <AddressFormDialog v-model="dialogVisible" :address="editing" @saved="load" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../api'
import AddressFormDialog from '../components/AddressFormDialog.vue'

const addresses = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const editing = ref(null)

async function load() {
  loading.value = true
  try {
    const list = await request.get('/addresses')
    addresses.value = [...list].sort((x, y) => (y.is_default ? 1 : 0) - (x.is_default ? 1 : 0))
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function openAdd() {
  editing.value = null
  dialogVisible.value = true
}

function openEdit(a) {
  editing.value = a
  dialogVisible.value = true
}

async function setDefault(a) {
  try {
    await request.put(`/addresses/${a.id}`, { ...a, is_default: true })
    ElMessage.success('已设为默认地址')
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function remove(a) {
  await ElMessageBox.confirm(`确认删除「${a.receiver}」的这条地址？`, '提示', { type: 'warning' })
  try {
    await request.delete(`/addresses/${a.id}`)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(load)
</script>

<style scoped>
.page-card { background: #fff; border-radius: 8px; padding: 20px 24px; }
.page-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }

.addr-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
.addr-card {
  border: 1px solid #eee; border-radius: 8px; padding: 14px 16px; position: relative;
  transition: box-shadow .2s;
}
.addr-card:hover { box-shadow: 0 4px 14px rgba(0,0,0,.07); }
.addr-card.default { border-color: #e1251b; }
.addr-top { display: flex; align-items: center; gap: 10px; }
.receiver { font-size: 15px; }
.phone { color: #999; font-size: 13px; }
.addr-region { margin-top: 8px; font-size: 13px; color: #666; }
.addr-detail { margin-top: 4px; font-size: 13px; color: #333; line-height: 1.5; }
.addr-ops { margin-top: 10px; display: flex; justify-content: flex-end; gap: 2px; }
.empty { grid-column: 1 / -1; }
.locate-tip { margin-top: 16px; font-size: 12px; color: #aaa; }
</style>
