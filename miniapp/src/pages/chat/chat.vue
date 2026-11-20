<template>
  <view class="chat-page">
    <scroll-view class="msg-list" scroll-y :scroll-into-view="scrollTarget">
      <view v-for="(msg, index) in messages" :id="`msg-${index}`" :key="index" class="msg" :class="msg.role">
        <view v-if="msg.role === 'bot'" class="avatar bot">AI</view>
        <view class="bubble-wrap">
          <view class="bubble">
            <text class="bubble-text">{{ msg.text }}</text>
            <view v-if="msg.sources?.length" class="sources">
              <text class="sources-label">参考资料</text>
              <text v-for="(s, i) in msg.sources.slice(0, 3)" :key="i" class="source">{{ s.doc_name }}</text>
            </view>
          </view>
        </view>
        <view v-if="msg.role === 'user'" class="avatar user">{{ avatarText }}</view>
      </view>

      <view v-if="sending" id="msg-typing" class="msg bot">
        <view class="avatar bot">AI</view>
        <view class="bubble typing">
          <text></text><text></text><text></text>
        </view>
      </view>
    </scroll-view>

    <view v-if="messages.length <= 1" class="quick">
      <view v-for="q in quickQuestions" :key="q" class="quick-item" @tap="askQuick(q)">{{ q }}</view>
    </view>

    <view class="input-bar">
      <input
        v-model="input"
        class="input"
        placeholder="输入问题，例如：怎么开发票？"
        confirm-type="send"
        :disabled="sending"
        @confirm="send"
      />
      <button class="send-btn" :disabled="sending || !input.trim()" @tap="send">发送</button>
    </view>
  </view>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import { http } from '../../api/request'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const input = ref('')
const sending = ref(false)
const sessionId = ref(null)
const scrollTarget = ref('')
const messages = ref([
  {
    role: 'bot',
    text: '你好，我是智购 AI 客服。可以问我商品推荐、售后政策、物流和订单问题。',
    sources: [],
  },
])

const quickQuestions = ['怎么开发票？', '退货运费谁承担？', '推荐一款降噪耳机', '我的订单到哪了？']
const avatarText = computed(() => (auth.user?.username || '我').slice(0, 1).toUpperCase())

function scrollToBottom() {
  nextTick(() => {
    scrollTarget.value = sending.value ? 'msg-typing' : `msg-${messages.value.length - 1}`
  })
}

async function send() {
  const question = input.value.trim()
  if (!question || sending.value) return
  if (!auth.isLogin) {
    uni.navigateTo({ url: '/pages/login/login' })
    return
  }
  messages.value.push({ role: 'user', text: question })
  input.value = ''
  sending.value = true
  scrollToBottom()
  try {
    const data = await http.post('/chat', {
      question,
      session_id: sessionId.value,
    })
    sessionId.value = data.session_id || sessionId.value
    messages.value.push({
      role: 'bot',
      text: data.answer || '抱歉，我暂时没有找到答案。',
      sources: data.sources || [],
    })
  } catch {
    messages.value.push({
      role: 'bot',
      text: '网络有点问题，请稍后再试。',
      sources: [],
    })
  } finally {
    sending.value = false
    scrollToBottom()
  }
}

function askQuick(question) {
  input.value = question
  send()
}
</script>

<style scoped>
.chat-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f6f8;
}

.msg-list {
  flex: 1;
  padding: 24rpx 24rpx 12rpx;
  height: 0;
}

.msg {
  display: flex;
  gap: 14rpx;
  margin-bottom: 24rpx;
  align-items: flex-start;
}

.msg.user {
  justify-content: flex-end;
}

.avatar {
  width: 64rpx;
  height: 64rpx;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22rpx;
  font-weight: 700;
  flex-shrink: 0;
}

.avatar.bot {
  background: linear-gradient(135deg, #e1251b, #ff7a45);
  color: #fff;
}

.avatar.user {
  background: #1f2937;
  color: #fff;
}

.bubble-wrap {
  max-width: 78%;
}

.bubble {
  padding: 20rpx 24rpx;
  border-radius: 4rpx 22rpx 22rpx 22rpx;
  background: #fff;
  box-shadow: 0 4rpx 14rpx rgba(15, 23, 42, 0.05);
}

.msg.user .bubble {
  border-radius: 22rpx 4rpx 22rpx 22rpx;
  background: linear-gradient(135deg, #e1251b, #f05432);
  color: #fff;
}

.bubble-text {
  font-size: 27rpx;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.sources {
  margin-top: 14rpx;
  padding-top: 12rpx;
  border-top: 1rpx dashed #eef0f3;
  display: flex;
  flex-wrap: wrap;
  gap: 8rpx;
}

.sources-label {
  width: 100%;
  font-size: 19rpx;
  color: #9aa0aa;
}

.source {
  padding: 4rpx 12rpx;
  border-radius: 999rpx;
  background: #f3f4f6;
  color: #6b7280;
  font-size: 19rpx;
}

.typing {
  display: flex;
  align-items: center;
  gap: 8rpx;
  height: 56rpx;
}

.typing text {
  width: 10rpx;
  height: 10rpx;
  border-radius: 50%;
  background: #c4c9d1;
  animation: blink 1.2s infinite;
}

.typing text:nth-child(2) {
  animation-delay: 0.2s;
}

.typing text:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes blink {
  0%,
  60%,
  100% {
    opacity: 0.3;
    transform: translateY(0);
  }
  30% {
    opacity: 1;
    transform: translateY(-4rpx);
  }
}

.quick {
  padding: 0 24rpx 16rpx;
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
}

.quick-item {
  padding: 10rpx 20rpx;
  border-radius: 999rpx;
  background: #fff;
  border: 1rpx solid #eef0f3;
  color: #4b5563;
  font-size: 22rpx;
}

.input-bar {
  padding: 16rpx 24rpx calc(16rpx + env(safe-area-inset-bottom));
  background: #fff;
  border-top: 1rpx solid #eef0f3;
  display: flex;
  align-items: center;
  gap: 16rpx;
}

.input {
  flex: 1;
  height: 76rpx;
  padding: 0 24rpx;
  border-radius: 999rpx;
  background: #f5f6f8;
  font-size: 26rpx;
}

.send-btn {
  margin: 0;
  width: 130rpx;
  height: 76rpx;
  line-height: 76rpx;
  border-radius: 999rpx;
  background: linear-gradient(120deg, #e1251b, #ff6a3d);
  color: #fff;
  font-size: 25rpx;
  font-weight: 600;
}

.send-btn::after {
  border: none;
}
</style>
