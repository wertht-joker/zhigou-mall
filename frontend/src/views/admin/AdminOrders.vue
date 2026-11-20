<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h3>订单发货</h3>
        <p>处理本店订单发货、物流轨迹与签收进度</p>
      </div>
      <el-radio-group v-model="statusFilter">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button value="待发货">待发货</el-radio-button>
        <el-radio-button value="已发货">已发货</el-radio-button>
        <el-radio-button value="已完成">已完成</el-radio-button>
      </el-radio-group>
    </div>

    <div class="stat-grid">
      <div class="stat-card warn">
        <div class="stat-label">待发货</div>
        <div class="stat-value">{{ stats.pending }}</div>
        <div class="stat-hint">需要尽快处理</div>
      </div>
      <div class="stat-card primary">
        <div class="stat-label">已发货</div>
        <div class="stat-value">{{ stats.shipped }}</div>
        <div class="stat-hint">可继续推进物流</div>
      </div>
      <div class="stat-card success">
        <div class="stat-label">已完成</div>
        <div class="stat-value">{{ stats.done }}</div>
        <div class="stat-hint">顾客已确认收货</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">本店订单金额</div>
        <div class="stat-value small">¥{{ stats.amount }}</div>
        <div class="stat-hint">共 {{ orders.length }} 笔订单</div>
      </div>
    </div>

    <div class="table-card">
      <el-table :data="visibleOrders" v-loading="loading" stripe>
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
      <el-table-column label="物流" width="210">
        <template #default="{ row }">
          <div v-if="row.logistics_company || row.tracking_no">
            <div class="logi-company">{{ row.logistics_company || '快递' }} · {{ row.tracking_no }}</div>
            <el-tag v-if="row.logistics_status" size="small" type="success">
              {{ row.logistics_status }}
            </el-tag>
          </div>
          <span v-else class="muted">{{ row.logistics || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button v-if="row.status === '待发货'" type="primary" size="small" @click="openShip(row)">
            发货
          </el-button>
          <el-button
            v-else-if="row.status === '已发货' || (row.status === '已完成' && row.logistics)"
            size="small"
            :type="row.status === '已发货' ? 'primary' : 'default'"
            :plain="row.status === '已发货'"
            @click="openLogistics(row)"
          >
            {{ row.status === '已发货' ? '更新物流' : '查看物流' }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && visibleOrders.length === 0" description="暂无相关订单" />
    </div>

    <!-- 发货弹窗 -->
    <el-dialog v-model="shipDialog" title="订单发货" width="460px">
      <p style="margin-bottom:14px;color:#666">订单号：{{ shipping?.order_no }}</p>
      <el-form label-width="80px">
        <el-form-item label="物流公司">
          <el-select v-model="logisticsCompany" style="width: 100%">
            <el-option v-for="c in companies" :key="c" :label="c" :value="c" />
          </el-select>
        </el-form-item>
        <el-form-item label="运单号">
          <el-input v-model="trackingNo" placeholder="请输入快递运单号" />
        </el-form-item>
      </el-form>
      <div class="ship-tip">发货后系统会自动生成物流轨迹，顾客可在订单详情查看。</div>
      <template #footer>
        <el-button @click="shipDialog = false">取消</el-button>
        <el-button type="primary" :loading="shippingSubmitting" @click="ship">确认发货</el-button>
      </template>
    </el-dialog>

    <!-- 物流管理 -->
    <el-drawer v-model="logisticsDrawer" title="物流管理" size="450px">
      <template v-if="logisticsRow">
        <div class="lg-summary">
          <div class="lg-company">{{ logisticsRow.logistics_company || '快递' }}</div>
          <div class="lg-tracking">运单号：{{ logisticsRow.tracking_no || logisticsRow.logistics }}</div>
          <div v-if="logisticsRow.estimated_delivery_at" class="lg-eta">
            预计送达：{{ formatTime(logisticsRow.estimated_delivery_at) }}
          </div>
          <el-tag v-if="logisticsRow.logistics_status" type="success" size="small">
            {{ logisticsRow.logistics_status }}
          </el-tag>
        </div>
        <div v-if="logisticsRow.status === '已发货'" class="lg-hint">
          选择下一物流节点提交后，顾客端「查看物流」会同步展示最新轨迹。
        </div>

        <el-timeline v-if="logisticsRow.logistics_events?.length" class="lg-timeline">
          <el-timeline-item
            v-for="(event, index) in logisticsRow.logistics_events"
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

        <div v-if="logisticsRow.status === '已发货' && nextStatuses.length" class="lg-form">
          <div class="lg-form-title">推进物流状态</div>
          <el-form label-width="64px">
            <el-form-item label="状态">
              <el-select v-model="logiStatus" style="width: 100%">
                <el-option v-for="s in nextStatuses" :key="s" :label="s" :value="s" />
              </el-select>
            </el-form-item>
            <el-form-item label="说明">
              <el-input v-model="logiDesc" placeholder="可选，留空使用系统默认说明" />
            </el-form-item>
            <el-form-item label="位置">
              <el-input v-model="logiLocation" placeholder="可选，如：杭州转运中心" />
            </el-form-item>
          </el-form>
          <el-button type="primary" style="width: 100%" :loading="logiSubmitting" @click="updateLogistics">
            提交物流更新
          </el-button>
        </div>
        <el-alert
          v-else-if="logisticsRow.status === '已发货'"
          title="物流已签收，等待顾客确认收货"
          type="success"
          :closable="false"
        />
        <el-alert
          v-else
          title="订单已完成，物流轨迹仅供查看"
          type="info"
          :closable="false"
        />
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '../../api'

const orders = ref([])
const loading = ref(false)
const statusFilter = ref('')

const visibleOrders = computed(() =>
  statusFilter.value
    ? orders.value.filter((o) => o.status === statusFilter.value)
    : orders.value
)

const stats = computed(() => ({
  pending: orders.value.filter((o) => o.status === '待发货').length,
  shipped: orders.value.filter((o) => o.status === '已发货').length,
  done: orders.value.filter((o) => o.status === '已完成').length,
  amount: orders.value
    .reduce((sum, o) => sum + Number(o.total_amount || 0), 0)
    .toFixed(2),
}))
const shipDialog = ref(false)
const shipping = ref(null)
const logisticsCompany = ref('顺丰速运')
const trackingNo = ref('')
const shippingSubmitting = ref(false)
const companies = ['顺丰速运', '京东物流', '中通快递', '圆通速递', '韵达快递', '邮政EMS']

const LOGISTICS_FLOW = ['已发货', '已揽收', '运输中', '派送中', '已签收']
const logisticsDrawer = ref(false)
const logisticsRow = ref(null)
const logiStatus = ref('')
const logiDesc = ref('')
const logiLocation = ref('')
const logiSubmitting = ref(false)

const nextStatuses = computed(() => {
  const current = logisticsRow.value?.logistics_status || '已发货'
  const index = LOGISTICS_FLOW.indexOf(current)
  if (index < 0) return []
  return LOGISTICS_FLOW.slice(index + 1)
})

function formatTime(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 19)
}

function openLogistics(row) {
  logisticsRow.value = row
  logiStatus.value = ''
  logiDesc.value = ''
  logiLocation.value = ''
  logisticsDrawer.value = true
  // 默认选中下一个状态
  const current = row.logistics_status || '已发货'
  const index = LOGISTICS_FLOW.indexOf(current)
  logiStatus.value = LOGISTICS_FLOW[index + 1] || ''
}

async function updateLogistics() {
  if (!logiStatus.value) return ElMessage.warning('请选择物流状态')
  logiSubmitting.value = true
  try {
    const updated = await request.post(
      `/merchant/orders/${logisticsRow.value.id}/logistics-events`,
      {
        status: logiStatus.value,
        description: logiDesc.value.trim(),
        location: logiLocation.value.trim(),
      }
    )
    const index = orders.value.findIndex((o) => o.id === updated.id)
    if (index >= 0) orders.value[index] = updated
    logisticsRow.value = updated
    logiDesc.value = ''
    logiLocation.value = ''
    const current = updated.logistics_status || '已发货'
    const nextIndex = LOGISTICS_FLOW.indexOf(current) + 1
    logiStatus.value = LOGISTICS_FLOW[nextIndex] || ''
    ElMessage.success(`物流已更新为「${current}」`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    logiSubmitting.value = false
  }
}

async function load() {
  loading.value = true
  try {
    orders.value = await request.get('/merchant/orders')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function openShip(row) {
  shipping.value = row
  logisticsCompany.value = '顺丰速运'
  trackingNo.value = ''
  shipDialog.value = true
}

async function ship() {
  if (!trackingNo.value.trim()) return ElMessage.warning('请填写物流单号')
  shippingSubmitting.value = true
  try {
    await request.post(`/merchant/orders/${shipping.value.id}/ship`, {
      logistics_company: logisticsCompany.value,
      tracking_no: trackingNo.value.trim(),
    })
    ElMessage.success('发货成功')
    shipDialog.value = false
    load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    shippingSubmitting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.page { padding: 0; }
.page-header { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 18px; gap: 16px; }
.page-header h3 { font-size: 21px; color: #0f172a; letter-spacing: -.02em; }
.page-header p { margin-top: 5px; font-size: 12.5px; color: #8a91a0; }
.stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 16px; }
.stat-card {
  background: #fff; border-radius: 16px; padding: 16px 18px;
  border: 1px solid rgba(23, 24, 28, .06);
  box-shadow: 0 6px 18px rgba(15, 23, 42, .04);
}
.stat-label { font-size: 12px; color: #8a91a0; }
.stat-value { margin-top: 6px; font-size: 26px; font-weight: 800; color: #0f172a; letter-spacing: -.03em; }
.stat-value.small { font-size: 21px; }
.stat-hint { margin-top: 4px; font-size: 11px; color: #a3aab7; }
.stat-card.warn .stat-value { color: #f59e0b; }
.stat-card.primary .stat-value { color: #2563eb; }
.stat-card.success .stat-value { color: #10b981; }
.table-card {
  background: #fff; border-radius: 16px; padding: 6px;
  border: 1px solid rgba(23, 24, 28, .06);
  box-shadow: 0 8px 24px rgba(15, 23, 42, .05);
}
.table-card :deep(.el-table) { border-radius: 12px; }
.table-card :deep(.el-table th.el-table__cell) {
  background: #f8fafc; color: #6b7280; font-weight: 600;
}
.item-line { line-height: 1.8; font-size: 13px; }
.logi-company { font-size: 13px; color: #1f2937; margin-bottom: 4px; }
.muted { color: #98a1b3; font-size: 12px; }
.ship-tip { margin-top: 6px; font-size: 12px; color: #7c8598; line-height: 1.6; }
.lg-summary { padding: 16px; border-radius: 14px; background: #f7f9fc; margin-bottom: 20px; }
.lg-company { font-size: 17px; font-weight: 800; color: #0f172a; }
.lg-tracking { margin-top: 6px; font-size: 13px; color: #56607a; }
.lg-eta { margin: 6px 0 10px; font-size: 13px; color: #1d4ed8; }
.lg-hint {
  margin: -8px 0 18px; padding: 10px 12px; border-radius: 10px;
  background: #fff8ec; color: #9a6700; font-size: 12px; line-height: 1.6;
}
.lg-timeline { padding-left: 4px; }
.lg-event-status { font-weight: 700; color: #0f172a; }
.lg-event-desc { margin-top: 4px; font-size: 13px; color: #4b5563; line-height: 1.6; }
.lg-event-loc { margin-top: 2px; font-size: 12px; color: #9ca3af; }
.lg-form { margin-top: 18px; padding-top: 16px; border-top: 1px solid #eef1f6; }
.lg-form-title { font-size: 14px; font-weight: 700; color: #0f172a; margin-bottom: 14px; }
</style>
