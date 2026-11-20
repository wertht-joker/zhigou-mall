<template>
  <div class="pf-page">
    <div class="pf-head">
      <div>
        <div class="pf-title">知识库管理</div>
        <div class="pf-sub">支持文档编辑、政策版本切换与生效时间管理；内容变更请上传新版本</div>
      </div>
      <div class="pf-toolbar">
        <el-select
          v-model="tenantFilter"
          placeholder="全部商家"
          clearable
          style="width: 170px"
          @change="load"
        >
          <el-option label="全部商家" value="" />
          <el-option v-for="t in tenants" :key="t.id" :label="t.name" :value="t.id" />
        </el-select>
        <el-input
          v-model="keyword"
          placeholder="搜索文档名称"
          clearable
          style="width: 210px"
          @keyup.enter="load"
          @clear="load"
        />
        <el-switch v-model="onlyCurrent" active-text="仅看当前版本" />
        <el-button @click="load">查询</el-button>
        <el-button type="primary" @click="openUpload()">+ 上传文档</el-button>
      </div>
    </div>

    <div class="pf-card">
      <el-table :data="visibleRows" v-loading="loading" stripe>
        <el-table-column label="文档" min-width="220">
          <template #default="{ row }">
            <div class="doc-name">📄 {{ row.name }}</div>
            <div class="pf-muted">{{ row.type.toUpperCase() }} · {{ formatSize(row.size) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="所属店铺" width="150">
          <template #default="{ row }">
            <el-tag size="small" :type="row.tenant_id === 1 ? 'success' : 'info'">
              {{ tenantName(row.tenant_id) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="110">
          <template #default="{ row }">{{ categoryName(row.category_id) }}</template>
        </el-table-column>
        <el-table-column label="政策 / 版本" width="180">
          <template #default="{ row }">
            <template v-if="row.policy_key">
              <div class="policy-key">{{ row.policy_key }}</div>
              <div class="version-line">
                <span>v{{ row.version }}</span>
                <el-tag :type="row.lifecycle_status === 'active' ? 'success' : 'info'" size="small">
                  {{ row.lifecycle_status === 'active' ? '当前版本' : '历史版本' }}
                </el-tag>
              </div>
            </template>
            <span v-else class="pf-muted">普通文档</span>
          </template>
        </el-table-column>
        <el-table-column label="生效区间" width="190">
          <template #default="{ row }">
            <div v-if="row.effective_from || row.effective_to" class="pf-muted">
              {{ row.effective_from ? formatDate(row.effective_from) : '不限' }}
              ~
              {{ row.effective_to ? formatDate(row.effective_to) : '不限' }}
            </div>
            <span v-else class="pf-muted">长期有效</span>
          </template>
        </el-table-column>
        <el-table-column label="切块" width="75" align="center" prop="chunk_count" />
        <el-table-column label="上传时间" width="145">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" align="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button
              v-if="row.policy_key"
              text
              type="primary"
              size="small"
              @click="openVersions(row)"
            >
              版本
            </el-button>
            <el-button text type="danger" size="small" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && visibleRows.length === 0" description="暂无知识文档" />
    </div>

    <!-- 编辑元数据 -->
    <el-dialog v-model="editDialog" title="编辑文档" width="540px">
      <div v-if="editing" class="edit-meta">
        <span>{{ editing.type.toUpperCase() }} · {{ formatSize(editing.size) }}</span>
        <span v-if="editing.policy_key">
          {{ editing.policy_key }} · v{{ editing.version }}（版本号不可修改）
        </span>
      </div>
      <el-form label-width="90px">
        <el-form-item label="文档名称">
          <el-input v-model="editForm.name" maxlength="255" />
        </el-form-item>
        <el-form-item label="知识分类">
          <el-select v-model="editForm.category_id" clearable style="width: 100%">
            <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="生效开始">
          <el-date-picker
            v-model="editForm.effective_from"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ss"
            placeholder="留空表示不限"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="生效结束">
          <el-date-picker
            v-model="editForm.effective_to"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ss"
            placeholder="留空表示长期有效"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <div class="pf-muted edit-tip">修改生效时间会重建检索索引；修改正文内容请通过「上传新版本」完成。</div>
      <template #footer>
        <el-button @click="editDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 版本管理 -->
    <el-dialog v-model="versionDialog" :title="`版本管理 · ${versionDoc?.policy_key || ''}`" width="820px">
      <div class="version-head">
        <div class="pf-muted">
          当前版本：v{{ activeVersion }} · 共 {{ versions.length }} 个版本
        </div>
        <el-button type="primary" size="small" @click="openUpload(versionDoc)">+ 上传新版本</el-button>
      </div>
      <el-table :data="versions" v-loading="versionLoading" size="small">
        <el-table-column label="版本" width="80" align="center">
          <template #default="{ row }">v{{ row.version }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.lifecycle_status === 'active' ? 'success' : 'info'" size="small">
              {{ row.lifecycle_status === 'active' ? '当前' : '已替代' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="文档" min-width="170" show-overflow-tooltip />
        <el-table-column label="生效区间" width="210">
          <template #default="{ row }">
            <span class="pf-muted">
              {{ row.effective_from ? formatDate(row.effective_from) : '不限' }}
              ~
              {{ row.effective_to ? formatDate(row.effective_to) : '不限' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="上传时间" width="145">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="190" align="right">
          <template #default="{ row }">
            <el-button
              v-if="row.lifecycle_status !== 'active'"
              text
              type="success"
              size="small"
              @click="activate(row)"
            >
              设为当前
            </el-button>
            <el-button text type="primary" size="small" @click="editFromVersion(row)">编辑</el-button>
            <el-button text type="danger" size="small" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 上传 / 新版本 -->
    <el-dialog
      v-model="dialog"
      :title="uploadParent ? `上传新版本 · ${uploadParent.policy_key}` : '上传知识文档'"
      width="560px"
      @closed="reset"
    >
      <div v-if="uploadParent" class="upload-hint">
        将在 v{{ uploadParent.version }} 基础上自动创建新版本，旧版本保留为历史版本
      </div>
      <el-upload
        ref="uploadRef"
        drag
        :auto-upload="false"
        :limit="1"
        accept=".pdf,.docx,.xlsx,.md,.txt"
        :on-change="onFileChange"
        :on-remove="() => (file = null)"
      >
        <div class="upload-icon">📥</div>
        <div class="upload-text">拖拽文件到此处，或点击选择</div>
        <div class="pf-muted">支持 PDF / Word / Excel / Markdown / TXT</div>
      </el-upload>

      <el-form label-width="90px" class="upload-form">
        <el-form-item label="归属店铺">
          <el-select v-model="form.tenant_id" :disabled="!!uploadParent" style="width: 100%">
            <el-option v-for="t in tenants" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="知识分类">
          <el-select v-model="form.category_id" clearable placeholder="可选" style="width: 100%">
            <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="政策标识">
          <el-input
            v-model="form.policy_key"
            :disabled="!!uploadParent"
            placeholder="可选，如 return_policy（同一标识自动升版本）"
          />
        </el-form-item>
        <el-form-item label="版本号">
          <el-input-number
            v-model="form.version"
            :min="1"
            :max="999"
            :disabled="!!uploadParent"
            placeholder="留空自动 +1"
          />
        </el-form-item>
        <el-form-item label="生效开始">
          <el-date-picker
            v-model="form.effective_from"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ss"
            placeholder="留空默认从现在生效"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="生效结束">
          <el-date-picker
            v-model="form.effective_to"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ss"
            placeholder="留空表示长期有效"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="submit">
          {{ uploading ? '解析入库中…' : (uploadParent ? '上传新版本' : '上传并入库') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../../api'

const rows = ref([])
const categories = ref([])
const tenants = ref([])
const tenantFilter = ref('')
const loading = ref(false)
const keyword = ref('')
const onlyCurrent = ref(true)

const dialog = ref(false)
const uploading = ref(false)
const file = ref(null)
const uploadRef = ref(null)
const uploadParent = ref(null)

const editDialog = ref(false)
const editing = ref(null)
const saving = ref(false)
const editForm = reactive({
  name: '',
  category_id: null,
  effective_from: null,
  effective_to: null,
})

const versionDialog = ref(false)
const versionDoc = ref(null)
const versions = ref([])
const versionLoading = ref(false)

const form = reactive({
  tenant_id: null,
  category_id: null,
  policy_key: '',
  version: null,
  effective_from: null,
  effective_to: null,
})

const visibleRows = computed(() =>
  onlyCurrent.value
    ? rows.value.filter((r) => !r.policy_key || r.lifecycle_status === 'active')
    : rows.value
)
const activeVersion = computed(
  () => versions.value.find((v) => v.lifecycle_status === 'active')?.version || '—'
)

function formatSize(size) {
  if (!size) return '0 KB'
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(0)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function formatDate(value) {
  if (!value) return '-'
  return value.slice(0, 16).replace('T', ' ')
}

function statusType(status) {
  return { done: 'success', processing: 'warning', failed: 'danger' }[status] || 'info'
}

function statusLabel(status) {
  return { done: '已入库', processing: '处理中', failed: '失败' }[status] || status
}

function categoryName(categoryId) {
  if (!categoryId) return '未分类'
  return categories.value.find((c) => c.id === categoryId)?.name || `#${categoryId}`
}

function tenantName(tenantId) {
  if (!tenantId) return '平台公共'
  return tenants.value.find((t) => t.id === tenantId)?.name || `租户#${tenantId}`
}

async function load() {
  loading.value = true
  try {
    const params = {}
    if (keyword.value.trim()) params.keyword = keyword.value.trim()
    if (tenantFilter.value) params.tenant_id = tenantFilter.value
    rows.value = await request.get('/documents', { params })
  } finally {
    loading.value = false
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

function reset() {
  file.value = null
  uploadParent.value = null
  uploadRef.value?.clearFiles()
  Object.assign(form, {
    tenant_id: tenantFilter.value || tenants.value[0]?.id || null,
    category_id: null,
    policy_key: '',
    version: null,
    effective_from: null,
    effective_to: null,
  })
}

function openUpload(parent = null) {
  reset()
  uploadParent.value = parent
  if (parent) {
    form.tenant_id = parent.tenant_id
    form.policy_key = parent.policy_key
    form.category_id = parent.category_id
    form.effective_from = new Date().toISOString().slice(0, 19)
  }
  if (versionDialog.value) versionDialog.value = false
  dialog.value = true
}

function onFileChange(uploadFile) {
  file.value = uploadFile.raw
}

function openEdit(row) {
  editing.value = row
  Object.assign(editForm, {
    name: row.name,
    category_id: row.category_id,
    effective_from: row.effective_from,
    effective_to: row.effective_to,
  })
  editDialog.value = true
}

function editFromVersion(row) {
  versionDialog.value = false
  openEdit(row)
}

async function saveEdit() {
  if (!editForm.name.trim()) return ElMessage.warning('请填写文档名称')
  saving.value = true
  try {
    await request.put(`/documents/${editing.value.id}`, {
      name: editForm.name.trim(),
      category_id: editForm.category_id,
      effective_from: editForm.effective_from,
      effective_to: editForm.effective_to,
    }, { params: { tenant_id: editing.value.tenant_id } })
    ElMessage.success('文档已更新')
    editDialog.value = false
    await load()
    if (versionDialog.value) await loadVersions(versionDoc.value.id)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function submit() {
  if (!file.value) return ElMessage.warning('请选择要上传的文件')
  const fd = new FormData()
  fd.append('file', file.value)
  if (form.tenant_id) fd.append('tenant_id', String(form.tenant_id))
  if (form.category_id) fd.append('category_id', String(form.category_id))
  if (form.policy_key.trim()) fd.append('policy_key', form.policy_key.trim())
  if (form.version) fd.append('version', String(form.version))
  if (form.effective_from) fd.append('effective_from', form.effective_from)
  if (form.effective_to) fd.append('effective_to', form.effective_to)

  uploading.value = true
  try {
    await request.post('/documents/upload', fd)
    ElMessage.success(uploadParent.value ? '新版本已入库' : '文档已解析并入库')
    dialog.value = false
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    uploading.value = false
  }
}

async function openVersions(row) {
  versionDoc.value = row
  versionDialog.value = true
  await loadVersions(row.id)
}

async function loadVersions(docId) {
  versionLoading.value = true
  try {
    versions.value = await request.get(`/documents/${docId}/versions`, {
      params: { tenant_id: versionDoc.value?.tenant_id },
    })
  } finally {
    versionLoading.value = false
  }
}

async function activate(row) {
  try {
    await ElMessageBox.confirm(
      `确定把 v${row.version} 设为当前生效版本吗？其他版本会自动变为历史版本。`,
      '切换当前版本',
      { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await request.post(`/documents/${row.id}/activate`, null, {
      params: { tenant_id: row.tenant_id },
    })
    ElMessage.success(`已切换到 v${row.version}`)
    await load()
    await loadVersions(row.id)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${row.name}」吗？删除后 AI 客服将不再检索到该文档。`,
      '删除文档',
      { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await request.delete(`/documents/${row.id}`, {
      params: { tenant_id: row.tenant_id },
    })
    ElMessage.success('文档已删除')
    await load()
    if (versionDialog.value) await loadVersions(versionDoc.value.id)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(() => {
  load()
  loadCategories()
  loadTenants()
})
</script>

<style scoped>
.doc-name { font-weight: 600; color: #1f2937; }
.policy-key { font-weight: 600; color: #1f2937; }
.version-line { display: flex; align-items: center; gap: 8px; margin-top: 4px; font-size: 12px; color: #7c8598; }
.edit-meta {
  display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap;
  padding: 10px 12px; margin-bottom: 16px; border-radius: 10px;
  background: #f7f9fc; color: #7c8598; font-size: 12px;
}
.edit-tip { line-height: 1.6; }
.upload-icon { font-size: 34px; line-height: 1.4; }
.upload-text { font-size: 14px; color: #374151; margin-bottom: 4px; }
.upload-form { margin-top: 18px; }
.upload-hint {
  margin-bottom: 14px; padding: 10px 12px; border-radius: 10px;
  background: #eff6ff; color: #1d4ed8; font-size: 12px;
}
.version-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
</style>
