<template>
  <div class="detail" v-if="product">
    <div class="detail-main">
      <div class="pic">
        <img
          v-if="product.image_url && !imgFailed"
          :src="product.image_url"
          :alt="product.name"
          @error="imgFailed = true"
        />
        <span v-else class="emoji">{{ product.image }}</span>
      </div>
      <div class="info">
        <h2 class="name">{{ product.name }}</h2>
        <p class="subtitle">{{ product.subtitle }}</p>

        <div class="price-box">
          <div class="price-line">
            <span class="label">价格</span>
            <span class="price big">¥{{ currentPrice }}</span>
            <span v-if="currentOriginalPrice" class="origin">¥{{ currentOriginalPrice }}</span>
          </div>
          <div class="meta-line">
            <span>销量 {{ product.sales }}</span>
            <span>库存 {{ currentStock }} 件</span>
            <span v-if="product.review_count" class="rate-link" @click="scrollToReviews">
              评分 {{ product.avg_rating }} ★（{{ product.review_count }} 条评价）
            </span>
          </div>
        </div>

        <div v-if="variants.length" class="variant-box">
          <span class="label">版本</span>
          <div class="variant-options">
            <button
              v-for="v in variants"
              :key="v.id"
              type="button"
              class="variant-chip"
              :class="{ active: v.id === selectedVariantId, soldout: v.stock <= 0 }"
              :disabled="v.stock <= 0"
              @click="selectVariant(v)"
            >
              <span class="v-spec">{{ v.spec }}</span>
              <span class="v-price">¥{{ v.price }}</span>
            </button>
          </div>
        </div>

        <div class="buy-box">
          <div class="qty">
            <span class="label">数量</span>
            <el-input-number v-model="quantity" :min="1" :max="Math.max(currentStock, 1)" />
          </div>
          <div class="actions">
            <el-button size="large" plain type="primary" :disabled="currentStock <= 0" @click="addToCart(false)">🛒 加入购物车</el-button>
            <el-button size="large" type="primary" :disabled="currentStock <= 0" @click="addToCart(true)">立即购买</el-button>
          </div>
        </div>

        <div class="service-tip">
          💡 有疑问？点击右下角「AI 客服」即可咨询售后政策、查订单、求推荐
        </div>
      </div>
    </div>

    <div class="detail-desc">
      <h3>商品详情</h3>
      <p class="desc-text">{{ product.description || '暂无详情' }}</p>
    </div>

    <div class="detail-reviews" ref="reviewsRef">
      <h3>商品评价（{{ product.review_count || 0 }}）</h3>
      <ProductReviews v-if="product" ref="reviewsComp" :product-id="product.id" />
    </div>
  </div>
  <el-empty v-else-if="loaded" description="商品不存在或已下架" />
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import request, { TOKEN_KEY } from '../api'
import ProductReviews from '../components/ProductReviews.vue'

const emit = defineEmits(['cart-updated'])
const route = useRoute()
const router = useRouter()
const product = ref(null)
const loaded = ref(false)
const quantity = ref(1)
const imgFailed = ref(false)
const reviewsRef = ref(null)
const reviewsComp = ref(null)
const selectedVariantId = ref(null)

const variants = computed(() => product.value?.variants || [])
const selectedVariant = computed(
  () => variants.value.find((v) => v.id === selectedVariantId.value) || null
)
// 有规格时价格/库存跟随所选规格；无规格回退商品自身
const currentPrice = computed(() => selectedVariant.value?.price ?? product.value?.price ?? 0)
const currentOriginalPrice = computed(
  () => selectedVariant.value?.original_price ?? product.value?.original_price
)
const currentStock = computed(() => selectedVariant.value?.stock ?? product.value?.stock ?? 0)

