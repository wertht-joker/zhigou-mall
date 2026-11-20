<template>
  <div class="orders-page">
    <div class="page-card">
      <h3>📋 我的订单</h3>

      <el-tabs v-model="activeStatus" @tab-change="reload">
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
                  <div v-if="item.variant_spec" class="oi-spec">版本：{{ item.variant_spec }}</div>
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
              <div v-if="order.payment_method" class="pay-meta">
                <PaymentIcon :type="order.payment_method" :size="16" class="pay-inline" />
                {{ order.payment_method_label || order.payment_method }}
                <span v-if="order.paid_at"> · {{ formatTime(order.paid_at) }}</span>
              </div>
              <div v-if="order.logistics" class="logistics">
                <div class="logi-line">🚚 {{ order.logistics_company || '物流' }} · {{ order.tracking_no || order.logistics }}</div>
                <div class="logi-bottom">
                  <el-tag v-if="order.logistics_status" size="small" type="success">{{ order.logistics_status }}</el-tag>
                  <el-button link type="primary" size="small" @click="openLogistics(order)">查看物流 ›</el-button>
                </div>
              </div>
              <div
                v-if="order.status === '待付款' || order.status === '已发货'"
                class="order-actions"
              >
                <el-button v-if="order.status === '待付款'" type="primary" size="small" @click="openPay(order)">支付</el-button>
                <el-button v-if="order.status === '待付款'" size="small" @click="cancel(order)">取消</el-button>
                <el-button v-if="order.status === '已发货'" type="primary" size="small" @click="confirm(order)">确认收货</el-button>
              </div>
            </div>
          </div>
        </div>

        <el-empty v-if="!loading && orders.length === 0" description="暂无相关订单">
          <el-button type="primary" @click="$router.push('/')">去逛逛</el-button>
        </el-empty>

        <div v-if="total > pageSize" class="orders-pager">
          <el-pagination
            background
            layout="prev, pager, next"
            :total="total"
            :page-size="pageSize"
            :current-page="page"
            @current-change="onPageChange"
          />
        </div>
      </div>
    </div>

    <ReviewDialog v-model="reviewVisible" :order-item="reviewItem" @submitted="onReviewed" />

    <!-- 支付弹窗：选支付方式 → 生成支付单 → 模拟网关确认 -->
    <el-dialog v-model="payVisible" title="订单支付" width="460px" @closed="resetPay">
      <template v-if="!payPayment">
        <div class="pay-total">
          应付金额 <span class="price">¥{{ payingOrder?.total_amount }}</span>
        </div>
        <div class="pay-methods">
          <div
            v-for="m in payMethods"
            :key="m.value"
            class="pay-method"
            :class="{ active: payMethod === m.value }"
            @click="payMethod = m.value"
          >
            <PaymentIcon :type="m.value" :size="26" />
            <span>{{ m.label }}</span>
          </div>
        </div>
        <el-button
          type="primary"
          style="width: 100%"
          :loading="creatingPayment"
          @click="createPayment"
        >去支付</el-button>
      </template>
      <template v-else>
        <div class="pay-created">
          <div class="pc-title">支付单已创建</div>
          <div class="pc-line">支付单号：{{ payPayment.payment_no }}</div>
          <div class="pc-line">支付方式：{{ payPayment.method_label }}</div>
          <div class="pc-amount price">¥{{ payPayment.amount }}</div>
          <div class="pc-tip">演示环境：点击下方按钮模拟支付网关回调成功</div>
        </div>
        <el-button
          type="primary"
          style="width: 100%"
          :loading="confirmingPayment"
          @click="confirmPayment"
        >模拟支付成功</el-button>
        <el-button text style="width: 100%; margin: 8px 0 0" @click="payVisible = false">稍后支付</el-button>
      </template>
    </el-dialog>

    <!-- 物流轨迹 -->
    <el-drawer v-model="logisticsVisible" title="物流详情" size="420px">
      <template v-if="logisticsOrder">
        <div class="lg-card">
          <div class="lg-company">{{ logisticsOrder.logistics_company || '物流' }}</div>
          <div class="lg-tracking">运单号：{{ logisticsOrder.tracking_no || logisticsOrder.logistics }}</div>
          <div v-if="logisticsOrder.estimated_delivery_at" class="lg-eta">
            预计送达：{{ formatTime(logisticsOrder.estimated_delivery_at) }}
          </div>
          <el-tag v-if="logisticsOrder.logistics_status" type="success" size="small">
            {{ logisticsOrder.logistics_status }}
          </el-tag>
        </div>
        <el-timeline v-if="logisticsOrder.logistics_events?.length" class="lg-timeline">
          <el-timeline-item
            v-for="(event, index) in logisticsOrder.logistics_events"
            :key="index"
            :timestamp="formatTime(event.occurred_at)"
            :type="index === 0 ? 'primary' : ''"
            placement="top"
          >
            <div class="lg-event-status">{{ event.status }}</div>
            <div class="lg-event-desc">{{ event.description }}</div>
            <div class="lg-event-loc">{{ event.location }}</div>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="暂无物流轨迹" :image-size="70" />
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '../api'
import ReviewDialog from '../components/ReviewDialog.vue'
import PaymentIcon from '../components/PaymentIcon.vue'

const activeStatus = ref('')
const orders = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = 10
const total = ref(0)
// 可评价的订单明细 ID 集合（本人已完成订单中未评价的商品）
const reviewableIds = ref(new Set())
const reviewVisible = ref(false)
const reviewItem = ref(null)
const logisticsVisible = ref(false)
const logisticsOrder = ref(null)

