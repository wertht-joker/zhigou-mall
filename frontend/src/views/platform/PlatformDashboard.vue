<template>
  <div class="pf-page" v-loading="loading">
    <div class="pf-head">
      <div>
        <div class="pf-title">平台概览</div>
        <div class="pf-sub">全平台商家、商品与交易的实时汇总</div>
      </div>
      <div class="pf-toolbar">
        <el-button @click="$router.push('/platform/tenants')">商家管理</el-button>
        <el-button type="primary" @click="$router.push('/platform/orders')">查看全部订单</el-button>
      </div>
    </div>

    <div class="pf-grid">
      <div class="pf-stat">
        <div class="pf-stat-label">商家总数</div>
        <div class="pf-stat-value">{{ data.tenants.total }}</div>
        <div class="pf-stat-hint">{{ data.tenants.active }} 家营业中</div>
      </div>
      <div class="pf-stat">
        <div class="pf-stat-label">平台商品</div>
        <div class="pf-stat-value">{{ data.products.total }}</div>
        <div class="pf-stat-hint">{{ data.products.on_sale }} 件在售</div>
      </div>
      <div class="pf-stat">
        <div class="pf-stat-label">平台订单</div>
        <div class="pf-stat-value">{{ data.orders.total }}</div>
        <div class="pf-stat-hint">今日新增 {{ data.orders.today }} 单</div>
      </div>
      <div class="pf-stat">
        <div class="pf-stat-label">累计成交额</div>
        <div class="pf-stat-value">¥{{ money(data.gmv) }}</div>
        <div class="pf-stat-hint">今日 ¥{{ money(data.today_gmv) }}</div>
      </div>
    </div>

    <div class="pf-card trend-card">
      <div class="panel-title">近 7 天成交趋势</div>
      <div class="trend-chart">
        <div v-for="day in data.trend" :key="day.date" class="trend-col">
          <div class="bar-area">
            <div
              class="bar"
              :style="{ height: barHeight(day.gmv) }"
              :title="`${day.date}：${day.orders} 单 / ¥${money(day.gmv)}`"
            ></div>
          </div>
          <div class="bar-value">¥{{ compactMoney(day.gmv) }}</div>
          <div class="bar-date">{{ day.date }}</div>
        </div>
      </div>
    </div>

    <div class="dashboard-row">
      <div class="pf-card status-panel">
        <div class="panel-title">订单状态分布</div>
        <div v-for="s in statusRows" :key="s.name" class="status-row">
          <div class="status-line">
            <span>{{ s.name }}</span>
            <span class="status-count">{{ s.count }} 单</span>
          </div>
          <el-progress
            :percentage="s.percentage"
            :stroke-width="8"
            :show-text="false"
            :color="s.color"
          />
        </div>
        <el-empty v-if="!data.orders.total" description="暂无订单" :image-size="70" />
      </div>

      <div class="pf-card">
        <div class="panel-title">最近订单</div>
        <el-table :data="data.recent_orders" size="small" :show-header="true">
          <el-table-column prop="order_no" label="订单号" min-width="160" />
          <el-table-column prop="username" label="顾客" width="90" />
          <el-table-column label="金额" width="100">
            <template #default="{ row }">¥{{ money(row.total_amount) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="statusType(row.status)">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="下单时间" width="120">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!data.recent_orders.length" description="暂无订单" :image-size="70" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import request from '../../api'

const loading = ref(false)
const data = ref({
  tenants: { total: 0, active: 0 },
  customers: 0,
  products: { total: 0, on_sale: 0 },
  orders: { total: 0, today: 0, by_status: {} },
  gmv: 0,
  today_gmv: 0,
  trend: [],
  recent_orders: [],
})

const STATUS_META = [
  { name: '待付款', color: '#f59e0b' },
  { name: '待发货', color: '#3b82f6' },
  { name: '已发货', color: '#8b5cf6' },
  { name: '已完成', color: '#10b981' },
  { name: '已取消', color: '#94a3b8' },
]

const statusRows = computed(() => {
  const total = data.value.orders.total || 1
  return STATUS_META.map((s) => {
    const count = data.value.orders.by_status[s.name] || 0
    return { ...s, count, percentage: Math.round((count / total) * 100) }
  })
})

function statusType(status) {
  return {
    待付款: 'warning',
    待发货: 'primary',
    已发货: 'success',
    已完成: 'success',
    已取消: 'info',
  }[status] || 'info'
}

function money(value) {
  return Number(value || 0).toFixed(2)
}

function compactMoney(value) {
  const n = Number(value || 0)
  if (n >= 10000) return `${(n / 10000).toFixed(1)}w`
  return n.toFixed(0)
}

const maxTrend = computed(() =>
  Math.max(...(data.value.trend || []).map((d) => Number(d.gmv || 0)), 1)
)

function barHeight(value) {
  const ratio = Number(value || 0) / maxTrend.value
  return ratio > 0 ? `${Math.max(6, ratio * 100)}%` : '3px'
}

function formatDate(value) {
  if (!value) return '-'
  return value.slice(0, 16).replace('T', ' ')
}

async function load() {
  loading.value = true
  try {
    data.value = await request.get('/platform/overview')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.dashboard-row {
  display: grid; grid-template-columns: minmax(280px, 360px) minmax(0, 1fr); gap: 16px;
}
.panel-title { font-size: 15px; font-weight: 700; color: #0f172a; margin-bottom: 16px; }
.trend-card { padding-bottom: 16px; }
.trend-chart { display: flex; align-items: flex-end; gap: 18px; height: 190px; padding: 0 6px; }
.trend-col { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; }
.bar-area { flex: 1; width: 100%; display: flex; align-items: flex-end; justify-content: center; }
.bar {
  width: 60%; max-width: 54px; border-radius: 8px 8px 4px 4px;
  background: linear-gradient(180deg, #60a5fa 0%, #2f6bff 100%);
  transition: height .4s ease; min-height: 3px;
}
.bar-value { margin-top: 8px; font-size: 11px; color: #56607a; }
.bar-date { margin-top: 2px; font-size: 11px; color: #98a1b3; }
.status-row { margin-bottom: 14px; }
.status-line { display: flex; justify-content: space-between; font-size: 13px; color: #56607a; margin-bottom: 6px; }
.status-count { color: #0f172a; font-weight: 600; }
@media (max-width: 1100px) {
  .dashboard-row { grid-template-columns: 1fr; }
}
</style>
