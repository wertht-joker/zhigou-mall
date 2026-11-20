<template>
  <view class="checkout-page">
    <view class="card section">
      <view class="section-head">
        <text class="section-title">收货地址</text>
        <text class="link" @tap="toggleAddressForm">{{ showAddressForm ? '取消新增' : '新增地址' }}</text>
      </view>

      <view v-if="addresses.length" class="address-list">
        <view
          v-for="addr in addresses"
          :key="addr.id"
          class="address"
          :class="{ active: selectedAddress === addr.id }"
          @tap="selectedAddress = addr.id"
        >
          <view class="addr-top">
            <text class="addr-name">{{ addr.receiver }}</text>
            <text class="addr-phone">{{ addr.phone }}</text>
            <text v-if="addr.is_default" class="default-tag">默认</text>
          </view>
          <view class="addr-detail">{{ addr.region }} {{ addr.detail }}</view>
        </view>
      </view>
      <view v-else-if="!showAddressForm" class="empty-addr">还没有收货地址，请先新增</view>

      <view v-if="showAddressForm" class="addr-form">
        <view class="form-row">
          <text class="form-label">收货人</text>
          <input v-model="newAddress.receiver" class="form-input" placeholder="请输入姓名" />
        </view>
        <view class="form-row">
          <text class="form-label">手机号</text>
          <input v-model="newAddress.phone" class="form-input" type="number" maxlength="11" placeholder="11 位手机号" />
        </view>
        <view class="form-row">
          <text class="form-label">地区</text>
          <input v-model="newAddress.region" class="form-input" placeholder="省 市 区，如：浙江省 杭州市 西湖区" />
        </view>
        <view class="form-row">
          <text class="form-label">详细地址</text>
          <input v-model="newAddress.detail" class="form-input" placeholder="街道、门牌号、小区、楼栋" />
        </view>
        <view class="form-row">
          <text class="form-label">设为默认</text>
          <switch :checked="newAddress.is_default" color="#e1251b" @change="onDefaultChange" />
        </view>
        <button class="btn-primary save-addr" :loading="savingAddress" @tap="saveAddress">保存地址</button>
      </view>
    </view>

    <view class="card section">
      <view class="section-head">
        <text class="section-title">商品清单</text>
        <text class="count">{{ orderItems.length }} 件</text>
      </view>

      <view v-for="item in orderItems" :key="item.id || item.product?.id" class="order-item">
        <view class="item-pic">
          <image v-if="item.product?.image_url" class="item-img" :src="imageUrl(item.product.image_url)" mode="aspectFill" />
          <text v-else>{{ item.product?.image || '📦' }}</text>
        </view>
        <view class="item-info">
          <view class="item-name">{{ item.product?.name }}</view>
          <view v-if="item.variant" class="item-spec">版本：{{ item.variant.spec }}</view>
          <view class="item-price">¥{{ money(priceOf(item)) }} × {{ item.quantity }}</view>
        </view>
        <text class="item-total">¥{{ money(priceOf(item) * item.quantity) }}</text>
      </view>
    </view>

    <view class="card section summary">
      <view class="summary-row">
        <text>商品金额</text>
        <text>¥{{ money(subtotal) }}</text>
      </view>
      <view class="summary-row">
        <text>运费</text>
        <text class="free">包邮</text>
      </view>
      <view class="coupon-row">
        <text class="coupon-label">优惠券</text>
        <view class="coupon-list">
          <view
            v-for="c in usableCoupons"
            :key="c.id"
            class="coupon-chip"
            :class="{ active: selectedCouponId === c.id }"
            @tap="toggleCoupon(c.id)"
          >
            满{{ c.threshold }}减{{ c.discount }}
          </view>
          <text v-if="!usableCoupons.length" class="coupon-empty">暂无可用券</text>
        </view>
      </view>
      <view class="summary-row total">
        <text>应付金额</text>
        <text class="total-price">¥{{ total }}</text>
      </view>
    </view>

    <view class="submit-bar">
      <view class="submit-total">
        <text class="submit-label">合计</text>
        <text class="submit-price">¥{{ total }}</text>
      </view>
      <button class="btn-primary submit-btn" :loading="submitting" @tap="submitOrder">提交订单</button>
    </view>
  </view>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { http } from '../../api/request'
import { imageUrl, money, priceOf } from '../../utils/format'
import { useAuthStore } from '../../stores/auth'
import { refreshCartBadge } from '../../utils/cart'

const auth = useAuthStore()
const wantedIds = ref([])
const buyNow = ref(false)
const buyNowItem = ref(null)
const addresses = ref([])
const cartItems = ref([])
const selectedAddress = ref(null)
const submitting = ref(false)
const showAddressForm = ref(false)
const savingAddress = ref(false)
const newAddress = reactive({
  receiver: '',
  phone: '',
  region: '',
  detail: '',
  is_default: false,
})

const orderItems = computed(() => {
  if (buyNow.value) return buyNowItem.value ? [buyNowItem.value] : []
  const ids = wantedIds.value
  if (ids.length) return cartItems.value.filter((i) => ids.includes(i.id) && i.product)
  return cartItems.value.filter((i) => i.product)
})

