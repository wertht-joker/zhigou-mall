<template>
  <div class="reviews" v-loading="loading">
    <!-- 统计条 -->
    <div class="stats-bar" v-if="stats.total">
      <div class="score">
        <div class="avg">{{ stats.avg_rating }}</div>
        <el-rate :model-value="stats.avg_rating" disabled allow-half />
        <div class="total">共 {{ stats.total }} 条评价</div>
      </div>
      <div class="dist">
        <div class="pos">好评率 {{ stats.positive_rate }}%</div>
        <div v-for="star in [5, 4, 3, 2, 1]" :key="star" class="dist-row">
          <span class="star-label">{{ star }} 星</span>
          <el-progress
            :percentage="pct(star)"
            :stroke-width="8"
            :show-text="false"
            color="#e1251b"
          />
          <span class="star-count">{{ stats.per_star[star] || 0 }}</span>
        </div>
      </div>
    </div>
    <div class="stats-empty" v-else-if="!loading">暂无评价，快来抢首评吧～</div>

    <!-- 评价列表 -->
    <div v-for="r in items" :key="r.id" class="review-item">
      <div class="head">
        <span class="avatar">{{ r.username.slice(0, 1) }}</span>
        <span class="username">{{ r.username }}</span>
        <el-rate :model-value="r.rating" disabled size="small" />
      </div>
      <div class="content">{{ r.content }}</div>
      <div class="product-line" v-if="r.product_name">购买商品：{{ r.product_name }}</div>
      <div class="reply" v-if="r.reply">
        <span class="reply-tag">商家回复</span>{{ r.reply }}
      </div>
      <div class="time">{{ formatTime(r.created_at) }}</div>
    </div>

    <div class="more" v-if="items.length < total">
      <el-button text type="primary" :loading="loading" @click="loadMore">查看更多评价</el-button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import request from '../api'

const props = defineProps({
  productId: { type: [Number, String], required: true },
})

const stats = ref({ total: 0, avg_rating: 0, per_star: {}, positive_rate: 100 })
const items = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)

function pct(star) {
  if (!stats.value.total) return 0
  return Math.round(((stats.value.per_star[star] || 0) / stats.value.total) * 100)
}

function formatTime(t) {
  return t ? String(t).replace('T', ' ').slice(0, 10) : ''
}

async function load(append = false) {
  loading.value = true
  try {
    const data = await request.get(`/products/${props.productId}/reviews`, {
      params: { page: page.value, page_size: 5 },
    })
    stats.value = data.stats
    total.value = data.total
    items.value = append ? items.value.concat(data.items) : data.items
  } catch {
    // 评价区加载失败不阻塞详情页
  } finally {
    loading.value = false
  }
}

function loadMore() {
  page.value += 1
  load(true)
}

function reload() {
  page.value = 1
  load(false)
}

defineExpose({ reload })
onMounted(() => load())
</script>

<style scoped>
.stats-bar {
  display: flex; gap: 40px; padding: 16px 20px; margin-bottom: 16px;
  background: #fafafa; border-radius: 8px;
}
.score { text-align: center; min-width: 120px; }
.avg { font-size: 32px; color: #e1251b; font-weight: 700; line-height: 1.2; }
.total { font-size: 12px; color: #999; margin-top: 6px; }
.dist { flex: 1; max-width: 380px; }
.pos { font-size: 13px; color: #e1251b; margin-bottom: 8px; }
.dist-row { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
.star-label { font-size: 12px; color: #999; width: 32px; }
.dist-row .el-progress { flex: 1; }
.star-count { font-size: 12px; color: #999; width: 24px; text-align: right; }
.stats-empty { color: #999; font-size: 13px; padding: 12px 0; }

.review-item { padding: 14px 4px; border-bottom: 1px solid #f5f5f5; }
.head { display: flex; align-items: center; gap: 8px; }
.avatar {
  width: 28px; height: 28px; border-radius: 50%; background: #fdeae8;
  color: #e1251b; font-size: 14px; display: flex; align-items: center; justify-content: center;
}
.username { font-size: 13px; color: #666; }
.content { margin-top: 8px; font-size: 14px; color: #333; line-height: 1.7; }
.product-line { margin-top: 6px; font-size: 12px; color: #bbb; }
.reply {
  margin-top: 10px; background: #fff8f0; border-radius: 6px; padding: 8px 12px;
  font-size: 13px; color: #8a5a2b; line-height: 1.6;
}
.reply-tag {
  display: inline-block; margin-right: 8px; padding: 0 6px; border-radius: 3px;
  background: #f5a623; color: #fff; font-size: 11px; line-height: 18px;
}
.time { margin-top: 6px; font-size: 12px; color: #ccc; }
.more { text-align: center; padding-top: 10px; }
</style>
