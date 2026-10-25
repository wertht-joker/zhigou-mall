<template>
  <div class="page">
    <div class="page-header">
      <h3>🚚 订单管理（含本店商品的订单）</h3>
      <el-radio-group v-model="statusFilter" @change="load">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button value="待发货">待发货</el-radio-button>
        <el-radio-button value="已发货">已发货</el-radio-button>
        <el-radio-button value="已完成">已完成</el-radio-button>
      </el-radio-group>
    </div>

    <el-table :data="orders" v-loading="loading" border stripe>
      <el-table-column prop="order_no" label="订单号" width="180" />
      <el-table-column label="本店商品" min-width="220">
        <template #default="{ row }">
          <div v-for="item in row.items" :key="item.id" class="item-line">
            {{ item.image }} {{ item.product_name }} ×{{ item.quantity }}
            <span class="price">¥{{ item.price }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="本店金额" width="110">
        <template #default="{ row }"><span class="price">¥{{ row.total_amount }}</span></template>
      </el-table-column>
      <el-table-column prop="receiver_name" label="收货人" width="90" />
      <el-table-column prop="receiver_address" label="收货地址" min-width="180" show-overflow-tooltip />
      <el-table-column prop="status" label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === '待发货' ? 'warning' : row.status === '已发货' ? 'success' : 'info'">
            {{ row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="logistics" label="物流" width="170" show-overflow-tooltip />
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button v-if="row.status === '待发货'" type="primary" size="small" @click="openShip(row)">
            发货
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && orders.length === 0" description="暂无相关订单" />

    <!-- 发货弹窗 -->
    <el-dialog v-model="shipDialog" title="订单发货" width="420px">
      <p style="margin-bottom:12px;color:#666">订单号：{{ shipping?.order_no }}</p>
      <el-input v-model="logistics" placeholder="物流信息，如：顺丰速运 SF1234567890" />
      <template #footer>
        <el-button @click="shipDialog = false">取消</el-button>
        <el-button type="primary" @click="ship">确认发货</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '../../api'

const orders = ref([])
const loading = ref(false)
const statusFilter = ref('')
const shipDialog = ref(false)
const shipping = ref(null)
const logistics = ref('')

async function load() {
  loading.value = true
  try {
    orders.value = await request.get('/merchant/orders', {
      params: { status: statusFilter.value || undefined },
    })
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function openShip(row) {
  shipping.value = row
  logistics.value = ''
  shipDialog.value = true
}

async function ship() {
  if (!logistics.value.trim()) return ElMessage.warning('请填写物流信息')
  try {
    await request.post(`/merchant/orders/${shipping.value.id}/ship`, { logistics: logistics.value })
    ElMessage.success('发货成功')
    shipDialog.value = false
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
.item-line { line-height: 1.8; font-size: 13px; }
</style>
