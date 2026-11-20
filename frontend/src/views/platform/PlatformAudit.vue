<template>
  <div class="pf-page">
    <div class="pf-head">
      <div>
        <div class="pf-title">操作审计</div>
        <div class="pf-sub">售后 Agent 写操作的完整留痕：谁、做了什么、变更前后与链路 ID</div>
      </div>
      <div class="pf-toolbar">
        <el-radio-group v-model="result" @change="load">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="success">成功</el-radio-button>
          <el-radio-button value="partial">部分成功</el-radio-button>
          <el-radio-button value="failed">失败</el-radio-button>
        </el-radio-group>
        <el-button @click="load">刷新</el-button>
      </div>
    </div>

    <div class="pf-card">
      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="audit-expand">
              <div class="audit-block">
                <div class="audit-label">变更前</div>
                <pre>{{ pretty(row.before_json) }}</pre>
              </div>
              <div class="audit-block">
                <div class="audit-label">变更后</div>
                <pre>{{ pretty(row.after_json) }}</pre>
              </div>
              <div v-if="row.error" class="audit-error">错误：{{ row.error }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="160">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作人" width="110">
          <template #default="{ row }">👤 {{ row.username }}</template>
        </el-table-column>
        <el-table-column prop="action_type" label="动作" width="180" />
        <el-table-column label="对象" width="140">
          <template #default="{ row }">
            {{ row.target_type || '-' }}<span v-if="row.target_id"> #{{ row.target_id }}</span>
          </template>
        </el-table-column>
        <el-table-column label="结果" width="100">
          <template #default="{ row }">
            <el-tag :type="resultType(row.result)" size="small">{{ resultLabel(row.result) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="trace_id" label="Trace ID" min-width="200" show-overflow-tooltip />
      </el-table>
      <el-empty v-if="!loading && rows.length === 0" description="暂无可审计的操作" />
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import request from '../../api'

const rows = ref([])
const loading = ref(false)
const result = ref('')

function resultType(value) {
  return { success: 'success', partial: 'warning', failed: 'danger' }[value] || 'info'
}

function resultLabel(value) {
  return { success: '成功', partial: '部分成功', failed: '失败' }[value] || value
}

function formatDate(value) {
  if (!value) return '-'
  return value.slice(0, 19).replace('T', ' ')
}

function pretty(raw) {
  if (!raw) return '{}'
  try {
    return JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return raw
  }
}

async function load() {
  loading.value = true
  try {
    const params = { limit: 200 }
    if (result.value) params.result = result.value
    rows.value = await request.get('/platform/audit-logs', { params })
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.audit-expand { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 8px 18px 14px; }
.audit-block { min-width: 0; }
.audit-label { font-size: 12px; color: #7c8598; margin-bottom: 6px; }
.audit-block pre {
  margin: 0; padding: 12px; background: #f7f9fc; border-radius: 10px;
  font-size: 12px; color: #334155; white-space: pre-wrap; word-break: break-all;
  max-height: 220px; overflow: auto;
}
.audit-error { grid-column: 1 / -1; color: #ef4444; font-size: 12px; }
@media (max-width: 800px) {
  .audit-expand { grid-template-columns: 1fr; }
}
</style>
