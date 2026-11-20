<template>
  <div class="product-card" @click="goDetail">
    <div class="pic">
      <img
        v-if="product.image_url && !imgFailed"
        :src="product.image_url"
        :alt="product.name"
        loading="lazy"
        @error="imgFailed = true"
      />
      <span v-else class="emoji">{{ product.image }}</span>
      <span class="store-badge" :class="{ own: isSelf }">{{ isSelf ? '自营' : '第三方' }}</span>
    </div>
    <div class="info">
      <div class="name">{{ product.name }}</div>
      <div class="subtitle">{{ product.subtitle }}</div>
      <div class="rate">
        <template v-if="product.review_count">
          <span class="stars">★ {{ product.avg_rating }}</span>
          <span class="count">{{ product.review_count }} 条评价</span>
        </template>
        <span v-else class="no-review">暂无评价</span>
        <span class="sales">已售 {{ product.sales }}</span>
      </div>
      <div class="bottom">
        <div class="price">
          <span class="unit">¥</span>{{ product.price }}
          <span v-if="product.original_price" class="origin">¥{{ product.original_price }}</span>
        </div>
      </div>
      <div class="store">🏪 {{ storeName }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  product: { type: Object, required: true },
})
const router = useRouter()
const storeName = computed(() => props.product.store_name || '智购自营')
const isSelf = computed(() => storeName.value === '智购自营')
const imgFailed = ref(false)

function goDetail() {
  router.push(`/product/${props.product.id}`)
}
</script>

<style scoped>
.product-card {
  background: #fff;
  border-radius: var(--radius-md);
  overflow: hidden;
  cursor: pointer;
  border: 1px solid var(--line);
  transition: transform .22s ease, box-shadow .22s ease, border-color .22s ease;
  display: flex;
  flex-direction: column;
}
.product-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 18px 36px rgba(15, 23, 42, .1);
  border-color: rgba(255, 77, 79, .22);
}
.pic {
  position: relative;
  height: 180px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 72px;
  background: linear-gradient(135deg, #fff7f3 0%, #ffece7 100%);
  overflow: hidden;
}
.pic img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform .35s ease;
}
.product-card:hover .pic img { transform: scale(1.05); }
.emoji { font-size: 72px; }
.store-badge {
  position: absolute;
  top: 10px;
  left: 10px;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  background: rgba(15, 23, 42, .62);
  backdrop-filter: blur(6px);
}
.store-badge.own { background: var(--brand-gradient); }
.info { padding: 12px 14px 14px; display: flex; flex-direction: column; gap: 4px; }
.name {
  font-size: 14px;
  line-height: 20px;
  height: 40px;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  color: var(--ink);
  font-weight: 500;
}
.subtitle {
  font-size: 12px;
  color: var(--brand);
  height: 18px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rate { display: flex; align-items: center; gap: 8px; height: 18px; font-size: 12px; }
.stars { color: #f59e0b; font-weight: 600; }
.count, .sales { color: var(--muted); }
.sales { margin-left: auto; }
.no-review { color: #c0c4cc; }
.bottom { margin-top: 2px; }
.price {
  color: var(--brand);
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -.02em;
  line-height: 1.2;
}
.unit { font-size: 13px; font-weight: 700; margin-right: 1px; }
.origin {
  margin-left: 6px;
  font-size: 12px;
  color: #aaa;
  text-decoration: line-through;
  font-weight: 400;
}
.store {
  margin-top: 2px;
  font-size: 12px;
  color: var(--muted);
  padding-top: 8px;
  border-top: 1px dashed var(--line);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
