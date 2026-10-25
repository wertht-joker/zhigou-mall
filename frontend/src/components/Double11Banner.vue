<template>
  <div class="d11-banner">
    <span v-for="i in 6" :key="i" class="float-gift" :style="giftStyle(i)">{{ ['🎁', '🛍️', '✨', '🎊', '🧧', '💫'][i - 1] }}</span>

    <div class="d11-left">
      <div class="d11-title-row">
        <span class="d11-logo">11.11</span>
        <span class="d11-name">双十一狂欢购物节</span>
      </div>
      <p class="d11-slogan">全场好物狂欢价 · 满 199 减 30 · AI 客服帮你凑单省更多</p>
      <div class="countdown">
        <span class="cd-label">距开抢仅剩</span>
        <span class="cd-box">{{ days }}</span><i>天</i>
        <span class="cd-box">{{ pad(hours) }}</span><i>时</i>
        <span class="cd-box">{{ pad(minutes) }}</span><i>分</i>
        <span class="cd-box">{{ pad(seconds) }}</span><i>秒</i>
      </div>
      <el-button class="d11-go" round @click="goSearch">立即抢购 →</el-button>
    </div>

    <div class="d11-right">
      <div class="coupon-title">🎟️ 狂欢满减券</div>
      <div
        v-for="c in coupons"
        :key="c.id"
        class="coupon"
        :class="{ claimed: claimed.includes(c.threshold), pop: popping === c.id }"
      >
        <div class="coupon-face">
          <span class="cut"><i>¥</i>{{ c.cut }}</span>
          <span class="cond">满{{ c.threshold }}可用</span>
        </div>
        <button class="coupon-btn" :disabled="claimed.includes(c.threshold)" @click="claim(c)">
          {{ claimed.includes(c.threshold) ? '已领取' : '领取' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import request, { TOKEN_KEY } from '../api'

const router = useRouter()

// 倒计时目标：今年的 11 月 11 日 0 点，若已过则顺延到明年
const target = (() => {
  const now = new Date()
  let t = new Date(now.getFullYear(), 10, 11, 0, 0, 0)
  if (now.getTime() > new Date(now.getFullYear(), 10, 11, 23, 59, 59).getTime()) {
    t = new Date(now.getFullYear() + 1, 10, 11, 0, 0, 0)
  }
  return t.getTime()
})()

const now = ref(Date.now())
let timer = null
onMounted(() => {
  timer = setInterval(() => { now.value = Date.now() }, 1000)
  loadClaimed()
})
onBeforeUnmount(() => clearInterval(timer))

// 已领档位从服务端读取（每档每用户限领一张）
const claimed = ref([])
const popping = ref(null)

async function loadClaimed() {
  if (!localStorage.getItem(TOKEN_KEY)) return
  try {
    const mine = await request.get('/coupons')
    claimed.value = mine.map((c) => c.threshold)
  } catch (e) { /* 未登录等情况忽略 */ }
}

async function claim(c) {
  if (claimed.value.includes(c.threshold)) return
  if (!localStorage.getItem(TOKEN_KEY)) {
    ElMessage.warning('请先登录后领券')
    router.push('/login')
    return
  }
  try {
    await request.post('/coupons/claim', { threshold: c.threshold })
    claimed.value.push(c.threshold)
    popping.value = c.id
    setTimeout(() => { popping.value = null }, 600)
    ElMessage.success(`已领取 满${c.threshold}减${c.cut} 狂欢券 🎉 结算时可直接抵扣`)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

const diff = computed(() => Math.max(0, target - now.value))
const days = computed(() => Math.floor(diff.value / 86400000))
const hours = computed(() => Math.floor(diff.value / 3600000) % 24)
const minutes = computed(() => Math.floor(diff.value / 60000) % 60)
const seconds = computed(() => Math.floor(diff.value / 1000) % 60)
const pad = (n) => String(n).padStart(2, '0')

const coupons = [
  { id: 'c30', threshold: 199, cut: 30 },
  { id: 'c80', threshold: 399, cut: 80 },
  { id: 'c150', threshold: 699, cut: 150 },
]

function giftStyle(i) {
  return {
    left: `${8 + ((i * 16) % 88)}%`,
    top: `${(i * 23) % 60}%`,
    animationDelay: `${(i % 4) * 0.8}s`,
    animationDuration: `${4 + (i % 3)}s`,
    fontSize: `${18 + (i % 3) * 8}px`,
  }
}

function goSearch() {
  router.push({ path: '/search' })
}
</script>

<style scoped>
.d11-banner {
  position: relative; overflow: hidden;
  border-radius: 12px; padding: 34px 44px; color: #fff;
  background: linear-gradient(115deg, #7a0c0c 0%, #c62828 48%, #e64a19 100%);
  box-shadow: 0 6px 24px rgba(198, 40, 40, .28);
  display: flex; justify-content: space-between; align-items: center; gap: 32px;
}
/* 斜向高光带 */
.d11-banner::before {
  content: ''; position: absolute; inset: 0; pointer-events: none;
  background:
    radial-gradient(500px 220px at 88% -30%, rgba(255, 214, 120, .35), transparent 60%),
    radial-gradient(420px 200px at -10% 120%, rgba(255, 138, 76, .3), transparent 60%);
}
.float-gift {
  position: absolute; opacity: .5; pointer-events: none;
  animation: floatY 5s ease-in-out infinite alternate;
}
@keyframes floatY { from { transform: translateY(-6px) rotate(-8deg); } to { transform: translateY(8px) rotate(10deg); } }

.d11-left { position: relative; flex: 1; min-width: 0; }
.d11-title-row { display: flex; align-items: center; gap: 14px; }
.d11-logo {
  font-size: 44px; font-weight: 900; font-style: italic; letter-spacing: 1px;
  background: linear-gradient(180deg, #fff4c9 20%, #ffd04d 60%, #ffab2e);
  -webkit-background-clip: text; background-clip: text; color: transparent;
  filter: drop-shadow(0 2px 6px rgba(0, 0, 0, .35));
  animation: logoPulse 2.4s ease-in-out infinite;
}
@keyframes logoPulse {
  0%, 100% { transform: scale(1); } 50% { transform: scale(1.06); }
}
.d11-name { font-size: 24px; font-weight: 700; text-shadow: 0 2px 8px rgba(0, 0, 0, .3); }
.d11-slogan { margin: 10px 0 18px; font-size: 14px; opacity: .92; }

.countdown { display: flex; align-items: center; gap: 6px; margin-bottom: 20px; }
.cd-label { font-size: 13px; opacity: .85; margin-right: 6px; }
.cd-box {
  min-width: 38px; padding: 5px 6px; text-align: center;
  background: rgba(0, 0, 0, .35); border: 1px solid rgba(255, 210, 130, .55);
  border-radius: 6px; font-size: 18px; font-weight: 700; color: #ffe3a1;
  font-variant-numeric: tabular-nums;
}
.countdown i { font-style: normal; font-size: 12px; opacity: .85; }

.d11-go {
  background: linear-gradient(90deg, #ffd04d, #ffab2e); border: none;
  color: #7a0c0c; font-weight: 700; padding: 20px 28px; font-size: 15px;
  box-shadow: 0 4px 14px rgba(255, 171, 46, .5);
}
.d11-go:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(255, 171, 46, .65); }

.d11-right {
  position: relative; display: flex; flex-direction: column; gap: 10px;
  width: 260px; flex-shrink: 0;
}
.coupon-title { font-size: 14px; font-weight: 700; color: #ffe3a1; text-align: center; }
.coupon {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  background: #fff; border-radius: 10px; padding: 8px 8px 8px 14px;
  border: 1px dashed #ffb74d;
  transition: transform .2s;
}
.coupon.pop { animation: couponPop .5s ease; }
@keyframes couponPop {
  0% { transform: scale(1); } 40% { transform: scale(1.12) rotate(-2deg); } 100% { transform: scale(1); }
}
.coupon.claimed { opacity: .75; }
.coupon-face { display: flex; align-items: baseline; gap: 8px; color: #c62828; }
.coupon-face .cut { font-size: 22px; font-weight: 800; }
.coupon-face .cut i { font-style: normal; font-size: 13px; }
.coupon-face .cond { font-size: 12px; color: #999; }
.coupon-btn {
  border: none; cursor: pointer; border-radius: 999px; padding: 6px 16px;
  font-size: 13px; font-weight: 600; color: #fff;
  background: linear-gradient(90deg, #ff6a00, #e1251b);
}
.coupon-btn:disabled { cursor: default; background: #c0c0c0; color: #fff; }
.coupon-btn:not(:disabled):hover { filter: brightness(1.08); }
</style>
