<template>
  <el-dialog
    :model-value="modelValue"
    :title="editing ? '编辑收货地址' : '新增收货地址'"
    width="520px"
    @update:model-value="$emit('update:modelValue', $event)"
    @closed="reset"
  >
    <el-form label-width="90px">
      <el-form-item label="收货人">
        <el-input v-model="form.receiver" placeholder="姓名" maxlength="50" />
      </el-form-item>
      <el-form-item label="手机号">
        <el-input v-model="form.phone" placeholder="11 位手机号" maxlength="20" />
      </el-form-item>
      <el-form-item label="所在地区">
        <div class="region-row">
          <el-cascader
            v-model="regionCodes"
            :options="regionData"
            placeholder="选择省 / 市 / 区县"
            style="flex:1"
            filterable
            @change="onRegionChange"
          />
          <el-button :loading="locating" @click="locate" title="使用浏览器定位自动填充">📍 定位</el-button>
        </div>
      </el-form-item>
      <el-form-item label="详细地址">
        <el-input v-model="form.detail" placeholder="街道、门牌号、小区、楼栋" maxlength="200" />
      </el-form-item>
      <el-form-item label="设为默认">
        <el-switch v-model="form.is_default" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { regionData, codeToText } from 'element-china-area-data'
import request from '../api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // 传入则为编辑模式
  address: { type: Object, default: null },
})
const emit = defineEmits(['update:modelValue', 'saved'])

const form = reactive({ receiver: '', phone: '', region: '', detail: '', is_default: false })
const regionCodes = ref([])
const locating = ref(false)
const saving = ref(false)

// 打开时回填（编辑模式）
watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    if (props.address) {
      Object.assign(form, {
        receiver: props.address.receiver,
        phone: props.address.phone,
        region: props.address.region,
        detail: props.address.detail,
        is_default: !!props.address.is_default,
      })
      regionCodes.value = matchCodes(props.address.region)
    } else {
      reset()
    }
  },
)

function reset() {
  form.receiver = ''
  form.phone = ''
  form.region = ''
  form.detail = ''
  form.is_default = false
  regionCodes.value = []
}

/** 把「省 市 区」文本反查回级联编码（定位回填 / 编辑回显用） */
function matchCodes(regionText) {
  if (!regionText) return []
  const parts = regionText.split(/\s+/).filter((p) => p && p !== '市辖区')
  const codes = []
  let pool = regionData
  for (const part of parts) {
    let hit = pool.find((node) => node.label && node.label.includes(part.replace(/[省市区县]/g, '')))
    // 直辖市数据里夹着一层「市辖区」，文本中通常没有它，自动穿过
    if (!hit && pool.length === 1 && pool[0].label === '市辖区') {
      codes.push(pool[0].value)
      pool = pool[0].children || []
      hit = pool.find((node) => node.label && node.label.includes(part.replace(/[省市区县]/g, '')))
    }
    if (!hit) break
    codes.push(hit.value)
    pool = hit.children || []
  }
  return codes
}

function onRegionChange(codes) {
  if (!codes || !codes.length) {
    form.region = ''
    return
  }
  // 直辖市的「市辖区」是冗余层级，拼地区文本时去掉
  const labels = codes.map((c) => codeToText[c] || '').filter((l) => l && l !== '市辖区')
  // 直辖市两级重名（北京市 北京市）只保留一个
  form.region = labels.length >= 2 && labels[0] === labels[1] ? labels[0] : labels.join(' ')
}

/** 浏览器定位 → 后端逆地理编码代理（Photon + BigDataCloud），回填省市区与详细地址 */
async function locate() {
  if (!navigator.geolocation) {
    return ElMessage.warning('当前浏览器不支持定位')
  }
  locating.value = true
  navigator.geolocation.getCurrentPosition(
    async (pos) => {
      try {
        const { latitude, longitude } = pos.coords
        const data = await request.get('/geo/reverse', {
          params: { lat: latitude, lon: longitude },
        })
        // 后端返回标准 6 位行政区划编码；级联组件按「省 2 位 / 市 4 位 / 区 6 位」
        // 组织，这里按层级截断后再校验是否存在，避免整段编码匹配失败
        const widths = [2, 4, 6]
        const codes = (data.region_codes || [])
          .map((code, idx) => String(code).replace(/\D/g, '').slice(0, widths[idx]))
          .filter((code) => codeToText[code])
        if (codes.length) {
          regionCodes.value = codes
          onRegionChange(codes)
        } else {
          const parts = data.region_parts || []
          regionCodes.value = matchCodes(parts.join(' '))
          if (regionCodes.value.length) onRegionChange(regionCodes.value)
          else form.region = parts.join(' ')
        }
        const tail = (data.detail || '').trim()
        if (tail) form.detail = form.detail ? `${form.detail}（${tail}）` : tail
        ElMessage.success(`已定位到${form.region || '当前位置'}，请补全详细地址`)
      } catch (e) {
        ElMessage.error(e.message || '定位解析失败，请手动选择所在地区')
      } finally {
        locating.value = false
      }
    },
    (err) => {
      locating.value = false
      const hints = {
        1: '定位权限被拒绝，请在浏览器允许定位后重试',
        2: '无法获取当前位置，请检查系统定位服务',
        3: '定位超时，请重试或手动选择所在地区',
      }
      ElMessage.warning(hints[err.code] || '定位失败，请手动选择所在地区')
    },
    { enableHighAccuracy: false, timeout: 10000 },
  )
}

async function save() {
  if (!form.receiver.trim()) return ElMessage.warning('请填写收货人')
  if (!form.phone.trim()) return ElMessage.warning('请填写手机号')
  if (!form.detail.trim()) return ElMessage.warning('请填写详细地址')
  saving.value = true
  try {
    if (props.address) {
      await request.put(`/addresses/${props.address.id}`, { ...form })
    } else {
      await request.post('/addresses', { ...form })
    }
    ElMessage.success(props.address ? '地址已更新' : '地址已保存')
    emit('update:modelValue', false)
    emit('saved')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.region-row { display: flex; gap: 8px; width: 100%; }
</style>
