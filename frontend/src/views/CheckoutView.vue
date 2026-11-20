<template>
  <div class="checkout">
    <!-- 收货地址 -->
    <div class="section">
      <h3>📦 收货地址 <router-link to="/addresses" class="manage-link">管理地址 ›</router-link></h3>
      <div class="address-list">
        <div
          v-for="a in addresses"
          :key="a.id"
          class="address-card"
          :class="{ selected: a.id === selectedAddress }"
          @click="selectedAddress = a.id"
        >
          <div class="addr-line"><b>{{ a.receiver }}</b> {{ a.phone }}</div>
          <div class="addr-detail">{{ a.region }} {{ a.detail }}</div>
          <el-tag v-if="a.is_default" size="small" type="danger" effect="plain">默认</el-tag>
        </div>
        <div class="address-card add-card" @click="addrDialog = true">
          <div class="add-icon">＋</div>
          <div>新增收货地址</div>
        </div>
      </div>
    </div>

    <!-- 商品清单 -->
    <div class="section">
      <h3>🧾 商品清单</h3>
      <div v-for="i in orderItems" :key="i.id ?? i.product?.id" class="order-item">
        <div class="oi-pic">{{ i.product?.image || '📦' }}</div>
        <div class="oi-info">
          <div>{{ i.product?.name }}</div>
          <div v-if="i.variant" class="oi-spec">版本：{{ i.variant.spec }}</div>
          <div class="oi-sub">{{ i.product?.subtitle }}</div>
        </div>
        <div>¥{{ priceOf(i) }} × {{ i.quantity }}</div>
        <div class="price oi-total">¥{{ (priceOf(i) * i.quantity).toFixed(2) }}</div>
      </div>
    </div>

    <!-- 优惠券 -->
    <div class="section">
      <h3>🎟️ 优惠券</h3>
      <div class="coupon-row">
        <el-select v-model="selectedCouponId" placeholder="请选择优惠券" clearable style="width: 340px">
          <el-option label="不使用优惠券" :value="0" />
          <el-option
            v-for="c in usableCoupons"
            :key="c.id"
            :label="`满${c.threshold}减${c.discount} · ${c.title}`"
            :value="c.id"
          />
        </el-select>
        <span v-if="!usableCoupons.length" class="coupon-hint">
          暂无可用券：双11 狂欢满减券 满 199 减 30，去首页领取 →
        </span>
        <span v-else-if="discount > 0" class="coupon-hint hit">已选券抵扣 ¥{{ discount.toFixed(2) }}</span>
      </div>
    </div>

    <!-- 提交栏 -->
    <div class="submit-bar">
      <div class="total">
        共 <b>{{ orderItems.length }}</b> 种商品<template v-if="discount > 0">，券抵扣 <b class="cut">-¥{{ discount.toFixed(2) }}</b></template>，应付总额：
        <span class="price big">¥{{ finalTotal.toFixed(2) }}</span>
      </div>
      <el-button type="primary" size="large" :loading="submitting" :disabled="!selectedAddress || orderItems.length === 0" @click="submitOrder">
        提交订单
      </el-button>
    </div>

    <!-- 新增地址弹窗（共享组件：省市区级联 + 自动定位） -->
    <AddressFormDialog v-model="addrDialog" @saved="onAddressSaved" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import request from '../api'
import AddressFormDialog from '../components/AddressFormDialog.vue'

const emit = defineEmits(['cart-updated'])
const route = useRoute()
const router = useRouter()

const addresses = ref([])
const selectedAddress = ref(null)
const cartItems = ref([])
const submitting = ref(false)
const addrDialog = ref(false)
const myCoupons = ref([])
const selectedCouponId = ref(0)

// 立即购买模式：绕过购物车，直接结算单个商品
const buyNow = computed(() => route.query.buy_now === '1')
const buyNowItem = ref(null)

// 勾选的购物车条目（从购物车页带过来；空则默认全部）
const wantedIds = computed(() =>
  (route.query.items || '').split(',').filter(Boolean).map(Number)
)
const orderItems = computed(() => {
  if (buyNow.value) return buyNowItem.value ? [buyNowItem.value] : []
  return wantedIds.value.length
    ? cartItems.value.filter((i) => wantedIds.value.includes(i.id) && i.product)
    : cartItems.value.filter((i) => i.product)
})
const total = computed(() =>
  orderItems.value.reduce((sum, i) => sum + priceOf(i) * i.quantity, 0)
)

// 后端购物车条目已按规格返回成交单价
function priceOf(item) {
  return item.unit_price ?? item.variant?.price ?? item.product?.price ?? 0
}

