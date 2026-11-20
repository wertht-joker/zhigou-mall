<template>
  <div class="pf-page">
    <div class="pf-head">
      <div>
        <div class="pf-title">订单监管</div>
        <div class="pf-sub">全平台订单总览（只读）；发货与售后仍由对应商家处理</div>
      </div>
      <div class="pf-toolbar">
        <el-radio-group v-model="status" @change="load">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="待付款">待付款</el-radio-button>
          <el-radio-button value="待发货">待发货</el-radio-button>
          <el-radio-button value="已发货">已发货</el-radio-button>
          <el-radio-button value="已完成">已完成</el-radio-button>
          <el-radio-button value="已取消">已取消</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <div class="pf-card">
      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="expand-box">
              <div v-for="item in row.items" :key="item.id" class="item-line">
                <span class="item-image">{{ item.image }}</span>
                <span class="item-name">{{ item.product_name }}</span>
                <span v-if="item.variant_spec" class="pf-muted">{{ item.variant_spec }}</span>
                <span class="pf-muted">×{{ item.quantity }}</span>
                <span class="pf-money">¥{{ item.price }}</span>
              </div>
              <div class="receiver">
                收货：{{ row.receiver_name }} {{ row.receiver_phone }} · {{ row.receiver_address }}
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="order_no" label="订单号" width="180" />
        <el-table-column prop="username" label="顾客" width="100" />
        <el-table-column label="商品" min-width="220">
          <template #default="{ row }">
            <div class="items-preview">
              {{ row.items.map((i) => `${i.product_name} ×${i.quantity}`).join(' / ') }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="110">
          <template #default="{ row }"><span class="pf-money">¥{{ row.total_amount }}</span></template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="支付方式" width="100">
          <template #default="{ row }">{{ row.payment_method_label || '—' }}</template>
        </el-table-column>
        <el-table-column label="下单时间" width="150">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && rows.length === 0" description="没有匹配的订单" />
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import request from '../../api'

const rows = ref([])
const loading = ref(false)
const status = ref('')

function statusType(value) {
  return {
    待付款: 'warning',
    待发货: 'primary',
    已发货: 'success',
    已完成: 'success',
    已取消: 'info',
  }[value] || 'info'
}

function formatDate(value) {
  if (!value) return '-'
  return value.slice(0, 16).replace('T', ' ')
}

async function load() {
  loading.value = true
  try {
    const params = status.value ? { status: status.value } : {}
    rows.value = await request.get('/platform/orders', { params })
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.items-preview { color: #4b5563; font-size: 13px; }
.expand-box { padding: 6px 18px 12px; }
.item-line {
  display: flex; align-items: center; gap: 10px;
  padding: 6px 0; border-bottom: 1px dashed #e5e7eb; font-size: 13px;
}
.item-image { font-size: 18px; }
.item-name { color: #1f2937; font-weight: 600; }
.receiver { margin-top: 10px; font-size: 12px; color: #7c8598; }
</style>