const subtotal = computed(() =>
  orderItems.value
    .reduce((sum, i) => sum + priceOf(i) * i.quantity, 0),
)

const myCoupons = ref([])
const selectedCouponId = ref(0)
// 可用券：未使用且门槛不超过当前商品金额
const usableCoupons = computed(() =>
  myCoupons.value.filter((c) => c.status === 'unused' && c.threshold <= subtotal.value),
)
const activeCoupon = computed(
  () => usableCoupons.value.find((c) => c.id === selectedCouponId.value) || null,
)
const discount = computed(() => activeCoupon.value?.discount || 0)

const total = computed(() =>
  Math.max(subtotal.value - discount.value, 0).toFixed(2),
)

function toggleCoupon(id) {
  selectedCouponId.value = selectedCouponId.value === id ? 0 : id
}

async function loadBuyNowItem(options) {
  const productId = Number(options?.product_id)
  if (!productId) return
  const product = await http.get(`/products/${productId}`)
  const variantId = options?.variant_id ? Number(options.variant_id) : null
  const variant = (product.variants || []).find((v) => v.id === variantId) || null
  const quantity = Number(options?.quantity) || 1
  buyNowItem.value = {
    id: null,
    product,
    variant,
    quantity,
    unit_price: variant ? variant.price : product.price,
    stock: variant ? variant.stock : product.stock,
  }
}

async function load(options) {
  try {
    const [addrList, couponList] = await Promise.all([
      http.get('/addresses'),
      http.get('/coupons'),
    ])
    addresses.value = addrList || []
    myCoupons.value = couponList || []
    if (buyNow.value) {
      await loadBuyNowItem(options)
    } else {
      cartItems.value = (await http.get('/cart')) || []
    }
    // 默认选中当前金额下抵扣最大的一张券
    if (usableCoupons.value.length) {
      selectedCouponId.value = usableCoupons.value[0].id
    }
    if (addresses.value.length) {
      selectedAddress.value = (addresses.value.find((a) => a.is_default) || addresses.value[0]).id
    } else {
      showAddressForm.value = true
    }
  } catch {
    // 请求层已提示
  }
}

function toggleAddressForm() {
  showAddressForm.value = !showAddressForm.value
}

function onDefaultChange(e) {
  newAddress.is_default = !!e.detail.value
}

async function saveAddress() {
  if (!newAddress.receiver.trim()) return uni.showToast({ title: '请填写收货人', icon: 'none' })
  if (!/^\d{6,20}$/.test(newAddress.phone.trim())) {
    return uni.showToast({ title: '请填写正确的手机号', icon: 'none' })
  }
  if (!newAddress.detail.trim()) return uni.showToast({ title: '请填写详细地址', icon: 'none' })
  savingAddress.value = true
  try {
    const created = await http.post('/addresses', {
      receiver: newAddress.receiver.trim(),
      phone: newAddress.phone.trim(),
      region: newAddress.region.trim(),
      detail: newAddress.detail.trim(),
      is_default: newAddress.is_default,
    })
    addresses.value = await http.get('/addresses')
    selectedAddress.value = created?.id
      || (addresses.value.find((a) => a.is_default) || addresses.value[0])?.id
    showAddressForm.value = false
    newAddress.receiver = ''
    newAddress.phone = ''
    newAddress.region = ''
    newAddress.detail = ''
    newAddress.is_default = false
    uni.showToast({ title: '地址已保存', icon: 'success' })
  } catch {
    // 请求层已提示
  } finally {
    savingAddress.value = false
  }
}

async function submitOrder() {
  if (!selectedAddress.value) {
    return uni.showToast({ title: '请选择收货地址', icon: 'none' })
  }
  if (!orderItems.value.length) {
    return uni.showToast({ title: '没有可结算的商品', icon: 'none' })
  }
  submitting.value = true
  try {
    const payload = {
      address_id: selectedAddress.value,
      coupon_id: activeCoupon.value?.id || null,
    }
    if (buyNow.value) {
      payload.buy_now = {
        product_id: buyNowItem.value.product.id,
        variant_id: buyNowItem.value.variant?.id ?? null,
        quantity: buyNowItem.value.quantity,
      }
    } else {
      payload.cart_item_ids = wantedIds.value.length
        ? wantedIds.value
        : orderItems.value.map((i) => i.id)
    }
    const order = await http.post('/orders', payload)
    if (!buyNow.value) refreshCartBadge()
    uni.showToast({ title: '下单成功', icon: 'success' })
    setTimeout(() => {
      uni.switchTab({ url: '/pages/orders/orders' })
    }, 600)
    console.log('创建订单', order?.order_no)
  } catch {
    // 请求层已提示
  } finally {
    submitting.value = false
  }
}

onLoad((options) => {
  if (!auth.isLogin) {
    uni.navigateTo({ url: '/pages/login/login' })
    return
  }
  buyNow.value = options?.buy_now === '1'
  wantedIds.value = String(options?.items || '')
    .split(',')
    .filter(Boolean)
    .map(Number)
  load(options)
})
</script>

