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
    </div>
    <div class="info">
      <div class="name">{{ product.name }}</div>
      <div class="subtitle">{{ product.subtitle }}</div>
      <div class="rate" v-if="product.review_count">
        <span class="stars" :style="{ color: '#e1251b' }">★ {{ product.avg_rating }}</span>
        <span class="count">{{ product.review_count }}条评价</span>
      </div>
      <div class="rate" v-else><span class="no-review">暂无评价</span></div>
      <div class="bottom">
        <div class="price">¥{{ product.price }}<span v-if="product.original_price" class="origin">¥{{ product.original_price }}</span></div>
        <div class="sales">已售 {{ product.sales }}</div>
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
const imgFailed = ref(false)

function goDetail() {
  router.push(`/product/${props.product.id}`)
}
</script>

<style scoped>
.product-card {
  background: #fff; border-radius: 8px; overflow: hidden; cursor: pointer;
  transition: transform .2s, box-shadow .2s;
  border: 1px solid #f0f0f0;
}
.product-card:hover { transform: translateY(-4px); box-shadow: 0 8px 20px rgba(0,0,0,.08); }
.pic {
  height: 160px; display: flex; align-items: center; justify-content: center;
  font-size: 72px; background: linear-gradient(135deg, #fdf6f5 0%, #fbeae8 100%);
}
.pic img { width: 100%; height: 100%; object-fit: cover; }
.emoji { font-size: 72px; }
.info { padding: 12px 14px 14px; }
.name {
  font-size: 14px; line-height: 20px; height: 40px; overflow: hidden;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
}
.subtitle {
  margin-top: 4px; font-size: 12px; color: #e1251b; height: 18px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rate { margin-top: 6px; display: flex; align-items: baseline; gap: 6px; height: 16px; }
.stars { font-size: 13px; font-weight: 600; }
.count { font-size: 12px; color: #999; }
.no-review { font-size: 12px; color: #ccc; }
.bottom { margin-top: 6px; display: flex; justify-content: space-between; align-items: baseline; }
.price { font-size: 18px; color: #e1251b; }
.origin { margin-left: 6px; font-size: 12px; color: #aaa; text-decoration: line-through; font-weight: 400; }
.sales { font-size: 12px; color: #999; }
.store { margin-top: 6px; font-size: 12px; color: #888; }
</style>
