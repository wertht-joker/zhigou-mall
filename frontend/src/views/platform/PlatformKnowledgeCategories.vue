<template>
  <div class="pf-page">
    <div class="pf-head">
      <div>
        <div class="pf-title">知识分类</div>
        <div class="pf-sub">给知识文档分组，便于运营时按业务主题归档</div>
      </div>
      <div class="pf-toolbar">
        <el-button type="primary" @click="openCreate">+ 新建分类</el-button>
      </div>
    </div>

    <div class="pf-card">
      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="70" align="center" />
        <el-table-column prop="name" label="分类名称" min-width="180" />
        <el-table-column label="上级分类" width="160">
          <template #default="{ row }">{{ parentName(row.parent_id) }}</template>
        </el-table-column>
        <el-table-column prop="sort" label="排序" width="90" align="center" />
        <el-table-column label="操作" width="150" align="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button text type="danger" size="small" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && rows.length === 0" description="还没有知识分类" />
    </div>

    <el-dialog v-model="dialog" :title="form.id ? '编辑知识分类' : '新建知识分类'" width="460px">
      <el-form label-width="90px">
        <el-form-item label="分类名称">
          <el-input v-model="form.name" maxlength="100" placeholder="如：售后服务" />
        </el-form-item>
        <el-form-item label="上级分类">
          <el-select v-model="form.parent_id" style="width: 100%">
            <el-option label="无（一级分类）" :value="0" />
            <el-option
              v-for="c in firstLevel"
              :key="c.id"
              :label="c.name"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort" :min="0" :max="999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../../api'

const rows = ref([])
const loading = ref(false)
const dialog = ref(false)
const saving = ref(false)
const form = reactive({ id: null, name: '', parent_id: 0, sort: 0 })

const firstLevel = computed(() =>
  rows.value.filter((c) => !c.parent_id || c.parent_id === 0)
)

function parentName(parentId) {
  if (!parentId) return '—'
  return rows.value.find((c) => c.id === parentId)?.name || `#${parentId}`
}

async function load() {
  loading.value = true
  try {
    rows.value = await request.get('/categories')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, { id: null, name: '', parent_id: 0, sort: 0 })
  dialog.value = true
}

function openEdit(row) {
  Object.assign(form, {
    id: row.id,
    name: row.name,
    parent_id: row.parent_id || 0,
    sort: row.sort,
  })
  dialog.value = true
}

async function save() {
  if (!form.name.trim()) return ElMessage.warning('请填写分类名称')
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      parent_id: form.parent_id || 0,
      sort: form.sort,
    }
    if (form.id) {
      await request.put(`/categories/${form.id}`, payload)
      ElMessage.success('分类已更新')
    } else {
      await request.post('/categories', payload)
      ElMessage.success('分类已创建')
    }
    dialog.value = false
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确定删除分类「${row.name}」吗？`, '删除分类', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await request.delete(`/categories/${row.id}`)
    ElMessage.success('分类已删除')
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(load)
</script>