<style scoped>
.checkout-page {
  min-height: 100vh;
  padding: 24rpx 24rpx 180rpx;
}

.section {
  margin-bottom: 20rpx;
  padding: 28rpx;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20rpx;
}

.section-title {
  font-size: 30rpx;
  font-weight: 700;
}

.link {
  font-size: 24rpx;
  color: #e1251b;
}

.count {
  font-size: 22rpx;
  color: #9aa0aa;
}

.address-list {
  display: flex;
  flex-direction: column;
  gap: 16rpx;
}

.address {
  padding: 20rpx 22rpx;
  border-radius: 18rpx;
  border: 2rpx solid #eef0f3;
  background: #fafbfc;
}

.address.active {
  border-color: #e1251b;
  background: #fff7f5;
}

.addr-top {
  display: flex;
  align-items: center;
  gap: 14rpx;
}

.addr-name {
  font-size: 27rpx;
  font-weight: 700;
}

.addr-phone {
  font-size: 24rpx;
  color: #6b7280;
}

.default-tag {
  padding: 2rpx 10rpx;
  border-radius: 999rpx;
  background: #e1251b;
  color: #fff;
  font-size: 18rpx;
}

.addr-detail {
  margin-top: 8rpx;
  font-size: 24rpx;
  color: #6b7280;
  line-height: 1.5;
}

.empty-addr {
  padding: 24rpx 0;
  font-size: 24rpx;
  color: #9aa0aa;
}

.addr-form {
  margin-top: 12rpx;
  padding-top: 16rpx;
  border-top: 1rpx solid #f1f2f4;
}

.form-row {
  display: flex;
  align-items: center;
  min-height: 82rpx;
  border-bottom: 1rpx solid #f4f5f7;
}

.form-label {
  width: 150rpx;
  font-size: 24rpx;
  color: #6b7280;
}

.form-input {
  flex: 1;
  font-size: 25rpx;
}

.save-addr {
  margin-top: 22rpx;
  height: 76rpx;
  line-height: 76rpx;
  font-size: 26rpx;
}

.order-item {
  display: flex;
  align-items: center;
  gap: 16rpx;
  padding: 16rpx 0;
  border-bottom: 1rpx solid #f4f5f7;
}

.order-item:last-child {
  border-bottom: none;
}

.item-pic {
  width: 100rpx;
  height: 100rpx;
  border-radius: 14rpx;
  background: #faf6f5;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 48rpx;
  overflow: hidden;
}

.item-img {
  width: 100%;
  height: 100%;
}

.item-info {
  flex: 1;
  min-width: 0;
}

.item-name {
  font-size: 26rpx;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.item-spec {
  display: inline-block;
  margin-top: 6rpx;
  padding: 2rpx 10rpx;
  border-radius: 999rpx;
  background: #f3f4f6;
  color: #6b7280;
  font-size: 19rpx;
}

.item-price {
  margin-top: 8rpx;
  font-size: 22rpx;
  color: #9aa0aa;
}

.item-total {
  font-size: 26rpx;
  font-weight: 600;
}

.summary-row {
  display: flex;
  justify-content: space-between;
  padding: 10rpx 0;
  font-size: 25rpx;
  color: #4b5563;
}

.coupon-row {
  display: flex;
  align-items: flex-start;
  gap: 18rpx;
  padding: 14rpx 0;
  border-top: 1rpx solid #f4f5f7;
  font-size: 25rpx;
  color: #4b5563;
}

.coupon-label {
  flex-shrink: 0;
  line-height: 48rpx;
}

.coupon-list {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
}

.coupon-chip {
  padding: 6rpx 16rpx;
  border-radius: 10rpx;
  border: 1rpx solid #f0c4bf;
  color: #e1251b;
  background: #fff7f5;
  font-size: 22rpx;
}

.coupon-chip.active {
  background: #e1251b;
  border-color: #e1251b;
  color: #fff;
}

.coupon-empty {
  font-size: 22rpx;
  color: #9aa0aa;
  line-height: 48rpx;
}

.free {
  color: #16a34a;
}

.summary-row.total {
  margin-top: 8rpx;
  padding-top: 18rpx;
  border-top: 1rpx solid #f1f2f4;
  font-size: 27rpx;
  font-weight: 600;
  color: #1f2937;
}

.total-price {
  font-size: 38rpx;
  color: #e1251b;
  font-weight: 800;
}

.submit-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  height: 120rpx;
  padding: 0 24rpx calc(0rpx + env(safe-area-inset-bottom));
  background: #fff;
  border-top: 1rpx solid #eef0f3;
  display: flex;
  align-items: center;
  gap: 20rpx;
  z-index: 20;
}

.submit-total {
  flex: 1;
  display: flex;
  align-items: baseline;
  gap: 8rpx;
}

.submit-label {
  font-size: 23rpx;
  color: #6b7280;
}

.submit-price {
  font-size: 40rpx;
  color: #e1251b;
  font-weight: 800;
}

.submit-btn {
  width: 240rpx;
  height: 78rpx;
  line-height: 78rpx;
  font-size: 27rpx;
}
</style>