onMounted(async () => {
  try {
    product.value = await request.get(`/products/${route.params.id}`)
    const list = product.value.variants || []
    if (list.length) {
      selectedVariantId.value = (list.find((v) => v.stock > 0) || list[0]).id
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loaded.value = true
  }
})

function selectVariant(variant) {
  if (variant.stock <= 0) return
  selectedVariantId.value = variant.id
  quantity.value = 1
}

function scrollToReviews() {
  reviewsRef.value?.scrollIntoView({ behavior: 'smooth' })
}

async function addToCart(buyNow) {
  if (!localStorage.getItem(TOKEN_KEY)) {
    return router.push({ path: '/login', query: { redirect: route.fullPath } })
  }
  if (variants.value.length && !selectedVariantId.value) {
    return ElMessage.warning('请选择商品版本')
  }
  if (buyNow) {
    // 立即购买：不写购物车，直接带商品/规格/数量去结算页
    return router.push({
      path: '/checkout',
      query: {
        buy_now: '1',
        product_id: String(product.value.id),
        variant_id: selectedVariantId.value ? String(selectedVariantId.value) : '',
        quantity: String(quantity.value),
      },
    })
  }
  try {
    await request.post('/cart/items', {
      product_id: product.value.id,
      variant_id: selectedVariantId.value,
      quantity: quantity.value,
    })
    emit('cart-updated')
    ElMessage.success('已加入购物车')
  } catch (e) {
    ElMessage.error(e.message)
  }
}
</script>

<style scoped>
.detail-main {
  background: #fff; border-radius: 8px; padding: 32px;
  display: flex; gap: 40px; margin-bottom: 14px;
}
.pic {
  width: 360px; height: 360px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 150px; background: linear-gradient(135deg, #fdf6f5 0%, #fbeae8 100%);
  border-radius: 8px; overflow: hidden;
}
.pic img { width: 100%; height: 100%; object-fit: cover; }
.emoji { font-size: 150px; }
.info { flex: 1; display: flex; flex-direction: column; }
.name { font-size: 22px; line-height: 1.4; }
.subtitle { color: #e1251b; margin-top: 8px; font-size: 13px; }

.price-box {
  background: linear-gradient(120deg, #fcedea 0%, #fdf3f1 100%);
  border-radius: 8px; padding: 18px 20px; margin: 20px 0;
}
.price-line { display: flex; align-items: baseline; gap: 10px; }
.label { color: #999; font-size: 12px; margin-right: 8px; }
.price.big { font-size: 30px; }
.origin { color: #aaa; text-decoration: line-through; font-size: 14px; }
.meta-line { margin-top: 8px; display: flex; gap: 24px; color: #999; font-size: 12px; }
.rate-link { color: #e1251b; cursor: pointer; }
.rate-link:hover { text-decoration: underline; }

.variant-box { display: flex; align-items: flex-start; margin-bottom: 20px; }
.variant-options { display: flex; flex-wrap: wrap; gap: 10px; }
.variant-chip {
  display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
  padding: 8px 14px; border-radius: 12px; cursor: pointer;
  background: #fff; border: 1.5px solid #eee;
  transition: border-color .2s ease, box-shadow .2s ease, transform .2s ease;
  font-family: inherit;
}
.variant-chip:hover:not(.soldout) { border-color: #ffb4a8; transform: translateY(-1px); }
.variant-chip.active {
  border-color: var(--brand);
  background: var(--brand-soft);
  box-shadow: 0 6px 16px rgba(255, 77, 79, .14);
}
.variant-chip.soldout { color: #ccc; cursor: not-allowed; background: #fafafa; }
.v-spec { font-size: 13px; font-weight: 600; }
.v-price { font-size: 12px; color: var(--brand); }
.variant-chip.soldout .v-price { color: #ccc; }

.qty { display: flex; align-items: center; margin-bottom: 20px; }
.actions { display: flex; gap: 12px; }
.actions .el-button { width: 180px; font-size: 15px; }

.service-tip {
  margin-top: auto; padding-top: 16px; color: #999; font-size: 12px;
}

.detail-desc { background: #fff; border-radius: 8px; padding: 20px 24px; margin-bottom: 14px; }
.detail-desc h3 { font-size: 16px; margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid #f0f0f0; }
.desc-text { color: #555; line-height: 1.8; font-size: 14px; }

.detail-reviews { background: #fff; border-radius: 8px; padding: 20px 24px; }
.detail-reviews h3 { font-size: 16px; margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid #f0f0f0; }
</style>