// 可用券：未使用且门槛不超过当前金额；金额变化导致不满足时自动失效
const usableCoupons = computed(() =>
  myCoupons.value.filter((c) => c.status === 'unused' && c.threshold <= total.value)
)
const activeCoupon = computed(() =>
  usableCoupons.value.find((c) => c.id === selectedCouponId.value) || null
)
const discount = computed(() => activeCoupon.value?.discount ?? 0)
const finalTotal = computed(() => Math.max(total.value - discount.value, 0))

async function loadBuyNowItem() {
  const productId = Number(route.query.product_id)
  if (!productId) return
  const product = await request.get(`/products/${productId}`)
  const variantId = route.query.variant_id ? Number(route.query.variant_id) : null
  const variant = (product.variants || []).find((v) => v.id === variantId) || null
  const quantity = Number(route.query.quantity) || 1
  buyNowItem.value = {
    id: null,
    product,
    variant,
    quantity,
    unit_price: variant ? variant.price : product.price,
    stock: variant ? variant.stock : product.stock,
  }
}

async function load() {
  try {
    const [addrs, coupons] = await Promise.all([
      request.get('/addresses'),
      request.get('/coupons'),
    ])
    addresses.value = addrs
    myCoupons.value = coupons
    if (buyNow.value) {
      await loadBuyNowItem()
    } else {
      cartItems.value = await request.get('/cart')
    }
    if (addrs.length) {
      selectedAddress.value = (addrs.find((a) => a.is_default) || addrs[0]).id
    }
    // 默认帮用户选抵扣最大的一张（可手动改）
    if (usableCoupons.value.length) {
      selectedCouponId.value = usableCoupons.value[0].id
    }
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function onAddressSaved() {
  const addrs = await request.get('/addresses')
  addresses.value = addrs
  selectedAddress.value = (addrs.find((a) => a.is_default) || addrs[0]).id
}

async function submitOrder() {
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
    const order = await request.post('/orders', payload)
    ElMessage.success(
      discount.value > 0
        ? `下单成功！订单号 ${order.order_no}（券已抵扣 ¥${discount.value.toFixed(2)}）`
        : `下单成功！订单号 ${order.order_no}`
    )
    if (!buyNow.value) emit('cart-updated')
    router.push('/orders')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.section { background: #fff; border-radius: 8px; padding: 20px 24px; margin-bottom: 14px; }
.section h3 { margin-bottom: 14px; }
.manage-link { margin-left: 12px; font-size: 13px; font-weight: 400; color: #e1251b; }

.address-list { display: flex; gap: 12px; flex-wrap: wrap; }
.address-card {
  width: 240px; border: 2px solid #eee; border-radius: 8px; padding: 12px 14px;
  cursor: pointer; position: relative; font-size: 13px;
}
.address-card:hover { border-color: #f3b8b3; }
.address-card.selected { border-color: #e1251b; background: #fffafa; }
.addr-line { margin-bottom: 6px; }
.addr-detail { color: #666; margin-bottom: 6px; line-height: 1.5; }
.add-card {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  color: #999; gap: 4px; border-style: dashed;
}
.add-icon { font-size: 24px; color: #ccc; }

.order-item {
  display: flex; align-items: center; gap: 14px; padding: 12px 0;
  border-bottom: 1px solid #f5f5f5; font-size: 14px;
}
.oi-pic {
  width: 56px; height: 56px; border-radius: 6px; font-size: 30px;
  background: #faf6f5; display: flex; align-items: center; justify-content: center;
}
.oi-info { flex: 1; }
.oi-spec {
  display: inline-block; margin-top: 4px; padding: 1px 8px;
  font-size: 12px; color: #666; background: #f5f5f7; border-radius: 999px;
}
.oi-sub { font-size: 12px; color: #999; margin-top: 4px; }
.oi-total { width: 90px; text-align: right; }

.submit-bar {
  background: #fff; border-radius: 8px; padding: 16px 24px;
  display: flex; justify-content: flex-end; align-items: center; gap: 24px;
  position: sticky; bottom: 16px; box-shadow: 0 -2px 12px rgba(0,0,0,.05);
}
.total b { color: #e1251b; }
.total b.cut { color: #ff6a00; }
.price.big { font-size: 26px; }

.coupon-row { display: flex; align-items: center; gap: 14px; }
.coupon-hint { font-size: 13px; color: #999; }
.coupon-hint.hit { color: #ff6a00; font-weight: 600; }
</style>
