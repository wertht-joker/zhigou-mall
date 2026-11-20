<template>
  <!-- 悬浮按钮 -->
  <div v-show="!visible" class="chat-fab" @click="visible = true">
    🤖<span class="fab-badge">AI客服</span>
  </div>

  <!-- 客服面板 -->
  <div v-show="visible" class="chat-panel">
    <div class="chat-header">
      <div class="header-title">
        <span class="bot-avatar">🤖</span>
        <div>
          <div class="title-main">智购 AI 客服</div>
          <div class="title-sub">7×24 小时在线 · 查订单 / 推荐商品 / 售后政策</div>
        </div>
      </div>
      <div class="header-actions">
        <el-button text size="small" title="新对话" @click="newChat">🔄</el-button>
        <el-button text size="small" title="收起" @click="visible = false">—</el-button>
      </div>
    </div>

    <div class="chat-body" ref="chatBody">
      <div v-if="messages.length === 0" class="empty-tip">
        <div class="empty-icon">👋</div>
        <div>您好，我是智购 AI 客服</div>
        <div class="empty-sub">可以帮我查订单、推荐商品、咨询售后政策</div>
        <div class="suggest">
          <el-tag v-for="q in suggestions" :key="q" class="suggest-tag" @click="ask(q)">{{ q }}</el-tag>
        </div>
      </div>

      <div v-for="(msg, i) in messages" :key="i" class="msg-row" :class="msg.role">
        <div class="avatar">{{ msg.role === 'user' ? '🧑' : '🤖' }}</div>
        <div class="msg-content">
          <!-- Agent 工具调用步骤 -->
          <div v-if="msg.role === 'assistant' && msg.steps && msg.steps.length" class="steps">
            <div v-for="(s, k) in msg.steps" :key="k" class="step-pill">✓ {{ s }}</div>
          </div>
          <div class="bubble">
            <span v-if="msg.role === 'user'">{{ msg.content }}</span>
            <span v-else class="rich" v-html="renderRich(msg.content)"></span><span v-if="msg.streaming" class="cursor">▌</span>
          </div>

          <!-- 可信回答校验：证据不足 / 有句子未找到依据时提示转人工 -->
          <div v-if="msg.role === 'assistant' && msg.verify && msg.verify.message"
               class="verify-bar" :class="msg.verify.low_confidence ? 'warn' : 'ok'">
            <span class="vb-icon">{{ msg.verify.low_confidence ? '⚠️' : '🛡️' }}</span>
            <span class="vb-text">{{ msg.verify.message }}</span>
          </div>

          <!-- 商品推荐卡片（导购工具结果） -->
          <div v-if="msg.role === 'assistant' && msg.products && msg.products.length" class="cards">
            <div v-for="p in msg.products" :key="p.id" class="rec-card" @click="goProduct(p.id)">
              <div class="rec-pic">
                <img v-if="p.image_url" :src="p.image_url" :alt="p.name" loading="lazy" />
                <span v-else>{{ p.image }}</span>
              </div>
              <div class="rec-info">
                <div class="rec-name">{{ p.name }}</div>
                <div class="rec-meta">
                  <span class="rec-price">¥{{ p.price }}</span>
                  <span v-if="p.review_count" class="rec-rate">★{{ p.avg_rating }}</span>
                </div>
                <div class="rec-store">{{ p.store_name }} · 已售{{ p.sales }}</div>
              </div>
            </div>
          </div>

          <!-- 订单卡片（查单工具结果） -->
          <div v-if="msg.role === 'assistant' && msg.orders && msg.orders.length" class="orders">
            <div v-for="o in msg.orders" :key="o.order_no" class="order-chip">
              <div class="oc-head">
                <span class="oc-no">{{ o.order_no }}</span>
                <el-tag size="small" :type="orderTagType(o.status)">{{ o.status }}</el-tag>
              </div>
              <div class="oc-items">
                <span v-for="(it, j) in o.items" :key="j" class="oc-item">
                  <span v-if="it.image_url"><img class="oc-pic" :src="it.image_url" alt="" /></span>
                  <span v-else class="oc-pic">{{ it.image }}</span>
                  {{ it.name }}×{{ it.quantity }}
                </span>
              </div>
              <div class="oc-foot">
                <span class="oc-total">¥{{ o.total_amount }}</span>
                <span v-if="o.logistics" class="oc-logi">🚚 {{ o.logistics }}</span>
              </div>
            </div>
          </div>

          <!-- 售后操作确认卡片（Agent 只生成提案，必须用户点击确认才执行） -->
          <div v-if="msg.role === 'assistant' && msg.actions && msg.actions.length" class="actions">
            <div v-for="a in msg.actions" :key="a.token" class="action-card" :class="a.uiState">
              <div class="ac-head">
                <span class="ac-title">{{ a.title }}</span>
                <span class="ac-badge">{{ actionBadge(a) }}</span>
              </div>
              <div class="ac-summary">{{ a.summary }}</div>
              <div v-if="a.details && a.details.length" class="ac-details">
                <div v-for="(d, j) in a.details" :key="j" class="ac-row">
                  <span class="ac-label">{{ d.label }}</span>
                  <span class="ac-value">{{ d.value }}</span>
                </div>
              </div>
              <div v-if="a.uiState === 'pending' || a.uiState === 'executing'" class="ac-btns">
                <el-button size="small" type="primary" :loading="a.uiState === 'executing'"
                           @click="confirmAction(a)">确认执行</el-button>
                <el-button size="small" :disabled="a.uiState === 'executing'"
                           @click="cancelAction(a)">取消</el-button>
              </div>
              <div v-else class="ac-result" :class="a.uiState">{{ a.resultText }}</div>
              <div v-if="a.uiState === 'pending'" class="ac-hint">确认后立即执行 · 5 分钟内有效</div>
            </div>
          </div>

          <!-- 本次检索链路（自适应路由 + 缓存命中） -->
          <div v-if="msg.role === 'assistant' && msg.route" class="route-badge">
            <el-tag size="small" effect="plain" :type="routeTagType(msg.route.strategy)">
              链路：{{ routeLabel(msg.route.strategy) }}
            </el-tag>
            <span v-if="msg.retrieval && msg.retrieval.cache === 'semantic'" class="route-note">
              语义缓存命中 {{ Math.round((msg.retrieval.similarity || 0) * 100) }}%
            </span>
            <span v-else-if="msg.retrieval && msg.retrieval.elapsed_ms != null" class="route-note">
              检索 {{ msg.retrieval.elapsed_ms }} ms
            </span>
          </div>

          <!-- 引用来源（知识库检索结果） -->
          <div v-if="msg.role === 'assistant' && msg.sources && msg.sources.length" class="sources">
            <el-collapse>
              <el-collapse-item :title="`📎 依据来源（${msg.sources.length} 条）`">
                <div v-for="(s, j) in msg.sources" :key="j" class="source-item">
                  <div class="source-doc">
                    📄 {{ s.doc_name }}
                    <el-tag v-if="s.version" size="small" type="info">v{{ s.version }}</el-tag>
                    <span v-if="s.effective_from" class="source-effective">
                      {{ String(s.effective_from).slice(0, 10) }} 生效
                    </span>
                    <el-tag v-if="s.verdict" size="small" :type="sourceTagType(s.verdict)">
                      {{ sourceVerdictText(s.verdict) }}
                    </el-tag>
                  </div>
                  <div class="source-text">{{ s.text }}</div>
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>

          <!-- 逐句校验明细：每一句答案是否能在引用中找到依据 -->
          <div v-if="msg.role === 'assistant' && msg.verify && msg.verify.claims && msg.verify.claims.length"
               class="verify-detail">
            <el-collapse>
              <el-collapse-item :title="`🔍 逐句校验（${msg.verify.supported}/${msg.verify.total} 句有依据）`">
                <div v-for="(c, j) in msg.verify.claims" :key="j" class="claim-row" :class="c.verdict">
                  <span class="claim-icon">{{ claimIcon(c.verdict) }}</span>
                  <span class="claim-text">{{ c.text }}</span>
                  <span class="claim-score">{{ Math.round((c.confidence || 0) * 100) }}%</span>
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>

          <!-- 反馈 -->
          <div v-if="msg.role === 'assistant' && msg.messageId && !msg.streaming" class="feedback">
            <span class="fb-btn" @click="feedback(msg.messageId, 'up')">👍 有帮助</span>
            <span class="fb-btn" @click="feedback(msg.messageId, 'down')">👎 没解决</span>
          </div>
        </div>
      </div>
    </div>

    <div class="chat-footer">
      <el-input
        v-model="input"
        placeholder="请描述您的问题，例如：我的订单到哪了？"
        @keyup.enter="send"
        :disabled="loading"
      />
      <el-button type="primary" @click="send" :loading="loading">发送</el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import request, { TOKEN_KEY } from '../api'

