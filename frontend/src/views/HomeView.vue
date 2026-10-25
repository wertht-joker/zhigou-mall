<template>
  <div class="home">
    <!-- 促销 Banner：618 ↔ 双11 自动轮播（悬停暂停） -->
    <div class="banner-wrap" @mouseenter="pauseRotate" @mouseleave="resumeRotate">
      <transition name="banner-swap" mode="out-in">
        <Double11Banner v-if="showD11" key="d11" />
        <div v-else key="normal" class="banner">
          <div class="banner-text">
            <h2>618 品质购物节</h2>
            <p>数码家电至高立减 400 · AI 客服全天在线答疑</p>
            <el-button type="primary" round @click="goSearch('')">立即逛逛 →</el-button>
          </div>
          <div class="banner-deco">🎉🛒🎁</div>
        </div>
      </transition>
      <!-- 两侧箭头手动切换 + 轮播指示点 -->
      <button class="banner-arrow left" title="上一个活动" @click="switchBanner(!showD11)">‹</button>
      <button class="banner-arrow right" title="下一个活动" @click="switchBanner(!showD11)">›</button>
      <div class="banner-dots">
        <span :class="{ active: !showD11 }" @click="switchBanner(false)"></span>
        <span :class="{ active: showD11 }" @click="switchBanner(true)"></span>
      </div>
    </div>

    <!-- 分类导航 -->
    <div class="category-nav">
      <div
        v-for="c in categories"
        :key="c.id"
        class="category-item"
        :class="{ active: c.id === activeCategory }"
        @click="pickCategory(c.id)"
      >
        <span class="cat-icon">{{ c.icon }}</span>
        <span>{{ c.name }}</span>
      </div>
    </div>

    <!-- 商品区标题 -->
    <div class="section-title">
      <h3>{{ activeCategoryName }} · 热销商品</h3>
      <el-link type="primary" @click="goSearch(keyword)">查看更多</el-link>
    </div>

    <!-- 商品瀑布 -->
    <div class="product-grid" v-loading="loading">
      <ProductCard v-for="p in products" :key="p.id" :product="p" />
    </div>
    <el-empty v-if="!loading && products.length === 0" description="该分类暂无在售商品" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import request from '../api'
import ProductCard from '../components/ProductCard.vue'
import Double11Banner from '../components/Double11Banner.vue'

const router = useRouter()
const categories = ref([])
const products = ref([])
const loading = ref(false)
const activeCategory = ref(null)
const keyword = ref('')

// 活动横幅自动轮播：618 ↔ 双11 每 6 秒来回切换，悬停暂停
const showD11 = ref(false)
let rotateTimer = null
function startRotate() {
  clearInterval(rotateTimer)
  rotateTimer = setInterval(() => { showD11.value = !showD11.value }, 6000)
}
function pauseRotate() { clearInterval(rotateTimer) }
function resumeRotate() { startRotate() }
function switchBanner(toD11) {
  showD11.value = toD11
  startRotate()
}
onBeforeUnmount(() => clearInterval(rotateTimer))

const activeCategoryName = computed(() => {
  const c = categories.value.find((c) => c.id === activeCategory.value)
  return c ? c.name : '为你推荐'
})

async function loadCategories() {
  try {
    categories.value = await request.get('/product-categories')
  } catch (e) { /* 忽略 */ }
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

function pickCategory(id) {
  activeCategory.value = activeCategory.value === id ? null : id
  loadProducts()
}

function goSearch(q) {
  router.push({ path: '/search', query: q ? { q } : {} })
}

onMounted(() => {
  loadCategories()
  loadProducts()
  startRotate()
})
</script>

<style scoped>
.banner {
  background: linear-gradient(120deg, #e1251b 0%, #ff6e40 100%);
  border-radius: 12px; padding: 40px 48px; color: #fff;
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 20px;
}
.banner-text h2 { font-size: 30px; margin-bottom: 8px; }
.banner-text p { opacity: .9; margin-bottom: 20px; font-size: 14px; }
.banner-deco { font-size: 64px; letter-spacing: 8px; }

/* 轮播容器与指示点 */
.banner-wrap { position: relative; margin-bottom: 20px; }
.banner-wrap .banner,
.banner-wrap :deep(.d11-banner) { margin-bottom: 0; }
/* 两侧圆形箭头（骑在横幅左右边缘，垂直居中） */
.banner-arrow {
  position: absolute; top: 50%; transform: translateY(-50%); z-index: 3;
  width: 38px; height: 38px; border-radius: 50%; border: none; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  padding: 0 0 5px; /* 箭头字符光学居中 */
  background: rgba(0, 0, 0, .28); color: #fff; font-size: 28px; line-height: 1;
  opacity: .6; transition: opacity .25s, background .25s, transform .25s;
}
.banner-arrow.left { left: -18px; }
.banner-arrow.right { right: -18px; }
.banner-arrow:hover { opacity: 1; background: rgba(0, 0, 0, .5); transform: translateY(-50%) scale(1.1); }
.banner-swap-btn:hover { background: rgba(0, 0, 0, .4); transform: scale(1.05); }
.banner-dots {
  position: absolute; bottom: 14px; left: 50%; transform: translateX(-50%);
  display: flex; gap: 8px; z-index: 3;
}
.banner-dots span {
  width: 24px; height: 4px; border-radius: 2px; cursor: pointer;
  background: rgba(255, 255, 255, .45); transition: background .3s, width .3s;
}
.banner-dots span.active { background: #ffd04d; width: 36px; }

/* 活动横幅来回切换动画（横向滑动） */
.banner-swap-enter-active { transition: opacity .45s ease, transform .45s ease; }
.banner-swap-leave-active { transition: opacity .3s ease, transform .3s ease; }
.banner-swap-enter-from { opacity: 0; transform: translateX(60px); }
.banner-swap-leave-to { opacity: 0; transform: translateX(-60px); }

.category-nav {
  background: #fff; border-radius: 8px; padding: 12px;
  display: flex; gap: 8px; margin-bottom: 20px; overflow-x: auto;
}
.category-item {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 18px; border-radius: 6px; cursor: pointer;
  font-size: 14px; color: #444; white-space: nowrap;
  border: 1px solid transparent;
}
.category-item:hover { background: #fcedea; }
.category-item.active { background: #fcedea; color: #e1251b; border-color: #f3b8b3; font-weight: 600; }
.cat-icon { font-size: 18px; }

.section-title { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-title h3 { font-size: 18px; }

.product-grid {
  display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px;
}
@media (max-width: 1100px) { .product-grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 700px) { .product-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
