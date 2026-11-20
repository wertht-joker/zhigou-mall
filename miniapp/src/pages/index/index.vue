<template>
  <view class="home">
    <view class="hero">
      <view class="hero-top">
        <view>
          <view class="hero-title">智购商城</view>
          <view class="hero-sub">品质好物 · AI 客服全天在线</view>
        </view>
        <view class="hero-badge">自营 + 严选商家</view>
      </view>
      <view class="search">
        <text class="search-icon">⌕</text>
        <input
          v-model="keyword"
          class="search-input"
          placeholder="搜索商品，如：耳机"
          confirm-type="search"
          @confirm="search"
        />
        <text v-if="keyword" class="search-clear" @tap="clearSearch">×</text>
      </view>
    </view>

    <scroll-view scroll-x class="cats" :show-scrollbar="false">
      <view class="cat" :class="{ active: activeCategory === null }" @tap="pickCategory(null)">全部</view>
      <view
        v-for="c in categories"
        :key="c.id"
        class="cat"
        :class="{ active: activeCategory === c.id }"
        @tap="pickCategory(c.id)"
      >
        <text class="cat-icon">{{ c.icon }}</text>
        <text>{{ c.name }}</text>
      </view>
    </scroll-view>

    <view class="section-head">
      <view>
        <view class="section-title">{{ activeName }}</view>
        <view class="section-sub">为你精选 {{ total }} 件好物</view>
      </view>
      <text class="more" @tap="goChat">问问 AI ›</text>
    </view>

    <view v-if="loading" class="grid">
      <view v-for="n in 4" :key="n" class="product skeleton">
        <view class="sk-pic"></view>
        <view class="sk-line"></view>
        <view class="sk-line short"></view>
      </view>
    </view>

    <view v-else class="grid">
      <view v-for="p in products" :key="p.id" class="product" @tap="goDetail(p.id)">
        <view class="p-pic">
          <image v-if="p.image_url" class="p-img" :src="imageUrl(p.image_url)" mode="aspectFill" />
          <text v-else class="p-emoji">{{ p.image || '📦' }}</text>
          <view class="p-tag">{{ (p.store_name || '智购自营').includes('自营') ? '自营' : '商家' }}</view>
        </view>
        <view class="p-body">
          <view class="p-name">{{ p.name }}</view>
          <view class="p-sub">{{ p.subtitle }}</view>
          <view class="p-meta">
            <text class="p-rate">★ {{ p.avg_rating || '—' }}</text>
            <text class="p-sales">已售 {{ p.sales || 0 }}</text>
          </view>
          <view class="p-bottom">
            <view>
              <text class="p-price">¥{{ p.price }}</text>
              <text v-if="p.original_price" class="p-origin">¥{{ p.original_price }}</text>
            </view>
            <text class="p-store">{{ p.store_name || '智购自营' }}</text>
          </view>
        </view>
      </view>
    </view>

    <view v-if="!loading && !products.length" class="empty">该分类暂无在售商品，换个关键词试试</view>

    <view v-if="products.length && products.length < total" class="load-more" @tap="loadMore">
      {{ loadingMore ? '加载中…' : '加载更多' }}
    </view>
    <view v-else-if="products.length" class="load-end">— 没有更多了 —</view>

    <view class="ai-fab" @tap="goChat">
      <text class="ai-fab-icon">AI</text>
      <text class="ai-fab-text">客服</text>
    </view>
  </view>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onShow, onPullDownRefresh, onReachBottom } from '@dcloudio/uni-app'
import { http } from '../../api/request'
import { imageUrl } from '../../utils/format'
import { refreshCartBadge } from '../../utils/cart'

const categories = ref([])
const products = ref([])
const activeCategory = ref(null)
const keyword = ref('')
const loading = ref(false)
const loadingMore = ref(false)
const page = ref(1)
const total = ref(0)
const PAGE_SIZE = 12

const activeName = computed(() => {
  if (keyword.value) return `搜索「${keyword.value}」`
  const current = categories.value.find((c) => c.id === activeCategory.value)
  return current ? current.name : '为你推荐'
})

async function loadCategories() {
  try {
    categories.value = await http.get('/product-categories')
  } catch {
    categories.value = []
  }
}

