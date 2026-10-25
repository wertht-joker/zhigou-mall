<template>
  <div class="search-page">
    <div class="filter-bar">
      <span class="result-tip">
        {{ keyword ? `“${keyword}” 的搜索结果` : '全部商品' }}
        <em>共 {{ products.length }} 件</em>
      </span>
      <el-radio-group v-model="activeCategory" size="small" @change="loadProducts">
        <el-radio-button :value="null">全部</el-radio-button>
        <el-radio-button v-for="c in categories" :key="c.id" :value="c.id">
          {{ c.icon }} {{ c.name }}
        </el-radio-button>
      </el-radio-group>
    </div>

    <div class="product-grid" v-loading="loading">
      <ProductCard v-for="p in products" :key="p.id" :product="p" />
    </div>
    <el-empty v-if="!loading && products.length === 0" description="没有找到相关商品，换个关键词试试？" />
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import request from '../api'
import ProductCard from '../components/ProductCard.vue'

const route = useRoute()
const keyword = ref(route.query.q || '')
const categories = ref([])
const activeCategory = ref(null)
const products = ref([])
const loading = ref(false)

async function loadCategories() {
  try { categories.value = await request.get('/product-categories') } catch (e) { /* 忽略 */ }
}

async function loadProducts() {
  loading.value = true
  try {
    products.value = await request.get('/products', {
      params: {
        keyword: keyword.value || undefined,
        category_id: activeCategory.value || undefined,
      },
    })
  } catch (e) { /* 忽略 */ } finally {
    loading.value = false
  }
}

watch(() => route.query.q, (q) => {
  keyword.value = q || ''
  loadProducts()
})

onMounted(() => {
  loadCategories()
  loadProducts()
})
</script>

<style scoped>
.filter-bar {
  background: #fff; border-radius: 8px; padding: 14px 16px; margin-bottom: 14px;
  display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap;
}
.result-tip { font-size: 14px; }
.result-tip em { font-style: normal; color: #999; margin-left: 8px; font-size: 12px; }
.product-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; }
@media (max-width: 1100px) { .product-grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 700px) { .product-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
