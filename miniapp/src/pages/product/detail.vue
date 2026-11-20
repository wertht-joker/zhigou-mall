<template>
  <view v-if="product" class="detail-page">
    <view class="pic">
      <image v-if="product.image_url" class="pic-img" :src="imageUrl(product.image_url)" mode="aspectFill" />
      <text v-else class="pic-emoji">{{ product.image || '📦' }}</text>
    </view>

    <view class="card info">
      <view class="price-row">
        <text class="price-now">¥{{ currentPrice }}</text>
        <text v-if="currentOriginalPrice" class="price-origin">¥{{ currentOriginalPrice }}</text>
        <text class="sales">已售 {{ product.sales || 0 }}</text>
      </view>
      <view class="name">{{ product.name }}</view>
      <view class="subtitle">{{ product.subtitle }}</view>

      <view class="meta-row">
        <text>库存 {{ currentStock }} 件</text>
        <text>评分 {{ product.avg_rating || '—' }} ★</text>
        <text>{{ product.review_count || 0 }} 条评价</text>
      </view>

      <view v-if="variants.length" class="variants">
        <view class="block-label">选择版本</view>
        <view class="variant-list">
          <view
            v-for="v in variants"
            :key="v.id"
            class="variant"
            :class="{ active: v.id === selectedVariantId, soldout: v.stock <= 0 }"
            @tap="selectVariant(v)"
          >
            <text class="v-spec">{{ v.spec }}</text>
            <text class="v-price">¥{{ v.price }}</text>
          </view>
        </view>
      </view>

      <view class="qty-row">
        <text class="block-label">购买数量</text>
        <view class="stepper">
          <view class="step" :class="{ disabled: quantity <= 1 }" @tap="changeQty(-1)">−</view>
          <text class="qty">{{ quantity }}</text>
          <view class="step" :class="{ disabled: quantity >= currentStock }" @tap="changeQty(1)">+</view>
        </view>
      </view>

      <view class="store-row">
        <text class="store-icon">🏪</text>
        <text>{{ product.store_name || '智购自营' }}</text>
        <text class="store-badge">{{ (product.store_name || '智购自营').includes('自营') ? '自营发货' : '商家发货' }}</text>
      </view>
    </view>

    <view class="card desc-card">
      <view class="block-label">商品详情</view>
      <text class="desc">{{ product.description || '暂无详情' }}</text>
    </view>

    <view class="service-tip" @tap="goChat">
      <text>🤖 有疑问？点这里问 AI 客服，支持售后政策、查订单、商品推荐</text>
      <text class="arrow">›</text>
    </view>

    <view class="bottom-bar">
      <view class="bar-icon" @tap="goCart">
        <text class="bar-icon-text">🛒</text>
        <text class="bar-icon-label">购物车</text>
      </view>
      <button class="btn-ghost bar-btn" :disabled="currentStock <= 0" @tap="addToCart(false)">加入购物车</button>
      <button class="btn-primary bar-btn" :disabled="currentStock <= 0" @tap="addToCart(true)">立即购买</button>
    </view>
  </view>

  <view v-else-if="loaded" class="empty">商品不存在或已下架</view>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { http } from '../../api/request'
import { imageUrl } from '../../utils/format'
import { useAuthStore } from '../../stores/auth'
import { refreshCartBadge } from '../../utils/cart'

const auth = useAuthStore()
const product = ref(null)
const loaded = ref(false)
const quantity = ref(1)
const selectedVariantId = ref(null)

const variants = computed(() => product.value?.variants || [])
const selectedVariant = computed(
  () => variants.value.find((v) => v.id === selectedVariantId.value) || null,
)
const currentPrice = computed(() => selectedVariant.value?.price ?? product.value?.price ?? 0)
const currentOriginalPrice = computed(
  () => selectedVariant.value?.original_price ?? product.value?.original_price,
)
const currentStock = computed(() => selectedVariant.value?.stock ?? product.value?.stock ?? 0)

async function loadProduct(id) {
  try {
    product.value = await http.get(`/products/${id}`)
    const list = product.value.variants || []
    if (list.length) {
      selectedVariantId.value = (list.find((v) => v.stock > 0) || list[0]).id
    }
  } catch {
    product.value = null
  } finally {
    loaded.value = true
  }
}

function selectVariant(v) {
  if (v.stock <= 0) return
  selectedVariantId.value = v.id
  quantity.value = 1
}

function changeQty(delta) {
  const next = quantity.value + delta
  if (next < 1 || next > currentStock.value) return
  quantity.value = next
}

async function addToCart(buyNow) {
  if (!auth.isLogin) {
    uni.navigateTo({ url: '/pages/login/login' })
    return
  }
  if (variants.value.length && !selectedVariantId.value) {
    uni.showToast({ title: '请选择商品版本', icon: 'none' })
    return
  }
  if (buyNow) {
    // 立即购买：不写购物车，直接带商品/规格/数量去结算页
    const variantPart = selectedVariantId.value ? `&variant_id=${selectedVariantId.value}` : ''
    uni.navigateTo({
      url: `/pages/checkout/checkout?buy_now=1&product_id=${product.value.id}${variantPart}&quantity=${quantity.value}`,
    })
    return
  }
  try {
    uni.showLoading({ title: '加入中' })
    await http.post('/cart/items', {
      product_id: product.value.id,
      variant_id: selectedVariantId.value,
      quantity: quantity.value,
    })
    refreshCartBadge()
    uni.showToast({ title: '已加入购物车', icon: 'success' })
  } catch {
    // 请求层已提示
  } finally {
    uni.hideLoading()
  }
}

