<template>
  <div class="page">
    <div class="page-header">
      <h3>⭐ 评价管理（本店商品）</h3>
      <el-input
        v-model="keyword"
        placeholder="按商品名过滤"
        style="width:220px"
        clearable
        @input="load"
      />
    </div>

    <el-table :data="filtered" v-loading="loading" border stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="product_name" label="商品" min-width="160" show-overflow-tooltip />
      <el-table-column prop="username" label="评价人" width="90" />
      <el-table-column label="评分" width="140">
        <template #default="{ row }">
          <el-rate :model-value="row.rating" disabled size="small" />
        </template>
      </el-table-column>
      <el-table-column prop="content" label="评价内容" min-width="220" show-overflow-tooltip />
      <el-table-column prop="reply" label="商家回复" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.reply">{{ row.reply }}</span>
          <el-tag v-else size="small" type="warning">待回复</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="评价时间" width="110">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!row.reply" size="small" type="primary" @click="openReply(row)">回复</el-button>
          <span v-else class="replied">已回复</span>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && filtered.length === 0" description="暂无评价" />

    <!-- 回复弹窗 -->
    <el-dialog v-model="replyDialog" title="回复评价" width="460px">
      <div class="reply-target" v-if="replying">
        <el-rate :model-value="replying.rating" disabled size="small" />
        <p class="content">「{{ replying.content }}」</p>
      </div>
      <el-input
        v-model="replyText"
        type="textarea"
        :rows="3"
        maxlength="300"
        show-word-limit
        placeholder="感谢您的评价，我们会继续努力～"
      />
      <template #footer>
        <el-button @click="replyDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitReply">提交回复</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '../../api'

const reviews = ref([])
const loading = ref(false)
const keyword = ref('')
const replyDialog = ref(false)
const replying = ref(null)
const replyText = ref('')
const submitting = ref(false)

const filtered = computed(() => {
  if (!keyword.value.trim()) return reviews.value
  const k = keyword.value.trim()
  return reviews.value.filter((r) => (r.product_name || '').includes(k))
})

function formatDate(t) {
  return t ? String(t).replace('T', ' ').slice(0, 10) : ''
}

async function load() {
  loading.value = true
  try {
    const data = await request.get('/merchant/reviews', { params: { page_size: 100 } })
    reviews.value = data.items
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function openReply(row) {
  replying.value = row
  replyText.value = ''
  replyDialog.value = true
}

async function submitReply() {
  if (!replyText.value.trim()) return ElMessage.warning('请填写回复内容')
  submitting.value = true
  try {
    await request.post(`/merchant/reviews/${replying.value.id}/reply`, { reply: replyText.value })
    ElMessage.success('回复成功')
    replyDialog.value = false
    load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.page { padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.reply-target { margin-bottom: 12px; }
.reply-target .content { color: #666; font-size: 13px; margin-top: 6px; }
.replied { font-size: 12px; color: #999; }
</style>
