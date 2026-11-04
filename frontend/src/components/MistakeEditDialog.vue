<template>
  <el-dialog
    v-model="visible"
    :title="form.id ? '编辑错题' : '新增错题'"
    width="760px"
    top="6vh"
    destroy-on-close
  >
    <el-form :model="form" label-width="86px" class="mistake-form">
      <el-form-item label="所属错题集" required>
        <el-select v-model="form.set_ids" multiple filterable placeholder="至少选择一个错题集" style="width: 100%">
          <el-option-group v-for="g in setGroups" :key="g.notebook_id" :label="g.notebook_name">
            <el-option v-for="s in g.sets" :key="s.id" :value="s.id" :label="s.name" />
          </el-option-group>
        </el-select>
      </el-form-item>
      <div class="row2">
        <el-form-item label="题号">
          <el-input v-model="form.question_no" placeholder="如 3" maxlength="20" />
        </el-form-item>
        <el-form-item label="掌握状态">
          <el-switch v-model="form.mastered" active-text="已掌握" inactive-text="未掌握" />
        </el-form-item>
      </div>
      <el-form-item label="标题">
        <el-input v-model="form.title" maxlength="120" placeholder="错题标题，如 阅读理解《故乡》" />
      </el-form-item>
      <el-form-item label="题干">
        <el-input v-model="form.stem" type="textarea" :rows="3" placeholder="题干文字（图片与题干至少填一项）" />
      </el-form-item>
      <div class="row2">
        <el-form-item label="我的答案">
          <el-input v-model="form.my_answer" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="正确答案">
          <el-input v-model="form.correct_answer" type="textarea" :rows="2" />
        </el-form-item>
      </div>
      <el-form-item label="解析">
        <el-input v-model="form.explanation" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="错因">
        <el-input v-model="form.reason" type="textarea" :rows="2" placeholder="如 计算错误、概念不清、审题不清" />
      </el-form-item>
      <el-form-item label="知识点">
        <el-select v-model="form.unit_ids" multiple filterable placeholder="优先选择已有单元" style="width: 100%">
          <el-option-group v-for="g in unitGroups" :key="g.subject_id" :label="g.subject_name">
            <el-option
              v-for="u in g.units"
              :key="u.id"
              :value="u.id"
              :label="`第${u.sort_no}单元${u.name ? '（' + u.name + '）' : ''}${u.term ? ' · ' + u.term : ''}`"
            />
          </el-option-group>
        </el-select>
      </el-form-item>
      <el-form-item label="自由标签">
        <el-input v-model="form.knowledge_tags" placeholder="没有合适单元时自行填写，顿号分隔" maxlength="300" />
      </el-form-item>
      <el-form-item v-if="form.figure_url" label="题目配图">
        <el-image
          :src="form.figure_url"
          :preview-src-list="[form.figure_url]"
          preview-teleported
          fit="contain"
          class="preview"
        />
      </el-form-item>
      <el-form-item label="图片">
        <div class="img-line">
          <img v-if="imagePreview" :src="imagePreview" class="preview" alt="错题图片" />
          <div class="img-actions">
            <el-upload :show-file-list="false" :auto-upload="false" accept=".jpg,.jpeg,.png,.gif,.webp" :on-change="onPick">
              <el-button size="small">{{ imagePreview ? '更换图片' : '上传图片' }}</el-button>
            </el-upload>
            <el-button v-if="imagePreview" size="small" text type="danger" @click="clearImage">移除</el-button>
          </div>
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button :loading="organizing" :disabled="!form.stem" @click="aiOrganize">AI 整理</el-button>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  childId: { type: Number, default: null },
  mistake: { type: Object, default: null },
  defaults: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['update:modelValue', 'saved'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const form = ref({})
const setOptions = ref([])
const unitGroups = ref([])
const imageFile = ref(null)
const localPreview = ref('')
const saving = ref(false)
const organizing = ref(false)

const setGroups = computed(() => {
  const groups = []
  const map = {}
  for (const s of setOptions.value) {
    if (!map[s.notebook_id]) {
      map[s.notebook_id] = { notebook_id: s.notebook_id, notebook_name: s.notebook_name, sets: [] }
      groups.push(map[s.notebook_id])
    }
    map[s.notebook_id].sets.push(s)
  }
  return groups
})

const imagePreview = computed(() => localPreview.value || props.defaults?.imageUrl || form.value.image_url || '')

function reset() {
  const m = props.mistake
  form.value = {
    id: m?.id || null,
    set_ids: m?.set_ids?.slice() || props.defaults?.setIds?.slice() || [],
    question_no: m?.question_no || '',
    title: m?.title || '',
    stem: m?.stem || '',
    my_answer: m?.my_answer || '',
    correct_answer: m?.correct_answer || '',
    explanation: m?.explanation || '',
    reason: m?.reason || '',
    knowledge_tags: m?.knowledge_tags || '',
    unit_ids: m?.unit_ids?.slice() || [],
    mastered: !!m?.mastered,
    image_url: m?.image_url || '',
    figure_url: m?.figure_url || '',
  }
  imageFile.value = null
  localPreview.value = ''
}

async function loadOptions() {
  if (!props.childId) return
  try {
    const [setsRes, unitsRes] = await Promise.all([
      api.get('/mistakes/set-options', { params: { child_id: props.childId } }),
      api.get('/mistakes/units', { params: { child_id: props.childId } }),
    ])
    setOptions.value = setsRes.data
    unitGroups.value = unitsRes.data
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

watch(
  () => props.modelValue,
  (v) => {
    if (v) {
      reset()
      loadOptions()
    }
  },
)

function onPick(file) {
  if (!file?.raw) return
  imageFile.value = file.raw
  localPreview.value = URL.createObjectURL(file.raw)
}

function clearImage() {
  imageFile.value = null
  localPreview.value = ''
  form.value.image_url = ''
}

async function aiOrganize() {
  organizing.value = true
  try {
    const { data } = await api.post('/mistakes/ai/organize', {
      stem: form.value.stem,
      my_answer: form.value.my_answer,
      correct_answer: form.value.correct_answer,
      child_id: props.childId,
    })
    form.value.stem = data.stem
    form.value.my_answer = data.my_answer
    form.value.correct_answer = data.correct_answer
    form.value.explanation = data.explanation
    form.value.reason = data.reason
    if (data.unit_ids?.length) form.value.unit_ids = data.unit_ids
    if (data.knowledge?.length) form.value.knowledge_tags = data.knowledge.join('、')
    ElMessage.success('AI 已整理，请核对后保存')
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    organizing.value = false
  }
}

async function save() {
  if (!form.value.set_ids.length) return ElMessage.warning('请至少选择一个错题集')
  if (!form.value.stem.trim() && !imageFile.value && !form.value.image_url) {
    return ElMessage.warning('题干或图片至少需要一项')
  }
  const payload = {
    child_id: props.childId,
    set_ids: form.value.set_ids,
    question_no: form.value.question_no,
    title: form.value.title,
    stem: form.value.stem,
    my_answer: form.value.my_answer,
    correct_answer: form.value.correct_answer,
    explanation: form.value.explanation,
    reason: form.value.reason,
    knowledge_tags: form.value.knowledge_tags,
    unit_ids: form.value.unit_ids,
    mastered: form.value.mastered,
    source_type: props.mistake ? props.mistake.source_type : props.defaults?.sourceScoreId ? 'score' : 'manual',
    source_score_id: props.mistake ? props.mistake.source_score_id : props.defaults?.sourceScoreId || null,
    source_image_id: props.mistake ? props.mistake.source_image_id : props.defaults?.sourceImageId || null,
    image_filename: imageFile.value ? null : filenameFromUrl(form.value.image_url || props.defaults?.imageUrl),
    clear_image: !imageFile.value && !form.value.image_url && !!(props.mistake?.image_url || props.defaults?.imageUrl),
  }
  saving.value = true
  try {
    let id = form.value.id
    if (!id) {
      const fd = new FormData()
      fd.append('payload', JSON.stringify(payload))
      if (imageFile.value) fd.append('file', imageFile.value)
      const { data } = await api.post('/mistakes', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      id = data.id
    } else {
      await api.patch(`/mistakes/${id}`, payload)
      if (imageFile.value) {
        const fd = new FormData()
        fd.append('file', imageFile.value)
        await api.post(`/mistakes/${id}/image`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      }
    }
    ElMessage.success('已保存')
    visible.value = false
    emit('saved')
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    saving.value = false
  }
}

function filenameFromUrl(url) {
  if (!url || !url.includes('/uploads/')) return null
  return url.split('/uploads/').pop().split('?')[0]
}
</script>

<style scoped>
.row2 {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 0 16px;
}
.img-line {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.preview {
  max-width: 200px;
  max-height: 150px;
  border-radius: 6px;
  border: 1px solid #ebeef5;
  object-fit: contain;
}
.img-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
}
</style>
