<template>
  <div class="pf-page">
    <div class="pf-head">
      <div>
        <div class="pf-title">商品监管</div>
        <div class="pf-sub">全平台商品总览（只读）；商家经营操作仍在各自商家后台完成</div>
      </div>
      <div class="pf-toolbar">
        <el-input
          v-model="keyword"
          placeholder="搜索商品名称"
          clearable
          style="width: 220px"
          @keyup.enter="load"
          @clear="load"
        />
        <el-select v-model="status" style="width: 130px" @change="load">
          <el-option label="全部状态" value="" />
          <el-option label="在售" value="on_sale" />
          <el-option label="已下架" value="off_sale" />
        </el-select>
        <el-button type="primary" @click="load">查询</el-button>
      </div>
    </div>

    <div class="pf-card">
      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column label="商品" min-width="240">
          <template #default="{ row }">
            <div class="product-cell">
              <div class="thumb">
                <img v-if="row.image_url" :src="row.image_url" :alt="row.name" />
                <span v-else>{{ row.image }}</span>
              </div>
              <div>
                <div class="p-name">{{ row.name }}</div>
                <div class="pf-muted">{{ row.subtitle || '—' }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="store_name" label="所属店铺" width="160" show-overflow-tooltip />
        <el-table-column label="分类" width="110">
          <template #default="{ row }">{{ row.category_name || '未分类' }}</template>
        </el-table-column>
        <el-table-column label="价格" width="110">
          <template #default="{ row }"><span class="pf-money">¥{{ row.price }}</span></template>
        </el-table-column>
        <el-table-column prop="stock" label="库存" width="80" align="center" />
        <el-table-column prop="sales" label="销量" width="80" align="center" />
        <el-table-column label="规格" width="80" align="center">
          <template #default="{ row }">
            <span :class="{ 'pf-muted': !row.variant_count }">{{ row.variant_count || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'on_sale' ? 'success' : 'info'" size="small">
              {{ row.status === 'on_sale' ? '在售' : '已下架' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && rows.length === 0" description="没有匹配的商品" />
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import request from '../../api'

const rows = ref([])
const loading = ref(false)
const keyword = ref('')
const status = ref('')

async function load() {
  loading.value = true
  try {
    const params = {}
    if (keyword.value.trim()) params.keyword = keyword.value.trim()
    if (status.value) params.status = status.value
    rows.value = await request.get('/platform/products', { params })
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.product-cell { display: flex; align-items: center; gap: 12px; }
.thumb {
  width: 46px; height: 46px; border-radius: 10px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 24px; background: #f4f6fb; overflow: hidden;
}
.thumb img { width: 100%; height: 100%; object-fit: cover; }
.p-name { font-weight: 600; color: #1f2937; }
</style>
