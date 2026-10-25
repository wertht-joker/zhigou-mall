<template>
  <el-dialog
    :model-value="modelValue"
    title="评价商品"
    width="480px"
    @update:model-value="$emit('update:modelValue', $event)"
    @closed="reset"
  >
    <div class="rv-item" v-if="orderItem">
      <div class="rv-pic">
        <img v-if="orderItem.image_url" :src="orderItem.image_url" alt="" />
        <span v-else>{{ orderItem.image }}</span>
      </div>
      <div class="rv-name">{{ orderItem.product_name }}</div>
    </div>

    <el-form label-width="60px">
      <el-form-item label="评分">
        <el-rate v-model="form.rating" show-text :texts="['很差', '较差', '一般', '不错', '超赞']" />
      </el-form-item>
      <el-form-item label="内容">
        <el-input
          v-model="form.content"
          type="textarea"
          :rows="4"
          maxlength="500"
          show-word-limit
          placeholder="说说你的使用感受吧～"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">发表评价</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import request from '../api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // 可评价列表条目（order_item_id）或订单明细（id 值为明细 ID）
  orderItem: { type: Object, default: null },
})
const emit = defineEmits(['update:modelValue', 'submitted'])

const form = reactive({ rating: 5, content: '' })
const submitting = ref(false)

function reset() {
  form.rating = 5
  form.content = ''
  submitting.value = false
}

async function submit() {
  if (!form.content.trim()) return ElMessage.warning('写点评价内容吧')
  submitting.value = true
  try {
    await request.post('/reviews', {
      order_item_id: props.orderItem.order_item_id ?? props.orderItem.id,
      rating: form.rating,
      content: form.content,
    })
    ElMessage.success('评价成功，感谢你的分享！')
    emit('update:modelValue', false)
    emit('submitted')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.rv-item { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
.rv-pic {
  width: 48px; height: 48px; border-radius: 6px; overflow: hidden; font-size: 26px;
  background: #faf6f5; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.rv-pic img { width: 100%; height: 100%; object-fit: cover; }
.rv-name { font-size: 14px; color: #333; }
</style>
