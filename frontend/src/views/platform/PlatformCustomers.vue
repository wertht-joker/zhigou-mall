<template>
  <div class="pf-page">
    <div class="pf-head">
      <div>
        <div class="pf-title">用户管理</div>
        <div class="pf-sub">平台顾客账号与消费概况；账号安全策略由登录体系统一管理</div>
      </div>
      <div class="pf-toolbar">
        <el-input
          v-model="keyword"
          placeholder="搜索用户名"
          clearable
          style="width: 220px"
          @keyup.enter="load"
          @clear="load"
        />
        <el-button type="primary" @click="load">查询</el-button>
      </div>
    </div>

    <div class="pf-grid customer-stats">
      <div class="pf-stat">
        <div class="pf-stat-label">顾客总数</div>
        <div class="pf-stat-value">{{ rows.length }}</div>
        <div class="pf-stat-hint">当前筛选结果</div>
      </div>
      <div class="pf-stat">
        <div class="pf-stat-label">有成交顾客</div>
        <div class="pf-stat-value">{{ payingCount }}</div>
        <div class="pf-stat-hint">至少有一笔已付款订单</div>
      </div>
      <div class="pf-stat">
        <div class="pf-stat-label">累计消费</div>
        <div class="pf-stat-value">¥{{ money(totalSpent) }}</div>
        <div class="pf-stat-hint">已付款订单金额合计</div>
      </div>
      <div class="pf-stat">
        <div class="pf-stat-label">客单价</div>
        <div class="pf-stat-value">¥{{ money(avgSpent) }}</div>
        <div class="pf-stat-hint">累计消费 / 有成交顾客</div>
      </div>
    </div>

    <div class="pf-card">
      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="70" align="center" />
        <el-table-column label="用户名" min-width="160">
          <template #default="{ row }">👤 {{ row.username }}</template>
        </el-table-column>
        <el-table-column prop="order_count" label="下单数" width="90" align="center" />
        <el-table-column prop="paid_order_count" label="成交单" width="90" align="center" />
        <el-table-column label="累计消费" width="120">
          <template #default="{ row }"><span class="pf-money">¥{{ money(row.total_spent) }}</span></template>
        </el-table-column>
        <el-table-column label="最近下单" width="160">
          <template #default="{ row }">{{ formatDate(row.last_order_at) }}</template>
        </el-table-column>
        <el-table-column label="注册时间" width="160">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && rows.length === 0" description="没有匹配的顾客" />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import request from '../../api'

const rows = ref([])
const loading = ref(false)
const keyword = ref('')

const payingCount = computed(() => rows.value.filter((r) => r.paid_order_count > 0).length)
const totalSpent = computed(() => rows.value.reduce((sum, r) => sum + Number(r.total_spent || 0), 0))
const avgSpent = computed(() => (payingCount.value ? totalSpent.value / payingCount.value : 0))

function money(value) {
  return Number(value || 0).toFixed(2)
}

function formatDate(value) {
  if (!value) return '-'
  return value.slice(0, 16).replace('T', ' ')
}

async function load() {
  loading.value = true
  try {
    const params = keyword.value.trim() ? { keyword: keyword.value.trim() } : {}
    rows.value = await request.get('/platform/customers', { params })
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.customer-stats { margin-bottom: 0; }
</style>
