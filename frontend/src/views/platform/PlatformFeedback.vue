<template>
  <div class="pf-page">
    <div class="pf-head">
      <div>
        <div class="pf-title">反馈分析</div>
        <div class="pf-sub">顾客对 AI 客服回答的点赞 / 点踩反馈，用于持续优化知识库</div>
      </div>
      <div class="pf-toolbar">
        <el-button @click="load">刷新</el-button>
      </div>
    </div>

    <div class="pf-grid">
      <div class="pf-stat">
        <div class="pf-stat-label">反馈总数</div>
        <div class="pf-stat-value">{{ data.total }}</div>
        <div class="pf-stat-hint">最近 50 条明细</div>
      </div>
      <div class="pf-stat">
        <div class="pf-stat-label">有用</div>
        <div class="pf-stat-value good">{{ data.up }}</div>
        <div class="pf-stat-hint">回答解决了问题</div>
      </div>
      <div class="pf-stat">
        <div class="pf-stat-label">无用</div>
        <div class="pf-stat-value bad">{{ data.down }}</div>
        <div class="pf-stat-hint">建议补充知识库</div>
      </div>
      <div class="pf-stat">
        <div class="pf-stat-label">满意度</div>
        <div class="pf-stat-value">{{ data.satisfaction === null ? '—' : data.satisfaction + '%' }}</div>
        <div class="pf-stat-hint">有用 / 反馈总数</div>
      </div>
    </div>

    <div class="pf-card">
      <div class="panel-title">最近反馈</div>
      <el-table :data="data.recent" v-loading="loading" stripe>
        <el-table-column label="评价" width="90">
          <template #default="{ row }">
            <el-tag :type="row.type === 'up' ? 'success' : 'danger'" size="small">
              {{ row.type === 'up' ? '有用' : '无用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="回答内容" min-width="320">
          <template #default="{ row }">
            <span v-if="row.content">{{ row.content }}</span>
            <span v-else class="pf-muted">消息 #{{ row.message_id }}（内容已不可用）</span>
          </template>
        </el-table-column>
        <el-table-column prop="message_id" label="消息 ID" width="100" align="center" />
        <el-table-column label="反馈时间" width="170">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !data.recent.length" description="暂无反馈数据" />
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import request from '../../api'

const loading = ref(false)
const data = ref({ up: 0, down: 0, total: 0, satisfaction: null, recent: [] })

function formatDate(value) {
  if (!value) return '-'
  return value.slice(0, 16).replace('T', ' ')
}

async function load() {
  loading.value = true
  try {
    data.value = await request.get('/platform/feedback')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.panel-title { font-size: 15px; font-weight: 700; color: #0f172a; margin-bottom: 14px; }
.good { color: #10b981; }
.bad { color: #ef4444; }
</style>
