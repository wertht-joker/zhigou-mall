<template>
  <div class="page">
    <div class="page-header">
      <h3>📄 知识库管理（AI 客服知识来源）</h3>
      <div style="display:flex;gap:12px">
        <el-input v-model="keyword" placeholder="搜索文档名称" style="width:240px" clearable @input="loadDocuments" />
        <el-upload :show-file-list="false" :http-request="handleUpload" accept=".pdf,.docx,.xlsx,.md,.txt">
          <el-button type="primary">上传文档</el-button>
        </el-upload>
      </div>
    </div>

    <div class="version-bar">
      <el-input v-model="policyKey" placeholder="政策标识（可选，如 return_policy）" style="width:240px" clearable />
      <el-input v-model="version" placeholder="版本（可空，自动递增）" style="width:170px" clearable />
      <el-date-picker v-model="effectiveFrom" type="datetime" placeholder="生效时间（可空）"
        value-format="YYYY-MM-DDTHH:mm:ss" style="width:190px" />
      <span class="version-sep">至</span>
      <el-date-picker v-model="effectiveTo" type="datetime" placeholder="失效时间（可空）"
        value-format="YYYY-MM-DDTHH:mm:ss" style="width:190px" />
    </div>

    <el-table :data="documents" v-loading="loading" border stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="文档名称" />
      <el-table-column label="政策版本" width="170">
        <template #default="{ row }">
          <span v-if="row.policy_key">{{ row.policy_key }} · v{{ row.version }}</span>
          <span v-else class="muted">普通文档</span>
        </template>
      </el-table-column>
      <el-table-column label="生效期" width="220">
        <template #default="{ row }">
          <span v-if="row.effective_from || row.effective_to">
            {{ formatTime(row.effective_from) || '—' }} ~ {{ formatTime(row.effective_to) || '长期' }}
          </span>
          <span v-else class="muted">长期有效</span>
        </template>
      </el-table-column>
      <el-table-column prop="type" label="格式" width="80" />
      <el-table-column prop="chunk_count" label="切分块数" width="100" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'done' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'">
            {{ statusText(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="上传时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button size="small" type="danger" text @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../../api'

const documents = ref([])
const loading = ref(false)
const keyword = ref('')
const policyKey = ref('')
const version = ref('')
const effectiveFrom = ref('')
const effectiveTo = ref('')

async function loadDocuments() {
  loading.value = true
  try {
    documents.value = await request.get('/documents', { params: { keyword: keyword.value } })
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function handleUpload(options) {
  const formData = new FormData()
  formData.append('file', options.file)
  if (policyKey.value) formData.append('policy_key', policyKey.value)
  if (version.value) formData.append('version', version.value)
  if (effectiveFrom.value) formData.append('effective_from', effectiveFrom.value)
  if (effectiveTo.value) formData.append('effective_to', effectiveTo.value)
  try {
    const data = await request.post('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    ElMessage.success(`上传成功，切分为 ${data.chunk_count} 块`)
    loadDocuments()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`确认删除文档「${row.name}」？`, '提示', { type: 'warning' })
  try {
    await request.delete(`/documents/${row.id}`)
    ElMessage.success('删除成功')
    loadDocuments()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function statusText(s) {
  return { done: '已完成', processing: '处理中', failed: '失败' }[s] || s
}

function formatTime(t) {
  return t ? String(t).replace('T', ' ').slice(0, 19) : ''
}

onMounted(loadDocuments)
</script>

<style scoped>
.page { padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.version-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
.version-sep { color: #909399; font-size: 12px; }
.muted { color: #909399; font-size: 12px; }
</style>