function goCart() {
  uni.switchTab({ url: '/pages/cart/cart' })
}

function goChat() {
  uni.navigateTo({ url: '/pages/chat/chat' })
}

onLoad((options) => {
  if (options?.id) loadProduct(options.id)
})
</script>

<style scoped>
.detail-page {
  min-height: 100vh;
  padding-bottom: 160rpx;
}

.pic {
  height: 620rpx;
  background: linear-gradient(135deg, #fdf6f5, #fbeae8);
  display: flex;
  align-items: center;
  justify-content: center;
}

.pic-img {
  width: 100%;
  height: 100%;
}

.pic-emoji {
  font-size: 220rpx;
}

.card {
  margin: 20rpx 24rpx;
  padding: 28rpx;
}

.price-row {
  display: flex;
  align-items: baseline;
  gap: 12rpx;
}

.price-now {
  font-size: 52rpx;
  color: #e1251b;
  font-weight: 800;
}

.price-origin {
  font-size: 24rpx;
  color: #b0b5bd;
  text-decoration: line-through;
}

.sales {
  margin-left: auto;
  font-size: 22rpx;
  color: #9aa0aa;
}

.name {
  margin-top: 16rpx;
  font-size: 36rpx;
  font-weight: 700;
  line-height: 1.4;
}

.subtitle {
  margin-top: 8rpx;
  font-size: 25rpx;
  color: #e1251b;
}

.meta-row {
  margin-top: 20rpx;
  padding: 18rpx 0;
  border-top: 1rpx solid #f4f5f7;
  border-bottom: 1rpx solid #f4f5f7;
  display: flex;
  gap: 28rpx;
  font-size: 22rpx;
  color: #8a8f99;
}

.block-label {
  font-size: 25rpx;
  color: #6b7280;
  font-weight: 600;
  margin-bottom: 14rpx;
}

.variants {
  margin-top: 24rpx;
}

.variant-list {
  display: flex;
  flex-wrap: wrap;
  gap: 16rpx;
}

.variant {
  min-width: 180rpx;
  padding: 14rpx 20rpx;
  border-radius: 16rpx;
  border: 1rpx solid #e5e7eb;
  background: #fafbfc;
  display: flex;
  flex-direction: column;
  gap: 4rpx;
}

.variant.active {
  border-color: #e1251b;
  background: #fff5f3;
}

.variant.soldout {
  opacity: 0.45;
}

.v-spec {
  font-size: 24rpx;
  color: #1f2937;
}

.v-price {
  font-size: 21rpx;
  color: #e1251b;
}

.qty-row {
  margin-top: 28rpx;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.qty-row .block-label {
  margin-bottom: 0;
}

.stepper {
  display: flex;
  align-items: center;
  border: 1rpx solid #e5e7eb;
  border-radius: 12rpx;
  overflow: hidden;
}

.step {
  width: 68rpx;
  height: 60rpx;
  line-height: 60rpx;
  text-align: center;
  background: #f8fafc;
  font-size: 32rpx;
  color: #4b5563;
}

.step.disabled {
  color: #cbd5e1;
}

.qty {
  width: 72rpx;
  text-align: center;
  font-size: 26rpx;
}

.store-row {
  margin-top: 24rpx;
  padding-top: 20rpx;
  border-top: 1rpx solid #f4f5f7;
  display: flex;
  align-items: center;
  gap: 10rpx;
  font-size: 24rpx;
  color: #4b5563;
}

.store-badge {
  margin-left: auto;
  padding: 4rpx 12rpx;
  border-radius: 999rpx;
  background: #fff1f0;
  color: #e1251b;
  font-size: 20rpx;
}

.desc-card {
  line-height: 1.8;
}

.desc {
  font-size: 26rpx;
  color: #4b5563;
  white-space: pre-wrap;
}

.service-tip {
  margin: 0 24rpx;
  padding: 22rpx 26rpx;
  border-radius: 18rpx;
  background: #fff8e6;
  color: #9a6b00;
  font-size: 23rpx;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.arrow {
  font-size: 34rpx;
}

.bottom-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 18rpx 24rpx calc(18rpx + env(safe-area-inset-bottom));
  background: #fff;
  border-top: 1rpx solid #eef0f3;
  display: flex;
  align-items: center;
  gap: 16rpx;
  z-index: 30;
}

.bar-icon {
  width: 90rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  color: #6b7280;
}

.bar-icon-text {
  font-size: 38rpx;
}

.bar-icon-label {
  font-size: 19rpx;
}

.bar-btn {
  flex: 1;
  height: 82rpx;
  line-height: 82rpx;
  padding: 0;
  font-size: 27rpx;
}
</style>