// 支付弹窗状态
const payVisible = ref(false)
const payingOrder = ref(null)
const payMethod = ref('alipay')
const payPayment = ref(null)
const creatingPayment = ref(false)
const confirmingPayment = ref(false)
const payMethods = [
  { value: 'alipay', label: '支付宝' },
  { value: 'wechat', label: '微信支付' },
  { value: 'unionpay', label: '银联' },
]

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

function openLogistics(order) {
  logisticsOrder.value = order
  logisticsVisible.value = true
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
    const data = await request.get('/orders', {
      params: {
        status: activeStatus.value || undefined,
        page: page.value,
        page_size: pageSize,
      },
    })
    orders.value = data.items || []
    total.value = data.total || 0
  } catch (e) {
    ElMessage.error(e.message)
    orders.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function reload() {
  page.value = 1
  loadOrders()
}

function onPageChange(next) {
  page.value = next
  loadOrders()
}

function openPay(order) {
  payingOrder.value = order
  payMethod.value = 'alipay'
  payPayment.value = null
  payVisible.value = true
}

function resetPay() {
  payPayment.value = null
  creatingPayment.value = false
  confirmingPayment.value = false
}

async function createPayment() {
  creatingPayment.value = true
  try {
    payPayment.value = await request.post(
      `/orders/${payingOrder.value.id}/payments`,
      { method: payMethod.value },
    )
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    creatingPayment.value = false
  }
}

async function confirmPayment() {
  confirmingPayment.value = true
  try {
    await request.post(`/payments/${payPayment.value.payment_no}/confirm`)
    ElMessage.success('支付成功，商家将尽快发货')
    payVisible.value = false
    loadOrders()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    confirmingPayment.value = false
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
.orders-pager { display: flex; justify-content: center; margin-top: 18px; }
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
.oi-spec {
  display: inline-block; margin-top: 4px; padding: 1px 8px;
  font-size: 12px; color: #666; background: #f5f5f7; border-radius: 999px;
}
.oi-price { font-size: 12px; color: #999; margin-top: 4px; }
.oi-info { flex: 1; }

.order-side {
  width: 272px; border-left: 1px solid #f1f1f1; margin-left: 20px; padding-left: 22px;
  display: flex; flex-direction: column; gap: 12px; justify-content: center;
}
.order-total { font-size: 13px; color: #888; display: flex; align-items: baseline; gap: 6px; }
.order-total .price { font-size: 22px; font-weight: 800; }
.order-cut {
  align-self: flex-start; padding: 2px 9px; border-radius: 999px;
  font-size: 12px; color: #e1251b; background: #fff1f0; border: 1px solid #ffd8d3;
}
.order-cut b { font-weight: 600; }
.pay-meta {
  font-size: 12px; color: #8a8f99; display: flex; align-items: center;
  flex-wrap: wrap; gap: 5px;
}
.pay-inline { vertical-align: -3px; }
.logistics {
  margin-top: 2px; padding: 10px 12px; border-radius: 10px;
  background: #f8fafc; border: 1px solid #eef2f7; font-size: 12px;
}
.logi-line { font-weight: 600; color: #334155; line-height: 1.6; word-break: break-all; }
.logi-bottom {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px; margin-top: 8px;
}
.lg-card { padding: 16px; border-radius: 14px; background: #f7f9fc; margin-bottom: 20px; }
.lg-company { font-size: 17px; font-weight: 800; color: #0f172a; }
.lg-tracking { margin-top: 6px; font-size: 13px; color: #56607a; }
.lg-eta { margin: 6px 0 10px; font-size: 13px; color: #1d4ed8; }
.lg-timeline { padding-left: 4px; }
.lg-event-status { font-weight: 700; color: #0f172a; }
.lg-event-desc { margin-top: 4px; font-size: 13px; color: #4b5563; line-height: 1.6; }
.lg-event-loc { margin-top: 2px; font-size: 12px; color: #9ca3af; }
.order-actions {
  display: flex; gap: 10px; padding-top: 12px; border-top: 1px dashed #eef0f3;
}
@media (max-width: 860px) {
  .order-body { flex-direction: column; }
  .order-side {
    width: auto; margin: 14px 0 0; padding: 14px 0 0;
    border-left: none; border-top: 1px solid #f1f1f1;
  }
}

/* ===== 支付弹窗 ===== */
.pay-total { font-size: 14px; color: #666; margin-bottom: 16px; }
.pay-total .price { font-size: 26px; margin-left: 6px; }
.pay-methods { display: flex; gap: 10px; margin-bottom: 18px; }
.pay-method {
  flex: 1; display: flex; align-items: center; justify-content: center; gap: 6px;
  padding: 12px 8px; border: 1.5px solid #eee; border-radius: 12px;
  font-size: 13px; cursor: pointer; transition: all .2s ease;
}
.pay-method:hover { border-color: #ffb4a8; }
.pay-method.active {
  border-color: var(--brand); background: var(--brand-soft);
  box-shadow: 0 6px 16px rgba(255, 77, 79, .14);
}
.pm-icon { font-size: 17px; }
.pay-created { text-align: center; padding: 8px 0 18px; }
.pc-title { font-size: 17px; font-weight: 700; margin-bottom: 12px; }
.pc-line { font-size: 13px; color: #666; margin-top: 6px; }
.pc-amount { font-size: 30px; margin: 14px 0 8px; }
.pc-tip { font-size: 12px; color: #999; }
</style>
