<template>
  <div class="pf-page" v-loading="loading">
    <div class="pf-head">
      <div>
        <div class="pf-title">智能洞察</div>
        <div class="pf-sub">把平台交易、库存、售后与知识库数据自动整理成可执行的运营建议</div>
      </div>
      <div class="pf-toolbar">
        <el-button @click="load">刷新洞察</el-button>
      </div>
    </div>

    <div class="brief-card">
      <div class="brief-head">
        <div>
          <div class="brief-kicker">TODAY · 运营简报</div>
          <div class="brief-title">今日经营脉搏</div>
        </div>
        <el-button class="copy-btn" size="small" @click="copyBrief">复制简报</el-button>
      </div>
      <div class="brief-text">{{ data.brief || '正在生成今日简报…' }}</div>
    </div>

    <div class="pf-grid">
      <div class="pf-stat">
        <div class="pf-stat-label">今日成交额</div>
        <div class="pf-stat-value">¥{{ money(data.pulse.today_gmv) }}</div>
        <div class="pf-stat-hint" :class="growthClass(data.pulse.gmv_growth)">
          环比 {{ growthText(data.pulse.gmv_growth) }}
        </div>
      </div>
      <div class="pf-stat">
        <div class="pf-stat-label">今日订单</div>
        <div class="pf-stat-value">{{ data.pulse.today_orders }}</div>
        <div class="pf-stat-hint" :class="growthClass(data.pulse.order_growth)">
          环比 {{ growthText(data.pulse.order_growth) }}
        </div>
      </div>
      <div class="pf-stat">
        <div class="pf-stat-label">待发货</div>
        <div class="pf-stat-value warn">{{ data.pulse.pending_ship }}</div>
        <div class="pf-stat-hint">
          <el-link type="primary" :underline="false" @click="$router.push('/platform/orders')">去处理订单 →</el-link>
        </div>
      </div>
      <div class="pf-stat">
        <div class="pf-stat-label">售后待处理</div>
        <div class="pf-stat-value" :class="{ danger: data.pulse.open_after_sales > 0 }">
          {{ data.pulse.open_after_sales }}
        </div>
        <div class="pf-stat-hint">涉及退款 / 补发 / 退货</div>
      </div>
    </div>

    <div class="insight-grid">
      <div class="pf-card">
        <div class="card-head">
          <div>
            <div class="card-title">库存预警</div>
            <div class="pf-muted">在售且库存 ≤ 10 的商品（{{ data.alerts.low_stock_total }} 个）</div>
          </div>
          <el-link type="primary" :underline="false" @click="$router.push('/platform/products')">商品监管 →</el-link>
        </div>
        <div v-for="p in data.alerts.low_stock" :key="p.id" class="list-row">
          <span class="row-icon">{{ p.image || '📦' }}</span>
          <div class="row-main">
            <div class="row-title">{{ p.name }}</div>
            <div class="pf-muted">{{ p.store_name }} · 已售 {{ p.sales }}</div>
          </div>
          <span class="stock-badge">剩 {{ p.stock }}</span>
        </div>
        <el-empty v-if="!data.alerts.low_stock.length" description="库存健康" :image-size="60" />
      </div>

      <div class="pf-card">
        <div class="card-head">
          <div>
            <div class="card-title">滞销商品</div>
            <div class="pf-muted">近 30 天无成交（{{ data.alerts.slow_moving_total }} 个）</div>
          </div>
          <el-link type="primary" :underline="false" @click="$router.push('/platform/products')">查看商品 →</el-link>
        </div>
        <div v-for="p in data.alerts.slow_moving" :key="p.id" class="list-row">
          <span class="row-icon">{{ p.image || '📦' }}</span>
          <div class="row-main">
            <div class="row-title">{{ p.name }}</div>
            <div class="pf-muted">{{ p.store_name }} · 库存 {{ p.stock }}</div>
          </div>
          <span class="slow-badge">30 天 0 单</span>
        </div>
        <el-empty v-if="!data.alerts.slow_moving.length" description="没有滞销商品" :image-size="60" />
      </div>
    </div>

    <div class="insight-grid">
      <div class="pf-card">
        <div class="card-head">
          <div>
            <div class="card-title">商家健康度</div>
            <div class="pf-muted">综合商品在售率、近 30 天成交与售后风险评分</div>
          </div>
          <el-link type="primary" :underline="false" @click="$router.push('/platform/tenants')">商家管理 →</el-link>
        </div>
        <el-table :data="data.merchant_health" size="small">
          <el-table-column label="商家" min-width="150">
            <template #default="{ row }">
              <div class="row-title">{{ row.name }}</div>
              <div class="pf-muted">{{ row.code }}</div>
            </template>
          </el-table-column>
          <el-table-column label="评分" width="80" align="center">
            <template #default="{ row }">
              <span class="score" :class="'grade-' + row.grade.toLowerCase()">{{ row.score }}</span>
            </template>
          </el-table-column>
          <el-table-column label="等级" width="70" align="center">
            <template #default="{ row }">
              <el-tag :type="gradeType(row.grade)" size="small">{{ row.grade }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="近 30 天" width="120">
            <template #default="{ row }">
              <div>{{ row.orders_30d }} 单</div>
              <div class="pf-muted">¥{{ money(row.gmv_30d) }}</div>
            </template>
          </el-table-column>
          <el-table-column label="风险" min-width="150">
            <template #default="{ row }">
              <div v-if="row.risks.length" class="risk-tags">
                <el-tag v-for="r in row.risks" :key="r" type="danger" size="small">{{ r }}</el-tag>
              </div>
              <el-tag v-else type="success" size="small">健康</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <div class="pf-card gap-card">
      <div class="card-head">
        <div>
          <div class="card-title">知识缺口闭环</div>
          <div class="pf-muted">
            AI 答不上来或被点踩的问题自动聚类，生成 FAQ 草稿并一键入库
          </div>
        </div>
        <div class="gap-tools">
          <el-select
            v-model="tenantFilter"
            size="small"
            placeholder="全部商家"
            style="width: 150px"
            @change="loadGaps"
          >
            <el-option label="全部商家" value="" />
            <el-option v-for="t in tenants" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
          <div class="gap-summary">
            <span class="gap-chip">坏例 {{ gapData.problem_events }}</span>
            <span class="gap-chip">聚类 {{ gapData.gap_count }}</span>
            <span class="gap-chip danger">点踩 {{ gapData.down_count }}</span>
            <span class="gap-chip warn">无结果 {{ gapData.no_hit_count }}</span>
          </div>
        </div>
      </div>

      <div v-loading="gapLoading">
        <div v-for="gap in gapData.gaps" :key="gap.id" class="gap-item">
          <div class="gap-main">
            <div class="gap-theme">{{ gap.theme }}</div>
            <div class="gap-meta">
              <el-tag size="small" type="info">{{ gap.tenant_name }}</el-tag>
              <el-tag v-for="c in gap.causes" :key="c" size="small" :type="causeType(c)">
                {{ c }}
              </el-tag>
              <span class="pf-muted">
                {{ gap.count }} 次
                <template v-if="gap.avg_faithfulness !== null && gap.avg_faithfulness !== undefined">
                  · 平均忠实度 {{ Math.round(gap.avg_faithfulness * 100) }}%
                </template>
              </span>
            </div>
            <div class="gap-queries">
              <span v-for="q in gap.queries" :key="q">「{{ q }}」</span>
            </div>
          </div>
          <el-button type="primary" plain size="small" @click="openDraft(gap)">
            生成 FAQ 草稿
          </el-button>
        </div>
      </div>
      <el-empty
        v-if="!gapLoading && !gapData.gaps.length"
        description="暂无知识缺口，客服质量良好"
        :image-size="60"
      />
    </div>

    <el-dialog v-model="draftVisible" title="FAQ 草稿" width="660px">
      <el-form label-width="80px">
        <el-form-item label="发布到">
          <el-tag type="info">{{ draftForm.tenant_name || '平台知识库' }}</el-tag>
        </el-form-item>
        <el-form-item label="文档标题">
          <el-input v-model="draftForm.title" maxlength="120" />
        </el-form-item>
        <el-form-item label="知识分类">
          <el-select v-model="draftForm.category_id" clearable placeholder="可选" style="width: 100%">
            <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="文档内容">
          <el-input v-model="draftForm.content" type="textarea" :rows="12" />
        </el-form-item>
      </el-form>
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="草稿只汇总问题与证据指针，标准答案请人工补充后再发布。"
      />
      <template #footer>
        <el-button @click="draftVisible = false">取消</el-button>
        <el-button type="primary" :loading="publishing" @click="publishDraft">
          发布到知识库
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="regressionVisible" title="FAQ 命中率回归" width="600px">
      <div class="reg-head">
        <div class="reg-rate" :class="{ low: regression.hit_rate < 0.6 }">
          {{ Math.round((regression.hit_rate || 0) * 100) }}%
        </div>
        <div>
          <div class="reg-title">Top-{{ regression.top_k }} 命中率</div>
          <div class="pf-muted">
            覆盖 {{ regression.total }} 个原问题 · MRR {{ regression.mrr }} ·
            文档 #{{ regression.document_id }}
          </div>
        </div>
      </div>
      <el-table :data="regression.details" size="small" max-height="300">
        <el-table-column prop="query" label="原问题" min-width="220" show-overflow-tooltip />
        <el-table-column label="命中" width="80">
          <template #default="{ row }">
            <el-tag :type="row.hit ? 'success' : 'danger'" size="small">
              {{ row.hit ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="rank" label="排名" width="70" />
        <el-table-column prop="score" label="分数" width="90" />
      </el-table>
      <el-alert
        v-if="regression.total && regression.hit_rate < 0.6"
        type="warning"
        :closable="false"
        show-icon
        title="命中率偏低：建议把原问题写进 FAQ 标题或正文，保存后重新检测。"
      />
      <template #footer>
        <el-button @click="regressionVisible = false">关闭</el-button>
        <el-button type="primary" plain :loading="regLoading" @click="recheckRegression">
          重新检测
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import request from '../../api'

const loading = ref(false)
const gapLoading = ref(false)
const data = ref({
  brief: '',
  pulse: {
    today_gmv: 0,
    today_orders: 0,
    gmv_growth: null,
    order_growth: null,
    pending_ship: 0,
    open_after_sales: 0,
  },
  alerts: { low_stock_total: 0, low_stock: [], slow_moving_total: 0, slow_moving: [] },
  merchant_health: [],
  knowledge_gaps: [],
})

const gapData = ref({
  window_days: 30,
  total_events: 0,
  problem_events: 0,
  gap_count: 0,
  down_count: 0,
  no_hit_count: 0,
  insufficient_count: 0,
  gaps: [],
})
const categories = ref([])
const tenants = ref([])
const tenantFilter = ref('')
const draftVisible = ref(false)
const publishing = ref(false)
const draftForm = ref({
  title: '', content: '', queries: [], category_id: null,
  tenant_id: null, tenant_name: '',
})
const regressionVisible = ref(false)
const regLoading = ref(false)
const regression = ref({
  document_id: null, tenant_id: null, top_k: 5,
  total: 0, hits: 0, hit_rate: 0, mrr: 0, details: [],
})

function money(value) {
  return Number(value || 0).toFixed(2)
}

function growthText(value) {
  return value === null || value === undefined ? '暂无基准' : `${value > 0 ? '+' : ''}${value}%`
}

function growthClass(value) {
  if (value === null || value === undefined) return 'muted'
  return value >= 0 ? 'up' : 'down'
}

function gradeType(grade) {
  return { A: 'success', B: 'warning', C: 'danger' }[grade] || 'info'
}

function formatDate(value) {
  if (!value) return '-'
  return value.slice(0, 16).replace('T', ' ')
}

function causeType(cause) {
  return {
    '顾客点踩': 'danger',
    '检索无结果': 'warning',
    '证据不足': 'warning',
    '忠实度偏低': 'info',
  }[cause] || 'info'
}

async function openDraft(gap) {
  try {
    const draft = await request.post('/platform/knowledge-gaps/draft', {
      queries: gap.queries,
      tenant_id: gap.tenant_id,
    })
    draftForm.value = {
      title: draft.title,
      content: draft.content,
      queries: draft.queries,
      category_id: null,
      tenant_id: gap.tenant_id,
      tenant_name: gap.tenant_name,
    }
    draftVisible.value = true
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function publishDraft() {
  if (!draftForm.value.title.trim() || !draftForm.value.content.trim()) {
    return ElMessage.warning('请填写文档标题和内容')
  }
  publishing.value = true
  try {
    const result = await request.post('/platform/knowledge-gaps/publish', {
      title: draftForm.value.title,
      content: draftForm.value.content,
      queries: draftForm.value.queries,
      category_id: draftForm.value.category_id,
      tenant_id: draftForm.value.tenant_id,
    })
    ElMessage.success(
      `已发布到「${draftForm.value.tenant_name || '平台'}」知识库，关闭 ${result.handled_events} 条缺口记录`
    )
    draftVisible.value = false
    if (result.regression) {
      regression.value = result.regression
      regressionVisible.value = true
    }
    await Promise.all([load(), loadGaps()])
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    publishing.value = false
  }
}

async function recheckRegression() {
  if (!regression.value.document_id) return
  regLoading.value = true
  try {
    regression.value = await request.get(
      `/platform/knowledge-gaps/regression/${regression.value.document_id}`,
      { params: { tenant_id: regression.value.tenant_id } }
    )
    ElMessage.success('回归检测完成')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    regLoading.value = false
  }
}

async function loadTenants() {
  try {
    tenants.value = await request.get('/platform/tenants')
  } catch {
    tenants.value = []
  }
}

async function loadCategories() {
  try {
    categories.value = await request.get('/categories')
  } catch {
    categories.value = []
  }
}

async function loadGaps() {
  gapLoading.value = true
  try {
    gapData.value = await request.get('/platform/knowledge-gaps', {
      params: tenantFilter.value ? { tenant_id: tenantFilter.value } : {},
    })
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    gapLoading.value = false
  }
}

async function load() {
  loading.value = true
  try {
    data.value = await request.get('/platform/insights')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function copyBrief() {
  try {
    await navigator.clipboard.writeText(data.value.brief)
    ElMessage.success('简报已复制')
  } catch {
    ElMessage.warning('复制失败，请手动选择文本')
  }
}

onMounted(() => {
  load()
  loadGaps()
  loadCategories()
  loadTenants()
})
</script>

<style scoped>
.brief-card {
  padding: 24px 26px; border-radius: 18px; color: #fff;
  background:
    radial-gradient(600px 180px at 90% -20%, rgba(94, 234, 212, .28), transparent 60%),
    linear-gradient(120deg, #0f172a 0%, #1e3a8a 100%);
  box-shadow: 0 18px 40px rgba(15, 23, 42, .18);
}
.brief-head { display: flex; justify-content: space-between; align-items: flex-start; }
.brief-kicker { font-size: 10px; letter-spacing: .16em; color: rgba(255, 255, 255, .45); }
.brief-title { margin-top: 6px; font-size: 20px; font-weight: 800; }
.brief-text { margin-top: 16px; font-size: 14px; line-height: 1.9; color: rgba(255, 255, 255, .82); }
.copy-btn {
  background: rgba(255, 255, 255, .12); border: 1px solid rgba(255, 255, 255, .2);
  color: #fff;
}
.insight-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.card-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; gap: 12px; }
.card-title { font-size: 15px; font-weight: 700; color: #0f172a; margin-bottom: 4px; }
.list-row {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 0; border-bottom: 1px dashed #e5e7eb;
}
.list-row:last-child { border-bottom: none; }
.row-icon { font-size: 22px; }
.row-main { flex: 1; min-width: 0; }
.row-title { font-weight: 600; color: #1f2937; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.stock-badge {
  padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 700;
  color: #b45309; background: #fef3c7;
}
.slow-badge {
  padding: 3px 10px; border-radius: 999px; font-size: 12px;
  color: #64748b; background: #f1f5f9;
}
.score { font-size: 16px; font-weight: 800; }
.grade-a { color: #10b981; }
.grade-b { color: #f59e0b; }
.grade-c { color: #ef4444; }
.risk-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.gap-card { margin-top: 16px; }
.gap-tools { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.reg-head { display: flex; align-items: center; gap: 18px; margin-bottom: 16px; }
.reg-rate {
  width: 92px; height: 92px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 24px; font-weight: 800; color: #047857;
  background: #ecfdf5; border: 6px solid #a7f3d0;
}
.reg-rate.low { color: #b45309; background: #fffbeb; border-color: #fde68a; }
.reg-title { font-size: 14px; font-weight: 700; color: #0f172a; margin-bottom: 4px; }
.gap-summary { display: flex; flex-wrap: wrap; gap: 6px; }
.gap-chip {
  padding: 3px 10px; border-radius: 999px; font-size: 12px;
  color: #475569; background: #f1f5f9; white-space: nowrap;
}
.gap-chip.danger { color: #b91c1c; background: #fee2e2; }
.gap-chip.warn { color: #b45309; background: #fef3c7; }
.gap-item {
  display: flex; align-items: center; gap: 16px;
  padding: 14px 0; border-bottom: 1px dashed #e5e7eb;
}
.gap-item:last-child { border-bottom: none; }
.gap-main { flex: 1; min-width: 0; }
.gap-theme { font-size: 14px; font-weight: 700; color: #0f172a; margin-bottom: 6px; }
.gap-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }
.gap-queries { display: flex; flex-wrap: wrap; gap: 8px; font-size: 12px; color: #6b7280; line-height: 1.7; }
.warn { color: #f59e0b; }
.danger { color: #ef4444; }
.up { color: #10b981; }
.down { color: #ef4444; }
.muted { color: #98a1b3; }
@media (max-width: 1100px) {
  .insight-grid { grid-template-columns: 1fr; }
}
</style>