const router = useRouter()
const visible = ref(false)
const messages = ref([])
const input = ref('')
const loading = ref(false)
const sessionId = ref(null)
const chatBody = ref(null)

const suggestions = [
  '我买的订单到哪了？',
  '退货退款多久能到账？',
  '推荐一款降噪耳机',
  '会员积分怎么用？',
]

/** 富文本渲染：先转义 HTML，再渲染 **加粗** / `片段` / 商品名高亮，换行交给 pre-wrap */
function renderRich(text) {
  if (!text) return ''
  const escaped = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return escaped
    .replace(/\*\*([^*]+)\*\*/g, '<strong class="rk">$1</strong>')
    .replace(/`([^`]+)`/g, '<code class="rc">$1</code>')
    .replace(/(ZG\d{10,})/g, '<span class="rn">$1</span>')
}

function orderTagType(status) {
  return { 待付款: 'warning', 待发货: 'primary', 已发货: 'success', 已完成: 'info', 已取消: 'danger' }[status] || 'info'
}

function actionBadge(a) {
  return {
    pending: '待确认', executing: '执行中', done: '已执行',
    cancelled: '已取消', failed: '未执行',
  }[a.uiState] || '待确认'
}

function sourceVerdictText(verdict) {
  return {
    supported: '已支撑', partial: '部分支撑',
    unsupported: '无依据', unused: '未引用',
  }[verdict] || verdict
}

function sourceTagType(verdict) {
  return { supported: 'success', partial: 'warning', unsupported: 'danger', unused: 'info' }[verdict] || 'info'
}

function routeLabel(strategy) {
  return {
    none: '无需检索',
    vector: '向量召回',
    hybrid: '混合检索',
    hybrid_rerank: '混合检索 + 精排',
    auto: '默认链路',
  }[strategy] || strategy
}

function routeTagType(strategy) {
  return {
    none: 'info',
    vector: 'success',
    hybrid: 'warning',
    hybrid_rerank: 'warning',
    auto: 'info',
  }[strategy] || 'info'
}

function claimIcon(verdict) {
  return { supported: '✓', partial: '◐', unsupported: '✗' }[verdict] || '?'
}

/** 幂等键：同一次确认的多次重试复用同一个值，后端据此识别重复请求 */
function newIdempotencyKey() {
  if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID()
  return 'ik-' + Date.now() + '-' + Math.random().toString(16).slice(2)
}

async function confirmAction(a) {
  if (a.uiState !== 'pending') return
  if (!sessionId.value) {
    ElMessage.warning('请等待本轮回答完成后再确认')
    return
  }
  a.idempotencyKey = a.idempotencyKey || newIdempotencyKey()
  a.uiState = 'executing'
  scrollBottom()
  try {
    const data = await request.post(`/aftersale/actions/${a.token}/confirm`, {
      session_id: sessionId.value,
      idempotency_key: a.idempotencyKey,
    })
    a.uiState = 'done'
    a.resultText = data.message || '操作已执行'
    ElMessage.success('操作已执行')
  } catch (e) {
    a.uiState = 'failed'
    a.resultText = e.message
  }
  scrollBottom()
}

async function cancelAction(a) {
  if (a.uiState !== 'pending') return
  if (!sessionId.value) {
    ElMessage.warning('请等待本轮回答完成后再确认')
    return
  }
  try {
    const data = await request.post(`/aftersale/actions/${a.token}/cancel`, {
      session_id: sessionId.value,
    })
    a.uiState = 'cancelled'
    a.resultText = data.message || '已取消，未产生任何变更'
  } catch (e) {
    ElMessage.error(e.message)
  }
  scrollBottom()
}

function goProduct(id) {
  visible.value = false
  router.push(`/product/${id}`)
}

function scrollBottom() {
  nextTick(() => {
    if (chatBody.value) chatBody.value.scrollTop = chatBody.value.scrollHeight
  })
}

function newChat() {
  messages.value = []
  sessionId.value = null
}

async function ask(q) {
  input.value = q
  await send()
}

async function feedback(messageId, type) {
  try {
    await request.post('/feedback', { message_id: messageId, type })
    ElMessage.success('感谢您的反馈')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function send() {
  const q = input.value.trim()
  if (!q || loading.value) return
  input.value = ''
  messages.value.push({ role: 'user', content: q })
  const aiMsg = {
    role: 'assistant', content: '', sources: [], steps: [],
    products: [], orders: [], actions: [], verify: null,
    route: null, retrieval: null,
    messageId: null, streaming: true,
  }
  messages.value.push(aiMsg)
  loading.value = true
  visible.value = true
  scrollBottom()

  try {
    const token = localStorage.getItem(TOKEN_KEY)
    const resp = await fetch('/api/v1/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
      body: JSON.stringify({ question: q, session_id: sessionId.value }),
    })
    // 建流前的鉴权/参数错误会以普通 JSON 4xx 返回，需先判断 resp.ok
    if (!resp.ok) {
      let msg = '请求失败'
      try { msg = (await resp.json()).message || msg } catch (e) {}
      throw new Error(msg)
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop() || ''
      for (const part of parts) {
        const line = part.trim()
        if (line.startsWith('data:')) {
          try { handleEvent(JSON.parse(line.slice(5).trim()), aiMsg) } catch (e) {}
        }
      }
    }
  } catch (e) {
    ElMessage.error(e.message)
    aiMsg.content = aiMsg.content || '请求失败：' + e.message
  } finally {
    loading.value = false
    aiMsg.streaming = false
    scrollBottom()
  }
}

function handleEvent(event, aiMsg) {
  if (event.type === 'meta') {
    aiMsg.sources = event.sources
    aiMsg.route = event.route || null
    aiMsg.retrieval = event.retrieval || null
    sessionId.value = event.session_id
    if (event.message_id) aiMsg.messageId = event.message_id
  } else if (event.type === 'step') {
    // Agent 调用工具的中间步骤，实时追加展示
    aiMsg.steps.push(event.label)
    scrollBottom()
  } else if (event.type === 'products') {
    // 导购工具的结构化结果 → 商品卡片
    if (event.items && event.items.length) aiMsg.products.push(...event.items)
    scrollBottom()
  } else if (event.type === 'orders') {
    // 查单工具的结构化结果 → 订单卡片
    if (event.items && event.items.length) aiMsg.orders.push(...event.items)
    scrollBottom()
  } else if (event.type === 'action') {
    // 写操作提案 → 确认卡片（默认待确认，点击后调用独立确认接口）
    if (event.action) {
      aiMsg.actions.push({ ...event.action, uiState: 'pending', resultText: '', idempotencyKey: '' })
    }
    scrollBottom()
  } else if (event.type === 'verify') {
    // 可信回答校验：把引用级 verdict 合并回来源列表，并展示低置信提示
    aiMsg.verify = event
    const byKey = {}
    for (const s of event.sources || []) byKey[`${s.doc_id}:${s.chunk_index}`] = s
    for (const s of aiMsg.sources || []) {
      const v = byKey[`${s.doc_id}:${s.chunk_index}`]
      if (v) {
        s.verdict = v.verdict
        s.confidence = v.confidence
      }
    }
    scrollBottom()
  } else if (event.type === 'delta') {
    aiMsg.content += event.content
    scrollBottom()
  } else if (event.type === 'done') {
    if (event.message_id) aiMsg.messageId = event.message_id
  }
}

onMounted(() => {
  // 首次进入商城页面自动展开客服（只弹一次）
  if (!sessionStorage.getItem('zg_chat_opened')) {
    visible.value = true
    sessionStorage.setItem('zg_chat_opened', '1')
  }
})
</script>

<style scoped>
/* 悬浮按钮 */
.chat-fab {
  position: fixed; right: 24px; bottom: 32px; z-index: 2000;
  width: 60px; height: 60px; border-radius: 50%;
  background: linear-gradient(135deg, #e1251b, #ff6e40);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  font-size: 24px; cursor: pointer; color: #fff;
  box-shadow: 0 6px 20px rgba(225, 37, 27, .4);
  transition: transform .2s;
}
.chat-fab:hover { transform: scale(1.08); }
.fab-badge { font-size: 10px; font-weight: 600; }

/* 面板 */
.chat-panel {
  position: fixed; right: 24px; bottom: 32px; z-index: 2000;
  width: 440px; height: 640px; max-height: calc(100vh - 64px);
  background: #fff; border-radius: 12px;
  box-shadow: 0 12px 48px rgba(0,0,0,.18);
  display: flex; flex-direction: column; overflow: hidden;
}
.chat-header {
  padding: 12px 16px; background: linear-gradient(135deg, #e1251b, #ff5e3a); color: #fff;
  display: flex; justify-content: space-between; align-items: center; flex-shrink: 0;
}
.header-title { display: flex; align-items: center; gap: 10px; }
.bot-avatar { font-size: 28px; }
.title-main { font-size: 15px; font-weight: 600; }
.title-sub { font-size: 11px; opacity: .85; margin-top: 2px; }
.header-actions :deep(.el-button) { color: #fff; font-size: 16px; }

.chat-body { flex: 1; overflow-y: auto; padding: 16px; background: #f7f8fa; }

.empty-tip { text-align: center; padding: 40px 12px 20px; color: #666; }
.empty-icon { font-size: 40px; margin-bottom: 8px; }
.empty-sub { font-size: 12px; color: #aaa; margin-top: 4px; }
.suggest { margin-top: 20px; display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
.suggest-tag { cursor: pointer; }

.msg-row { display: flex; gap: 10px; margin-bottom: 16px; }
.msg-row.user { flex-direction: row-reverse; }
.avatar { font-size: 28px; flex-shrink: 0; }
.msg-content { max-width: 82%; }
.msg-row.user .msg-content { display: flex; flex-direction: column; align-items: flex-end; }

.bubble {
  padding: 10px 14px; border-radius: 10px; font-size: 14px; line-height: 1.65;
  white-space: pre-wrap; word-break: break-word;
}
.msg-row.assistant .bubble { background: #fff; border: 1px solid #ececec; border-top-left-radius: 2px; }
.msg-row.user .bubble { background: #fdecea; color: #333; border-top-right-radius: 2px; }
.bubble .rich :deep(.rk) { color: #e1251b; font-weight: 600; }
.bubble .rich :deep(.rc) {
  background: #f4f4f5; border-radius: 4px; padding: 1px 5px; font-size: 12px;
}
.bubble .rich :deep(.rn) { color: #e1251b; font-weight: 600; }
.cursor { animation: blink 1s infinite; }
@keyframes blink { 50% { opacity: 0; } }

.steps { margin-bottom: 6px; display: flex; flex-direction: column; gap: 4px; align-items: flex-start; }
.step-pill {
  font-size: 12px; color: #67c23a; background: #f0f9eb;
  border: 1px solid #d1edc4; padding: 3px 10px; border-radius: 12px;
}

/* 商品推荐卡片 */
.cards { margin-top: 8px; display: flex; gap: 8px; overflow-x: auto; padding-bottom: 4px; }
.rec-card {
  width: 118px; flex-shrink: 0; background: #fff; border: 1px solid #ececec;
  border-radius: 8px; overflow: hidden; cursor: pointer; transition: box-shadow .2s;
}
.rec-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,.1); }
.rec-pic {
  height: 84px; display: flex; align-items: center; justify-content: center;
  background: #faf6f5; font-size: 40px; overflow: hidden;
}
.rec-pic img { width: 100%; height: 100%; object-fit: cover; }
.rec-info { padding: 6px 8px 8px; }
.rec-name {
  font-size: 12px; line-height: 16px; height: 32px; overflow: hidden;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
}
.rec-meta { margin-top: 4px; display: flex; justify-content: space-between; align-items: baseline; }
.rec-price { color: #e1251b; font-size: 14px; font-weight: 600; }
.rec-rate { color: #999; font-size: 11px; }
.rec-store { margin-top: 2px; font-size: 10px; color: #bbb; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* 订单卡片 */
.orders { margin-top: 8px; display: flex; flex-direction: column; gap: 8px; }
.order-chip {
  background: #fff; border: 1px solid #ececec; border-radius: 8px; padding: 10px 12px;
}
.oc-head { display: flex; justify-content: space-between; align-items: center; }
.oc-no { font-size: 12px; color: #e1251b; font-weight: 600; }
.oc-items { margin-top: 6px; display: flex; flex-direction: column; gap: 4px; }
.oc-item { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #333; }
.oc-pic {
  width: 22px; height: 22px; border-radius: 4px; background: #faf6f5; font-size: 13px;
  display: inline-flex; align-items: center; justify-content: center; overflow: hidden;
  flex-shrink: 0;
}
.oc-pic img { width: 100%; height: 100%; object-fit: cover; }
.oc-foot { margin-top: 6px; display: flex; justify-content: space-between; align-items: center; }
.oc-total { color: #e1251b; font-size: 13px; font-weight: 600; }
.oc-logi { font-size: 11px; color: #999; }

/* 售后操作确认卡片 */
.actions { margin-top: 8px; display: flex; flex-direction: column; gap: 8px; }
.action-card {
  background: #fff; border: 1px solid #f0e2cc; border-left: 3px solid #e6a23c;
  border-radius: 8px; padding: 10px 12px;
}
.action-card.done { border-left-color: #67c23a; }
.action-card.failed { border-left-color: #f56c6c; }
.action-card.cancelled { border-left-color: #c0c4cc; }
.ac-head { display: flex; justify-content: space-between; align-items: center; }
.ac-title { font-size: 14px; font-weight: 600; color: #303133; }
.ac-badge {
  font-size: 11px; padding: 1px 8px; border-radius: 10px;
  background: #fdf6ec; color: #e6a23c;
}
.action-card.done .ac-badge { background: #f0f9eb; color: #67c23a; }
.action-card.failed .ac-badge { background: #fef0f0; color: #f56c6c; }
.action-card.cancelled .ac-badge { background: #f4f4f5; color: #909399; }
.ac-summary { margin-top: 6px; font-size: 12px; line-height: 1.6; color: #606266; }
.ac-details { margin-top: 6px; background: #fafafa; border-radius: 6px; padding: 6px 8px; }
.ac-row { display: flex; gap: 8px; font-size: 12px; line-height: 1.7; }
.ac-label { color: #909399; flex-shrink: 0; width: 66px; }
.ac-value { color: #303133; word-break: break-all; }
.ac-btns { margin-top: 8px; display: flex; gap: 8px; }
.ac-result { margin-top: 8px; font-size: 12px; line-height: 1.6; color: #67c23a; }
.ac-result.failed { color: #f56c6c; }
.ac-result.cancelled { color: #909399; }
.ac-hint { margin-top: 6px; font-size: 11px; color: #c0c4cc; }

.sources { margin-top: 8px; }
.sources :deep(.el-collapse) { border: none; }
.sources :deep(.el-collapse-item__header) { font-size: 12px; height: 30px; }
.source-item { margin-bottom: 8px; }
.source-doc { font-size: 12px; color: #e1251b; display: flex; align-items: center; gap: 6px; }
.source-text { font-size: 12px; color: #888; margin-top: 2px; max-height: 60px; overflow: hidden; }

/* 可信回答校验（方向 B） */
.verify-bar {
  margin-top: 8px; display: flex; gap: 6px; align-items: flex-start;
  padding: 7px 10px; border-radius: 8px; font-size: 12px; line-height: 1.55;
}
.verify-bar.ok { background: #f0f9eb; border: 1px solid #d1edc4; color: #529b2e; }
.verify-bar.warn { background: #fdf6ec; border: 1px solid #f5dab1; color: #b26a00; }
.vb-icon { flex-shrink: 0; }
.verify-detail { margin-top: 4px; }
.verify-detail :deep(.el-collapse) { border: none; }
.verify-detail :deep(.el-collapse-item__header) { font-size: 12px; height: 30px; }
.claim-row {
  display: flex; gap: 6px; align-items: flex-start;
  padding: 3px 0; font-size: 12px; color: #606266;
}
.claim-icon { width: 14px; flex-shrink: 0; color: #67c23a; }
.claim-row.partial .claim-icon { color: #e6a23c; }
.claim-row.unsupported .claim-icon { color: #f56c6c; }
.claim-text { flex: 1; line-height: 1.5; }
.claim-score { flex-shrink: 0; color: #c0c4cc; }
.source-effective { margin-left: 6px; font-size: 11px; color: #909399; }
.route-badge { display: flex; align-items: center; gap: 6px; margin-top: 6px; flex-wrap: wrap; }
.route-note { font-size: 11px; color: #909399; }

.feedback { margin-top: 6px; display: flex; gap: 12px; }
.fb-btn { font-size: 12px; color: #999; cursor: pointer; }
.fb-btn:hover { color: #e1251b; }

.chat-footer { padding: 12px; border-top: 1px solid #eee; display: flex; gap: 8px; flex-shrink: 0; }
.chat-footer .el-input { flex: 1; }
</style>
