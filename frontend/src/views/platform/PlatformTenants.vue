<template>
  <div class="pf-page">
    <div class="pf-head">
      <div>
        <div class="pf-title">商家管理</div>
        <div class="pf-sub">查看全平台商家经营概况，并控制店铺启用状态</div>
      </div>
      <div class="pf-toolbar">
        <el-input
          v-model="keyword"
          placeholder="搜索店铺名称 / 编码"
          clearable
          style="width: 240px"
          @keyup.enter="load"
          @clear="load"
        />
        <el-button type="primary" @click="load">查询</el-button>
      </div>
    </div>

    <div class="pf-card">
      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column label="商家" min-width="200">
          <template #default="{ row }">
            <div class="tenant-name">
              🏬 {{ row.name }}
              <el-tag v-if="row.is_platform_store" size="small" type="success">平台自营</el-tag>
            </div>
            <div class="pf-muted">{{ row.code }}</div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
              {{ row.status === 'active' ? '营业中' : '已停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="product_count" label="商品数" width="90" align="center" />
        <el-table-column prop="on_sale_count" label="在售" width="80" align="center" />
        <el-table-column prop="order_count" label="订单数" width="90" align="center" />
        <el-table-column label="入住时间" width="150">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="启用" width="100" align="center">
          <template #default="{ row }">
            <el-tooltip
              v-if="row.is_platform_store"
              content="平台自营店不允许停用"
              placement="top"
            >
              <el-switch :model-value="true" disabled />
            </el-tooltip>
            <el-switch
              v-else
              :model-value="row.status === 'active'"
              :loading="row._loading"
              @change="toggle(row)"
            />
          </template>
        </el-table-column>
        <el-table-column prop="id" label="ID" width="70" align="center" />
      </el-table>
      <el-empty v-if="!loading && rows.length === 0" description="没有匹配的商家" />
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../../api'

const rows = ref([])
const loading = ref(false)
const keyword = ref('')

function formatDate(value) {
  if (!value) return '-'
  return value.slice(0, 10)
}

async function load() {
  loading.value = true
  try {
    const params = keyword.value.trim() ? { keyword: keyword.value.trim() } : {}
    const data = await request.get('/platform/tenants', { params })
    rows.value = data.map((row) => ({ ...row, _loading: false }))
  } finally {
    loading.value = false
  }
}

async function toggle(row) {
  const next = row.status === 'active' ? 'disabled' : 'active'
  const action = next === 'disabled' ? '停用' : '启用'
  try {
    await ElMessageBox.confirm(
      `确定${action}商家「${row.name}」吗？${next === 'disabled' ? '停用后该店铺将无法登录和经营。' : ''}`,
      `${action}商家`,
      { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  row._loading = true
  try {
    await request.patch(`/platform/tenants/${row.id}/status`, { status: next })
    ElMessage.success(`已${action}「${row.name}」`)
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    row._loading = false
  }
}

onMounted(load)
</script>

<style scoped>
.tenant-name { display: flex; align-items: center; gap: 8px; font-weight: 600; color: #1f2937; }
</style>