async function loadProducts() {
  loading.value = true
  page.value = 1
  try {
    const data = await http.get('/products', {
      keyword: keyword.value || undefined,
      category_id: activeCategory.value || undefined,
      page: 1,
      page_size: PAGE_SIZE,
    })
    products.value = data.items || []
    total.value = data.total || 0
  } catch {
    products.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (loading.value || loadingMore.value || products.value.length >= total.value) return
  loadingMore.value = true
  try {
    const data = await http.get('/products', {
      keyword: keyword.value || undefined,
      category_id: activeCategory.value || undefined,
      page: page.value + 1,
      page_size: PAGE_SIZE,
    })
    page.value += 1
    products.value = products.value.concat(data.items || [])
    total.value = data.total || total.value
  } catch {
    // 请求层已提示
  } finally {
    loadingMore.value = false
  }
}

function pickCategory(id) {
  activeCategory.value = activeCategory.value === id ? null : id
  loadProducts()
}

function search() {
  loadProducts()
}

function clearSearch() {
  keyword.value = ''
  loadProducts()
}

function goDetail(id) {
  uni.navigateTo({ url: `/pages/product/detail?id=${id}` })
}

function goChat() {
  uni.navigateTo({ url: '/pages/chat/chat' })
}

onShow(() => {
  refreshCartBadge()
})

onReachBottom(() => {
  loadMore()
})

onPullDownRefresh(async () => {
  await Promise.all([loadCategories(), loadProducts()])
  uni.stopPullDownRefresh()
})

loadCategories()
loadProducts()
</script>

<style scoped>
.home {
  min-height: 100vh;
  padding: 24rpx 24rpx 120rpx;
}

.hero {
  padding: 30rpx 28rpx 28rpx;
  border-radius: 32rpx;
  background: linear-gradient(135deg, #d81e14 0%, #f04b2f 55%, #ff8a5c 100%);
  box-shadow: 0 16rpx 36rpx rgba(225, 37, 27, 0.24);
  color: #fff;
}

.hero-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.hero-title {
  font-size: 44rpx;
  font-weight: 800;
  letter-spacing: 2rpx;
}

.hero-sub {
  margin-top: 8rpx;
  font-size: 24rpx;
  opacity: 0.86;
}

.hero-badge {
  padding: 8rpx 16rpx;
  border-radius: 999rpx;
  background: rgba(255, 255, 255, 0.18);
  border: 1rpx solid rgba(255, 255, 255, 0.35);
  font-size: 20rpx;
}

.search {
  margin-top: 28rpx;
  height: 80rpx;
  padding: 0 24rpx;
  border-radius: 999rpx;
  background: #fff;
  display: flex;
  align-items: center;
}

.search-icon {
  font-size: 36rpx;
  color: #b0b5bd;
  margin-right: 8rpx;
}

.search-input {
  flex: 1;
  font-size: 26rpx;
  color: #1f2937;
}

.search-clear {
  padding: 0 8rpx;
  color: #b0b5bd;
  font-size: 34rpx;
}

.cats {
  white-space: nowrap;
  margin: 24rpx 0 8rpx;
}

.cat {
  display: inline-flex;
  align-items: center;
  gap: 8rpx;
  margin-right: 16rpx;
  padding: 14rpx 26rpx;
  border-radius: 999rpx;
  background: #fff;
  color: #4b5563;
  font-size: 25rpx;
  border: 1rpx solid #eef0f3;
}

.cat.active {
  background: #fff1f0;
  color: #e1251b;
  border-color: #ffc9c2;
  font-weight: 600;
}

.cat-icon {
  font-size: 28rpx;
}

.section-head {
  margin: 28rpx 4rpx 18rpx;
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
}

.section-title {
  font-size: 34rpx;
  font-weight: 700;
}

.section-sub {
  margin-top: 6rpx;
  font-size: 22rpx;
  color: #9aa0aa;
}

.more {
  font-size: 24rpx;
  color: #e1251b;
}

.grid {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
}

.product {
  width: 48.6%;
  margin-bottom: 20rpx;
  background: #fff;
  border-radius: 24rpx;
  overflow: hidden;
  box-shadow: 0 6rpx 20rpx rgba(15, 23, 42, 0.05);
}

.p-pic {
  position: relative;
  height: 300rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #fdf6f5, #fbeae8);
}

.p-img {
  width: 100%;
  height: 100%;
}

.p-emoji {
  font-size: 110rpx;
}

.p-tag {
  position: absolute;
  left: 14rpx;
  top: 14rpx;
  padding: 4rpx 12rpx;
  border-radius: 999rpx;
  background: rgba(225, 37, 27, 0.92);
  color: #fff;
  font-size: 19rpx;
}

.p-body {
  padding: 18rpx 18rpx 20rpx;
}

.p-name {
  font-size: 26rpx;
  line-height: 1.45;
  height: 76rpx;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.p-sub {
  margin-top: 6rpx;
  font-size: 21rpx;
  color: #e1251b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.p-meta {
  margin-top: 10rpx;
  display: flex;
  justify-content: space-between;
  font-size: 20rpx;
  color: #9aa0aa;
}

.p-rate {
  color: #f59e0b;
}

.p-bottom {
  margin-top: 12rpx;
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
}

.p-price {
  font-size: 34rpx;
  color: #e1251b;
  font-weight: 800;
}

.p-origin {
  margin-left: 8rpx;
  font-size: 20rpx;
  color: #b0b5bd;
  text-decoration: line-through;
}

.p-store {
  max-width: 140rpx;
  font-size: 19rpx;
  color: #9aa0aa;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.skeleton {
  padding-bottom: 20rpx;
}

.sk-pic {
  height: 300rpx;
  background: #eef1f5;
}

.sk-line {
  height: 24rpx;
  margin: 18rpx 18rpx 0;
  border-radius: 8rpx;
  background: #eef1f5;
}

.sk-line.short {
  width: 50%;
}

.ai-fab {
  position: fixed;
  right: 28rpx;
  bottom: 150rpx;
  width: 100rpx;
  height: 100rpx;
  border-radius: 50%;
  background: linear-gradient(135deg, #e1251b, #ff7a45);
  color: #fff;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  box-shadow: 0 12rpx 28rpx rgba(225, 37, 27, 0.35);
  z-index: 20;
}

.ai-fab-icon {
  font-size: 28rpx;
  font-weight: 800;
  line-height: 1;
}

.ai-fab-text {
  font-size: 18rpx;
  margin-top: 4rpx;
}

.load-more {
  margin: 28rpx 0;
  text-align: center;
  font-size: 26rpx;
  color: #e1251b;
}

.load-end {
  margin: 28rpx 0;
  text-align: center;
  font-size: 22rpx;
  color: #b0b5bd;
}
</style>
