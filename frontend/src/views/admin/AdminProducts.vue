<template>
  <div class="page">
    <div class="page-header">
      <h3>📦 商品管理</h3>
      <div style="display:flex;gap:12px">
        <el-input v-model="keyword" placeholder="搜索商品名称" style="width:220px" clearable @input="load" />
        <el-button type="primary" @click="openAdd">＋ 新增商品</el-button>
      </div>
    </div>

    <el-table :data="products" v-loading="loading" border stripe>
      <el-table-column prop="image" label="图" width="70" align="center">
        <template #default="{ row }">
          <img v-if="row.image_url" :src="row.image_url" class="row-img" />
          <span v-else style="font-size:24px">{{ row.image }}</span>
        </template>
      </el-table-column>
      <el-table-column label="商品名称" min-width="180">
        <template #default="{ row }">
          {{ row.name }}
          <el-tag v-if="row.variants?.length" size="small" effect="plain" style="margin-left: 6px">
            多规格
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="subtitle" label="卖点" min-width="140" show-overflow-tooltip />
      <el-table-column prop="price" label="售价" width="100">
        <template #default="{ row }"><span class="price">¥{{ row.price }}</span></template>
      </el-table-column>
      <el-table-column prop="stock" label="库存" width="80" />
      <el-table-column prop="sales" label="销量" width="80" />
      <el-table-column prop="status" label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 'on_sale' ? 'success' : 'info'">
            {{ row.status === 'on_sale' ? '在售' : '下架' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220">
        <template #default="{ row }">
          <el-button size="small" text type="primary" @click="toggleSale(row)">
            {{ row.status === 'on_sale' ? '下架' : '上架' }}
          </el-button>
          <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" text type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑商品' : '新增商品'" width="520px">
      <el-form label-width="90px">
        <el-form-item label="商品名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="卖点副标题"><el-input v-model="form.subtitle" /></el-form-item>
        <el-form-item label="商品分类">
          <el-select v-model="form.category_id" placeholder="选择分类" style="width:100%">
            <el-option v-for="c in categories" :key="c.id" :label="`${c.icon} ${c.name}`" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="售价（元）" v-if="!hasVariants">
          <el-input-number v-model="form.price" :min="0.01" :precision="2" />
          <span style="margin-left:16px">划线原价</span>
          <el-input-number v-model="form.original_price" :min="0" :precision="2" style="margin-left:8px" />
        </el-form-item>
        <el-form-item label="库存" v-if="!hasVariants">
          <el-input-number v-model="form.stock" :min="0" />
        </el-form-item>

        <el-form-item label="多规格">
          <el-switch v-model="hasVariants" active-text="开启" inactive-text="关闭" />
          <span class="form-hint">开启后按规格独立定价与库存，售价/库存取规格汇总</span>
        </el-form-item>
        <el-form-item v-if="hasVariants" label="规格列表">
          <div class="variant-editor">
            <div v-for="(v, idx) in form.variants" :key="idx" class="variant-row">
              <el-input v-model="v.spec" placeholder="如 16GB+512GB" style="width: 150px" />
              <el-input-number v-model="v.price" :min="0.01" :precision="2" controls-position="right" placeholder="价格" />
              <el-input-number v-model="v.stock" :min="0" controls-position="right" placeholder="库存" />
              <el-button text type="danger" @click="removeVariant(idx)">删除</el-button>
            </div>
            <el-button text type="primary" @click="addVariant">＋ 添加规格</el-button>
          </div>
        </el-form-item>
        <el-form-item label="商品主图">
          <div class="image-upload">
            <img v-if="form.image_url" :src="form.image_url" class="image-preview" />
            <span v-else class="image-emoji">{{ form.image || '📦' }}</span>
            <el-upload
              v-if="editing"
              :show-file-list="false"
              :http-request="uploadImage"
              accept="image/png,image/jpeg,image/webp,image/gif"
            >
              <el-button size="small">{{ form.image_url ? '更换图片' : '上传图片' }}</el-button>
            </el-upload>
            <span v-else class="form-hint">保存商品后可上传主图</span>
          </div>
        </el-form-item>
        <el-form-item label="主图 emoji"><el-input v-model="form.image" style="width:100px" /></el-form-item>
        <el-form-item label="图文详情"><el-input v-model="form.description" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="上架状态">
          <el-switch v-model="onSale" active-text="在售" inactive-text="下架" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../../api'

const products = ref([])
const categories = ref([])
const loading = ref(false)
const keyword = ref('')
const dialogVisible = ref(false)
const editing = ref(null)
const form = ref({})
const hasVariants = ref(false)
const onSale = computed({
  get: () => form.value.status === 'on_sale',
  set: (v) => { form.value.status = v ? 'on_sale' : 'off_sale' },
})

async function load() {
  loading.value = true
  try {
    products.value = await request.get('/merchant/products', { params: { keyword: keyword.value } })
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function loadCategories() {
  try { categories.value = await request.get('/product-categories') } catch (e) { /* 忽略 */ }
}

function emptyForm() {
  return {
    name: '', subtitle: '', description: '', price: 0.01, original_price: null,
    stock: 0, image: '📦', category_id: null, status: 'on_sale', variants: [],
  }
}

function openAdd() {
  editing.value = null
  form.value = emptyForm()
  hasVariants.value = false
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = row
  form.value = {
    ...row,
    variants: (row.variants || []).map((v) => ({
      id: v.id, spec: v.spec, price: v.price, stock: v.stock,
    })),
  }
  hasVariants.value = !!form.value.variants.length
  dialogVisible.value = true
}

function addVariant() {
  form.value.variants.push({ spec: '', price: 0.01, stock: 0 })
}

function removeVariant(index) {
  form.value.variants.splice(index, 1)
}

async function uploadImage({ file }) {
  if (!editing.value) return
  const fd = new FormData()
  fd.append('file', file)
  try {
    const data = await request.post(`/merchant/products/${editing.value.id}/image`, fd)
    form.value.image_url = data.image_url
    ElMessage.success('主图已更新')
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function save() {
  if (!form.value.name?.trim()) return ElMessage.warning('请填写商品名称')
  if (hasVariants.value && !form.value.variants.length) {
    return ElMessage.warning('请至少添加一个规格')
  }
  if (hasVariants.value && form.value.variants.some((v) => !v.spec?.trim())) {
    return ElMessage.warning('请填写完整的规格名称')
  }
  const payload = {
    ...form.value,
    variants: hasVariants.value ? form.value.variants : [],
  }
  try {
    if (editing.value) {
      await request.put(`/merchant/products/${editing.value.id}`, payload)
    } else {
      await request.post('/merchant/products', payload)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function toggleSale(row) {
  try {
    const next = row.status === 'on_sale' ? 'off_sale' : 'on_sale'
    await request.put(`/merchant/products/${row.id}`, { ...row, status: next })
    ElMessage.success(next === 'on_sale' ? '已上架' : '已下架')
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`确认删除商品「${row.name}」？`, '提示', { type: 'warning' })
  try {
    await request.delete(`/merchant/products/${row.id}`)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(() => {
  load()
  loadCategories()
})
</script>

<style scoped>
.page { padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.form-hint { margin-left: 12px; font-size: 12px; color: #999; }
.variant-editor { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.variant-row { display: flex; align-items: center; gap: 8px; }
.variant-row :deep(.el-input-number) { width: 110px; }
.row-img { width: 38px; height: 38px; object-fit: cover; border-radius: 6px; }
.image-upload { display: flex; align-items: center; gap: 12px; }
.image-preview { width: 64px; height: 64px; object-fit: cover; border-radius: 8px; border: 1px solid #eee; }
.image-emoji {
  width: 64px; height: 64px; display: flex; align-items: center; justify-content: center;
  font-size: 32px; background: #faf6f5; border-radius: 8px;
}
</style>
