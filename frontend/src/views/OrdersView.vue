<template>
  <div class="orders-page">
    <div class="page-card">
      <h3>📋 我的订单</h3>

      <el-tabs v-model="activeStatus" @tab-change="loadOrders">
        <el-tab-pane v-for="t in statusTabs" :key="t.value" :label="t.label" :name="t.value" />
      </el-tabs>

      <div v-loading="loading">
        <div v-for="order in orders" :key="order.id" class="order-card">
          <div class="order-head">
            <span class="order-no">订单号：{{ order.order_no }}</span>
            <span class="order-time">{{ formatTime(order.created_at) }}</span>
            <el-tag :type="statusTagType(order.status)" size="small">{{ order.status }}</el-tag>
          </div>

          <div class="order-body">
            <div class="order-items">
              <div v-for="item in order.items" :key="item.id" class="order-item">
                <div class="oi-pic">
                  <img v-if="item.image_url" :src="item.image_url" :alt="item.product_name" />
                  <span v-else>{{ item.image }}</span>
                </div>
                <div class="oi-info">
                  <div class="oi-name">{{ item.product_name }}</div>
                  <div class="oi-price">¥{{ item.price }} × {{ item.quantity }}</div>
                </div>
                <el-button
                  v-if="canReview(order, item)"
                  size="small"
                  type="warning"
                  plain
                  @click="openReview(item)"
                >评价</el-button>
                <el-tag v-else-if="order.status === '已完成'" size="small" type="info">已评价</el-tag>
              </div>
            </div>
            <div class="order-side">
              <div v-if="order.discount_amount > 0" class="order-cut">券已抵扣 <b>-¥{{ order.discount_amount }}</b></div>
              <div class="order-total">实付 <span class="price">¥{{ order.total_amount }}</span></div>
              <div v-if="order.logistics" class="logistics">🚚 {{ order.logistics }}</div>
              <div class="order-actions">
                <el-button v-if="order.status === '待付款'" type="primary" size="small" @click="pay(order)">支付</el-button>
                <el-button v-if="order.status === '待付款'" size="small" @click="cancel(order)">取消</el-button>
                <el-button v-if="order.status === '已发货'" type="primary" size="small" @click="confirm(order)">确认收货</el-button>
              </div>
            </div>
          </div>
        </div>

        <el-empty v-if="!loading && orders.length === 0" description="暂无相关订单">
          <el-button type="primary" @click="$router.push('/')">去逛逛</el-button>
        </el-empty>
      </div>
    </div>

    <ReviewDialog v-model="reviewVisible" :order-item="reviewItem" @submitted="onReviewed" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '../api'
import ReviewDialog from '../components/ReviewDialog.vue'

const activeStatus = ref('')
const orders = ref([])
const loading = ref(false)
// 可评价的订单明细 ID 集合（本人已完成订单中未评价的商品）
const reviewableIds = ref(new Set())
const reviewVisible = ref(false)
const reviewItem = ref(null)

const statusTabs = [
  { label: '全部', value: '' },
  { label: '待付款', value: '待付款' },
  { label: '待发货', value: '待发货' },
  { label: '已发货', value: '已发货' },
  { label: '已完成', value: '已完成' },
]

function statusTagType(status) {
  return { 待付款: 'warning', 待发货: 'primary', 已发货: 'success', 已完成: 'info', 已取消: 'danger' }[status] || 'info'
}

function formatTime(t) {
  return t ? String(t).replace('T', ' ').slice(0, 19) : ''
}

function canReview(order, item) {
  return order.status === '已完成' && reviewableIds.value.has(item.id)
}

function openReview(item) {
  reviewItem.value = item
  reviewVisible.value = true
}

async function onReviewed() {
  await Promise.all([loadReviewable(), loadOrders()])
}

async function loadReviewable() {
  try {
    const list = await request.get('/reviews/my/reviewable')
    reviewableIds.value = new Set(list.map((i) => i.order_item_id))
  } catch {
    reviewableIds.value = new Set()
  }
}

async function loadOrders() {
  loading.value = true
  try {
    orders.value = await request.get('/orders', {
      params: { status: activeStatus.value || undefined },
    })
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function pay(order) {
  try {
    await request.post(`/orders/${order.id}/pay`)
    ElMessage.success('支付成功，商家将尽快发货')
    loadOrders()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function cancel(order) {
  try {
    await request.post(`/orders/${order.id}/cancel`)
    ElMessage.success('订单已取消')
    loadOrders()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function confirm(order) {
  try {
    await request.post(`/orders/${order.id}/confirm`)
    ElMessage.success('确认收货成功，记得评价哦')
    await Promise.all([loadOrders(), loadReviewable()])
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(() => {
  loadOrders()
  loadReviewable()
})
</script>

<style scoped>
.page-card { background: #fff; border-radius: 8px; padding: 20px 24px; }
.page-card > h3 { margin-bottom: 8px; }

.order-card { border: 1px solid #f0f0f0; border-radius: 8px; margin-bottom: 14px; overflow: hidden; }
.order-head {
  background: #fafafa; padding: 10px 16px; display: flex; gap: 16px; align-items: center;
  font-size: 13px;
}
.order-no { color: #666; }
.order-time { color: #bbb; flex: 1; }

.order-body { display: flex; padding: 16px; }
.order-items { flex: 1; }
.order-item { display: flex; gap: 12px; align-items: center; padding: 6px 0; }
.oi-pic {
  width: 52px; height: 52px; border-radius: 6px; font-size: 28px; overflow: hidden;
  background: #faf6f5; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.oi-pic img { width: 100%; height: 100%; object-fit: cover; }
.oi-name { font-size: 14px; }
.oi-price { font-size: 12px; color: #999; margin-top: 4px; }
.oi-info { flex: 1; }

.order-side {
  width: 240px; border-left: 1px solid #f5f5f5; padding-left: 16px;
  display: flex; flex-direction: column; gap: 10px; justify-content: center;
}
.order-total { font-size: 14px; color: #666; }
.order-total .price { font-size: 18px; }
.order-cut { font-size: 12px; color: #ff6a00; }
.order-cut b { font-weight: 600; }
.logistics { font-size: 12px; color: #999; }
.order-actions { display: flex; gap: 8px; }
</style>
