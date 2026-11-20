<template>
  <div class="pf-page">
    <div class="pf-head">
      <div>
        <div class="pf-title">平台分类</div>
        <div class="pf-sub">全平台商品共用的一级分类，商家上新时从这些分类中选择</div>
      </div>
      <div class="pf-toolbar">
        <el-button type="primary" @click="openCreate">+ 新建分类</el-button>
      </div>
    </div>

    <div class="pf-card">
      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column label="图标" width="80" align="center">
          <template #default="{ row }"><span class="cat-icon">{{ row.icon }}</span></template>
        </el-table-column>
        <el-table-column prop="name" label="分类名称" min-width="160" />
        <el-table-column prop="sort" label="排序" width="90" align="center" />
        <el-table-column prop="product_count" label="商品数" width="100" align="center" />
        <el-table-column label="操作" width="160" align="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button text type="danger" size="small" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && rows.length === 0" description="还没有平台分类" />
    </div>

    <el-dialog v-model="dialog" :title="form.id ? '编辑分类' : '新建分类'" width="460px">
      <el-form label-width="80px">
        <el-form-item label="分类名称">
          <el-input v-model="form.name" maxlength="50" placeholder="如：手机数码" />
        </el-form-item>
        <el-form-item label="图标">
          <el-input v-model="form.icon" maxlength="20" placeholder="一个 emoji，如 📱" />
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
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../../api'

const rows = ref([])
const loading = ref(false)
const dialog = ref(false)
const saving = ref(false)
const form = reactive({ id: null, name: '', icon: '🛒', sort: 0 })

async function load() {
  loading.value = true
  try {
    rows.value = await request.get('/platform/product-categories')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, { id: null, name: '', icon: '🛒', sort: 0 })
  dialog.value = true
}

function openEdit(row) {
  Object.assign(form, { id: row.id, name: row.name, icon: row.icon, sort: row.sort })
  dialog.value = true
}

async function save() {
  if (!form.name.trim()) return ElMessage.warning('请填写分类名称')
  saving.value = true
  try {
    const payload = { name: form.name.trim(), icon: form.icon || '🛒', sort: form.sort }
    if (form.id) {
      await request.put(`/platform/product-categories/${form.id}`, payload)
      ElMessage.success('分类已更新')
    } else {
      await request.post('/platform/product-categories', payload)
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
    await ElMessageBox.confirm(
      `确定删除分类「${row.name}」吗？分类下还有商品时将无法删除。`,
      '删除分类',
      { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await request.delete(`/platform/product-categories/${row.id}`)
    ElMessage.success('分类已删除')
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(load)
</script>

<style scoped>
.cat-icon { font-size: 20px; }
</style>
