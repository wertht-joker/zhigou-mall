<template>
  <svg
    class="payment-icon"
    :width="size"
    :height="size"
    viewBox="0 0 40 40"
    role="img"
    :aria-label="label"
  >
    <template v-if="type === 'alipay'">
      <rect width="40" height="40" rx="10" fill="#1677FF" />
      <text
        x="20" y="28"
        text-anchor="middle"
        font-size="24"
        font-weight="700"
        font-family="'PingFang SC','Microsoft YaHei',sans-serif"
        fill="#fff"
      >支</text>
    </template>

    <template v-else-if="type === 'wechat'">
      <rect width="40" height="40" rx="10" fill="#07C160" />
      <path
        d="M16.5 9C10.7 9 6 12.9 6 17.7c0 2.7 1.5 5.1 3.9 6.7l-.9 3.3 3.8-1.8c1 .3 2.1.5 3.2.5.4 0 .8 0 1.2-.1-.3-.8-.4-1.7-.4-2.6 0-4.4 4.2-8 9.4-8 .4 0 .8 0 1.2.1C26.1 12 21.8 9 16.5 9z"
        fill="#fff"
      />
      <path
        d="M26.5 17.6c-4.4 0-8 3.1-8 6.9s3.6 6.9 8 6.9c.9 0 1.8-.1 2.6-.4l2.9 1.4-.7-2.5c1.9-1.3 3.1-3.3 3.1-5.4 0-3.8-3.6-6.9-7.9-6.9z"
        fill="#fff"
      />
      <circle cx="12.8" cy="16" r="1.3" fill="#07C160" />
      <circle cx="20.2" cy="16" r="1.3" fill="#07C160" />
      <circle cx="23.8" cy="23.4" r="1.1" fill="#07C160" />
      <circle cx="29.2" cy="23.4" r="1.1" fill="#07C160" />
    </template>

    <template v-else-if="type === 'unionpay'">
      <rect width="40" height="40" rx="10" fill="#fff" />
      <path d="M6 26.5 12.5 7h8.2l-6.5 19.5z" fill="#E60012" />
      <path d="M15.3 26.5 21.8 7h8.2l-6.5 19.5z" fill="#005BAC" />
      <path d="M24.6 26.5 31.1 7h3.2c1.4 0 2.2 1.1 1.7 2.5l-5.5 16.9z" fill="#009944" />
      <rect x="4" y="29" width="32" height="3" rx="1.5" fill="#e5e7eb" />
    </template>

    <template v-else>
      <rect width="40" height="40" rx="10" fill="#eef2ff" />
      <rect x="7" y="11" width="26" height="18" rx="4" fill="#4f46e5" />
      <rect x="7" y="16" width="26" height="4" fill="#312e81" />
      <rect x="12" y="24" width="9" height="2.5" rx="1.25" fill="#c7d2fe" />
    </template>
  </svg>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  type: { type: String, default: 'card' },
  size: { type: Number, default: 28 },
})

const label = computed(() => ({
  alipay: '支付宝',
  wechat: '微信支付',
  unionpay: '银联',
}[props.type] || '银行卡'))
</script>

<style scoped>
.payment-icon { display: inline-block; vertical-align: middle; flex-shrink: 0; }
</style>
