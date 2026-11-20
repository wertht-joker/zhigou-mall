<template>
  <div class="page">
    <div class="page-header">
      <h3>🧾 售后处理（本店商品）</h3>
      <el-radio-group v-model="statusFilter" @change="load">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button value="待商家处理">待商家处理</el-radio-button>
        <el-radio-button value="已完成">已完成</el-radio-button>
        <el-radio-button value="已驳回">已驳回</el-radio-button>
      </el-radio-group>
    </div>

    <el-table :data="tickets" v-loading="loading" border stripe>
      <el-table-column prop="ticket_no" label="工单号" width="200" />
      <el-table-column prop="order_no" label="订单号" width="190" />
      <el-table-column prop="kind" label="类型" width="80" />
      <el-table-column label="退款金额" width="110">
        <template #default="{ row }"><span class="price">¥{{ row.amount }}</span></template>
      </el-table-column>
      <el-table-column prop="reason" label="申请原因" min-width="200" show-overflow-tooltip />
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="申请时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <template v-if="row.status === '待商家处理'">
            <el-button type="primary" size="small" @click="review(row, true)">通过</el-button>
            <el-button type="danger" size="small" @click="review(row, false)">驳回</el-button>
          </template>
          <span v-else class="muted">已处理</span>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && tickets.length === 0" description="暂无售后工单" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../../api'

const tickets = ref([])
const loading = ref(false)
const statusFilter = ref('')

function statusType(status) {
  if (status === '待商家处理') return 'warning'
  if (status === '已完成') return 'success'
  if (status === '已驳回') return 'danger'
  return 'info'
}

function formatTime(value) {
  return value ? value.replace('T', ' ').slice(0, 19) : ''
}

async function load() {
  loading.value = true
  try {
    tickets.value = await request.get('/merchant/aftersale/tickets', {
      params: { status: statusFilter.value || undefined },
    })
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function review(row, approve) {
  const label = approve ? '通过' : '驳回'
  try {
    await ElMessageBox.confirm(
      `确定${label}售后单 ${row.ticket_no}（¥${row.amount}）吗？`,
      '售后审核',
      { type: 'warning', confirmButtonText: `确认${label}`, cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await request.post(
      `/merchant/aftersale/tickets/${row.id}/${approve ? 'approve' : 'reject'}`,
    )
    ElMessage.success(`已${label}`)
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(load)
</script>

<style scoped>
.page { padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.muted { color: #999; font-size: 13px; }
</style>
