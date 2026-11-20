<template>
  <div class="cart-page">
    <div class="page-card">
      <div class="header-row">
        <h3>🛒 我的购物车</h3>
        <el-button v-if="items.length" text type="danger" @click="clearAll">清空购物车</el-button>
      </div>

      <template v-if="items.length">
        <div class="cart-list">
          <div v-for="item in items" :key="item.id" class="cart-item">
            <el-checkbox v-model="item.checked" @change="refreshTotal" />
            <div class="item-pic">{{ item.product?.image || '📦' }}</div>
            <div class="item-info" @click="goDetail(item)">
              <div class="item-name">{{ item.product?.name || '（商品已失效）' }}</div>
              <div v-if="item.variant" class="item-spec">版本：{{ item.variant.spec }}</div>
              <div class="item-sub">{{ item.product?.subtitle }}</div>
            </div>
            <div class="item-price price">¥{{ priceOf(item) }}</div>
            <el-input-number
              v-if="item.product"
              v-model="item.quantity"
              :min="1"
              :max="Math.max(stockOf(item), 1)"
              size="small"
              @change="changeQty(item)"
            />
            <el-button text type="danger" size="small" @click="removeItem(item)">删除</el-button>
          </div>
        </div>

        <div class="checkout-bar">
          <div class="total">
            已选 <b>{{ checkedCount }}</b> 件，合计：
            <span class="price big">¥{{ total.toFixed(2) }}</span>
          </div>
          <el-button type="primary" size="large" :disabled="!checkedCount" @click="goCheckout">
            去结算
          </el-button>
        </div>
      </template>
      <el-empty v-else description="购物车还是空的，去逛逛吧～">
        <el-button type="primary" @click="$router.push('/')">去逛逛</el-button>
      </el-empty>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../api'

const emit = defineEmits(['cart-updated'])
const router = useRouter()
const items = ref([])

const checkedCount = computed(() => items.value.filter((i) => i.checked && i.product).length)
const total = computed(() =>
  items.value
    .filter((i) => i.checked && i.product)
    .reduce((sum, i) => sum + priceOf(i) * i.quantity, 0)
)

// 后端已按规格返回成交单价与可购库存
function priceOf(item) {
  return item.unit_price ?? item.variant?.price ?? item.product?.price ?? 0
}

function stockOf(item) {
  return item.stock ?? item.variant?.stock ?? item.product?.stock ?? 0
}

function refreshTotal() { /* checked 变化由 computed 自动响应 */ }

async function loadCart() {
  try {
    items.value = (await request.get('/cart')).map((i) => ({ ...i, checked: true }))
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function goDetail(item) {
  if (item.product) router.push(`/product/${item.product_id}`)
}

async function changeQty(item) {
  try {
    const fresh = await request.put(`/cart/items/${item.id}`, { quantity: item.quantity })
    syncItem(item, fresh)
    emit('cart-updated')
  } catch (e) {
    ElMessage.error(e.message)
    loadCart()
  }
}

async function removeItem(item) {
  try {
    const fresh = await request.request({ method: 'DELETE', url: '/cart/items', data: [item.id] })
    items.value = fresh.map((i) => ({ ...i, checked: i.checked ?? true }))
    emit('cart-updated')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function clearAll() {
  await ElMessageBox.confirm('确认清空购物车？', '提示', { type: 'warning' })
  try {
    await request.request({ method: 'DELETE', url: '/cart/items', data: null })
    items.value = []
    emit('cart-updated')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function syncItem(local, freshList) {
  const target = freshList.find((i) => i.id === local.id)
  if (target) local.quantity = target.quantity
}

async function goCheckout() {
  const ids = items.value.filter((i) => i.checked && i.product).map((i) => i.id)
  router.push({ path: '/checkout', query: { items: ids.join(',') } })
}

onMounted(loadCart)
</script>

<style scoped>
.page-card { background: #fff; border-radius: 8px; padding: 20px 24px; }
.header-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }

.cart-item {
  display: flex; align-items: center; gap: 14px;
  padding: 16px 0; border-bottom: 1px solid #f5f5f5;
}
.item-pic {
  width: 72px; height: 72px; border-radius: 6px; font-size: 40px;
  background: #faf6f5; display: flex; align-items: center; justify-content: center;
}
.item-info { flex: 1; cursor: pointer; min-width: 0; }
.item-name { font-size: 14px; }
.item-name:hover { color: #e1251b; }
.item-spec {
  display: inline-block; margin-top: 4px; padding: 1px 8px;
  font-size: 12px; color: #666; background: #f5f5f7; border-radius: 999px;
}
.item-sub { font-size: 12px; color: #999; margin-top: 4px; }
.item-price { width: 90px; font-size: 16px; }

.checkout-bar {
  margin-top: 20px; display: flex; justify-content: flex-end;
  align-items: center; gap: 24px;
}
.total { font-size: 14px; color: #666; }
.price.big { font-size: 24px; }
</style>
