<template>
  <el-dialog v-model="visible" title="AI 识别错题" width="960px" top="4vh" destroy-on-close>
    <div v-if="phase === 'idle'" class="upload-box">
      <el-upload drag :show-file-list="false" :auto-upload="false" accept=".jpg,.jpeg,.png,.gif,.webp" :on-change="onPick">
        <div class="upload-text">把试卷图片拖到这里，或点击选择图片</div>
        <div class="upload-hint">AI 会识别题干、作答与批改痕迹；有批改痕迹时自动挑出错题，没有则让你勾选</div>
      </el-upload>
      <div class="tip">
        需要先在「设置 → 智能助手」里配置支持看图的模型（如通义千问、智谱 GLM、Kimi 的多模态模型）。
      </div>
    </div>

    <div v-else-if="phase === 'loading'" class="loading-box">
      <el-icon class="is-loading" :size="26"><Loading /></el-icon>
      <span>AI 正在识别试卷，可能需要几十秒…</span>
    </div>

    <template v-else-if="phase === 'select' || phase === 'edit'">
      <div class="src-line">
        <img v-if="preview" :src="preview" class="src-thumb" alt="试卷" />
        <div class="src-info">
          <div class="src-title">
            <el-tag :type="result?.has_marks ? 'success' : 'warning'" size="small">
              {{ result?.has_marks ? '检测到批改痕迹，已自动挑出错题' : '未检测到批改痕迹，请手动勾选错题' }}
            </el-tag>
            <span class="muted" v-if="items.length">共 {{ items.length }} 道待处理</span>
          </div>
          <div class="muted small">识别结果仅供参考，请核对后保存。</div>
        </div>
      </div>

      <div v-if="phase === 'select'" class="select-list">
        <el-checkbox-group v-model="checked">
          <el-checkbox v-for="(q, i) in items" :key="i" :value="i" class="select-item">
            <span class="qn">{{ q.no ? `第 ${q.no} 题` : `题目 ${i + 1}` }}</span>
            <span class="stem">{{ q.stem || '（未识别到题干）' }}</span>
          </el-checkbox>
        </el-checkbox-group>
        <div class="select-actions">
          <el-button @click="visible = false">取消</el-button>
          <el-button type="primary" :disabled="!checked.length" @click="startEdit">开始逐题整理</el-button>
        </div>
      </div>

      <div v-else class="edit-step">
        <div class="step-head">
          <div class="step-nav">
            <span>第 {{ current + 1 }} / {{ items.length }} 道</span>
            <el-tag v-if="currentGroupCount > 1" size="small" type="warning">
              本大题 {{ currentGroupCount }} 道错题合并保存
            </el-tag>
            <el-select :model-value="current" size="small" class="jump-select" @change="onJump">
              <el-option v-for="(q, i) in items" :key="i" :value="i" :label="questionOptionLabel(q, i)" />
            </el-select>
            <el-button size="small" type="danger" plain @click="removeCurrent">删除本题</el-button>
            <el-button size="small" type="primary" plain :loading="adding" @click="addByNo">手动添加</el-button>
            <el-button size="small" plain @click="reRecognize">重新识别</el-button>
          </div>
          <el-tag size="small" type="info">{{ form.no ? `第 ${form.no} 题` : '未标题号' }}</el-tag>
        </div>
        <div class="step-body">
          <div class="left">
            <el-image
              v-if="preview"
              :src="preview"
              :preview-src-list="[preview]"
              preview-teleported
              fit="contain"
              class="src-big"
              alt="试卷原图"
            />
          </div>
          <div class="right">
            <el-form label-width="76px">
              <div class="row2">
                <el-form-item label="题号"><el-input v-model="form.no" maxlength="20" /></el-form-item>
                <el-form-item label="错题集" required>
                  <el-select v-model="form.set_ids" multiple filterable placeholder="至少选择一个" style="width: 100%">
                    <el-option-group v-for="g in setGroups" :key="g.notebook_id" :label="g.notebook_name">
                      <el-option v-for="s in g.sets" :key="s.id" :value="s.id" :label="s.name" />
                    </el-option-group>
                  </el-select>
                </el-form-item>
              </div>
              <el-form-item label="标题">
                <el-input v-model="form.title" maxlength="120" placeholder="AI 总结的标题，如 阅读理解《故乡》" />
              </el-form-item>
              <el-form-item label="题干">
                <el-input v-model="form.stem" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" />
              </el-form-item>
              <el-form-item v-if="currentFigure || currentHasFigure" label="题目配图">
                <el-image
                  v-if="currentFigure"
                  :src="currentFigure"
                  :preview-src-list="[currentFigure]"
                  preview-teleported
                  fit="contain"
                  class="figure-img"
                />
                <span v-else class="muted small">检测到配图，但未能自动裁剪；建议重新上传更清晰的题目图片。</span>
              </el-form-item>
              <div class="row2">
                <el-form-item label="我的答案">
                  <el-input v-model="form.my_answer" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" />
                </el-form-item>
                <el-form-item label="正确答案">
                  <el-input v-model="form.correct_answer" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" />
                </el-form-item>
              </div>
              <el-form-item label="解析">
                <el-input v-model="form.explanation" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" />
              </el-form-item>
              <el-form-item label="错因"><el-input v-model="form.reason" /></el-form-item>
              <el-form-item label="知识点">
                <el-select v-model="form.unit_ids" multiple filterable placeholder="优先选已有单元" style="width: 100%">
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
                <el-input v-model="form.knowledge_tags" placeholder="顿号分隔" maxlength="300" />
              </el-form-item>
            </el-form>
          </div>
        </div>
        <div class="step-actions">
          <el-button :loading="organizing" :disabled="!form.stem" @click="organizeCurrent">AI 整理本题</el-button>
          <span class="grow" />
          <el-button @click="skip">跳过</el-button>
          <el-button @click="saveScreenshot">仅存截图</el-button>
          <el-button type="primary" :loading="saving" @click="saveCurrent">加入错题集</el-button>
        </div>
      </div>
    </template>

    <div v-else-if="phase === 'done'" class="done-box">
      <el-result icon="success" title="处理完成" :sub-title="`本次共加入 ${addedCount} 道错题`">
        <template #extra>
          <el-button type="primary" @click="visible = false">完成</el-button>
        </template>
      </el-result>
    </div>

    <template #footer>
      <span class="muted small">此流程为逐题确认，AI 结果可改；不确认时可只保留截图。</span>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { api, errMsg } from '../api'
import { attachToNearestGroup, buildGroupAggregate, buildQuestionForm, groupSiblings, normalizeNo, questionOptionLabel, selectWrongQuestions, sortQuestionsByNo } from '../utils/mistakeQuestionNav'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  childId: { type: Number, default: null },
  sourceScoreId: { type: Number, default: null },
  sourceImageId: { type: Number, default: null },
  imageUrl: { type: String, default: '' },
  setIds: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue', 'saved'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const phase = ref('idle') // idle / loading / select / edit / done
const result = ref(null)
const items = ref([])
const checked = ref([])
const current = ref(0)
const pickedFile = ref(null)
const localPreview = ref('')
const setOptions = ref([])
const unitGroups = ref([])
const saving = ref(false)
const organizing = ref(false)
const adding = ref(false)
const addedCount = ref(0)

const form = reactive({
  no: '',
  title: '',
  stem: '',
  my_answer: '',
  correct_answer: '',
  explanation: '',
  reason: '',
  knowledge_tags: '',
  unit_ids: [],
  set_ids: [],
})

const preview = computed(() => localPreview.value || props.imageUrl || '')
const currentItem = computed(() => items.value[current.value] || {})
const currentGroupCount = computed(() => groupSiblings(items.value, current.value).length)
const currentFigure = computed(() => currentItem.value.figure_url || '')
const currentHasFigure = computed(() => !!currentItem.value.has_figure)
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

watch(
  () => props.modelValue,
  async (v) => {
    if (!v) return
    phase.value = 'idle'
    result.value = null
    items.value = []
    checked.value = []
    current.value = 0
    pickedFile.value = null
    localPreview.value = ''
    addedCount.value = 0
    await loadOptions()
    if (props.sourceImageId || props.imageUrl) {
      recognize()
    }
  },
)

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

function onPick(file) {
  if (!file?.raw) return
  pickedFile.value = file.raw
  localPreview.value = URL.createObjectURL(file.raw)
  recognize()
}

async function recognize() {
  phase.value = 'loading'
  try {
    const fd = new FormData()
    if (props.sourceImageId) fd.append('score_image_id', props.sourceImageId)
    else if (props.sourceScoreId) fd.append('score_id', props.sourceScoreId)
    fd.append('child_id', props.childId)
    if (pickedFile.value) fd.append('file', pickedFile.value)
    const { data } = await api.post('/mistakes/ai/recognize', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000,
    })
    result.value = data
    items.value = (data.questions || []).map((q) => ({ ...q, done: false }))
    if (!items.value.length) {
      ElMessage.warning('没有从图片中识别到题目')
      phase.value = 'idle'
      return
    }
    if (data.has_marks) {
      const wrong = selectWrongQuestions(items.value, true)
      if (wrong === null) {
        ElMessage.info('AI 未逐题标注对错，请手动勾选错题')
        checked.value = items.value.map((q, i) => i)
        phase.value = 'select'
        return
      }
      if (!wrong.length) {
        ElMessage.warning('没有识别到被批改为错的题目')
        phase.value = 'idle'
        return
      }
      items.value = wrong
      current.value = 0
      loadCurrent()
      phase.value = 'edit'
    } else {
      checked.value = items.value.map((q, i) => i)
      phase.value = 'select'
    }
  } catch (e) {
    ElMessage.error(errMsg(e))
    phase.value = 'idle'
  }
}

async function removeCurrent() {
  const item = items.value[current.value]
  if (!item) return
  if (item.done) {
    try {
      await ElMessageBox.confirm(
        '这道题已经加入错题集，从列表移除不会删除已保存的错题。',
        '移除本题',
        { type: 'warning', confirmButtonText: '移除', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
  }
  items.value.splice(current.value, 1)
  if (!items.value.length) {
    phase.value = 'idle'
    ElMessage.info('已移除全部待处理题目，可重新识别或重新上传')
    return
  }
  if (current.value >= items.value.length) current.value = items.value.length - 1
  loadCurrent()
  ElMessage.success('已从待处理列表移除')
}

async function addByNo() {
  let no = ''
  try {
    const { value } = await ElMessageBox.prompt('输入要补充识别的题号，例如 3、(2)', '手动添加错题', {
      confirmButtonText: '识别',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '题号不能为空',
    })
    no = value.trim()
  } catch {
    return
  }
  const exist = items.value.findIndex((q) => normalizeNo(q.no) === normalizeNo(no))
  if (exist >= 0) {
    current.value = exist
    loadCurrent()
    ElMessage.info(`第 ${no} 题已在列表中`)
    return
  }
  adding.value = true
  try {
    const fd = new FormData()
    if (props.sourceImageId) fd.append('score_image_id', props.sourceImageId)
    else if (props.sourceScoreId) fd.append('score_id', props.sourceScoreId)
    fd.append('child_id', props.childId)
    fd.append('target_no', no)
    if (pickedFile.value) fd.append('file', pickedFile.value)
    const { data } = await api.post('/mistakes/ai/recognize', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000,
    })
    const q = (data.questions || [])[0]
    if (!q) {
      ElMessage.warning(`图片中没有识别到第 ${no} 题`)
      return
    }
    q.is_wrong = true
    q.done = false
    attachToNearestGroup(q, items.value)
    syncFormToItem(current.value)
    items.value.push(q)
    items.value = sortQuestionsByNo(items.value)
    const index = items.value.indexOf(q)
    current.value = index >= 0 ? index : items.value.length - 1
    loadCurrent()
    ElMessage.success(`已补充第 ${q.no || no} 题`)
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    adding.value = false
  }
}

async function reRecognize() {
  if (addedCount.value > 0) {
    try {
      await ElMessageBox.confirm(
        `已保存 ${addedCount.value} 道错题，重新识别只重置当前待处理列表，不会删除已保存的内容。`,
        '重新识别',
        { type: 'warning', confirmButtonText: '重新识别', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
  }
  await recognize()
}

function startEdit() {
  const list = items.value.filter((_, i) => checked.value.includes(i))
  items.value = list
  current.value = 0
  loadCurrent()
  phase.value = 'edit'
}

function loadCurrent() {
  const q = items.value[current.value] || {}
  const setIds = props.setIds?.length ? props.setIds : form.set_ids
  Object.assign(form, buildQuestionForm(q, setIds))
}

/** 切题前把表单里的修改写回题目，避免编辑内容丢失、也保证整体保存取到最新内容。 */
function syncFormToItem(index = current.value) {
  const item = items.value[index]
  if (!item) return
  Object.assign(item, {
    no: form.no,
    title: form.title,
    stem: form.stem,
    my_answer: form.my_answer,
    correct_answer: form.correct_answer,
    explanation: form.explanation,
    reason: form.reason,
    knowledge: form.knowledge_tags
      .split(/[、,，]/)
      .map((x) => x.trim())
      .filter(Boolean),
    unit_ids: form.unit_ids,
  })
}

function onJump(index) {
  syncFormToItem(current.value)
  current.value = index
  loadCurrent()
}

function next() {
  syncFormToItem(current.value)
  const remain = items.value.findIndex((it, i) => i > current.value && !it.done)
  if (remain >= 0) {
    current.value = remain
    loadCurrent()
  } else {
    phase.value = 'done'
    emit('saved')
  }
}

function skip() {
  items.value[current.value].done = true
  next()
}

async function organizeCurrent() {
  organizing.value = true
  try {
    const { data } = await api.post('/mistakes/ai/organize', {
      stem: form.stem,
      my_answer: form.my_answer,
      correct_answer: form.correct_answer,
      child_id: props.childId,
      subject_id: result.value?.subject_id,
    }, { timeout: 120000 })
    form.stem = data.stem
    form.my_answer = data.my_answer
    form.correct_answer = data.correct_answer
    form.explanation = data.explanation
    form.reason = data.reason
    if (data.unit_ids?.length) form.unit_ids = data.unit_ids
    if (data.knowledge?.length) form.knowledge_tags = data.knowledge.join('、')
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    organizing.value = false
  }
}

async function saveCurrent() {
  if (!form.set_ids.length) return ElMessage.warning('请至少选择一个错题集')
  if (!form.stem.trim() && !pickedFile.value && !props.imageUrl) {
    return ElMessage.warning('题干或图片至少需要一项')
  }
  await persist(false)
}

async function saveScreenshot() {
  if (!form.set_ids.length) return ElMessage.warning('请至少选择一个错题集')
  await persist(true)
}

async function persist(screenshotOnly) {
  saving.value = true
  try {
    syncFormToItem(current.value)
    const q = items.value[current.value] || {}
    const group = buildGroupAggregate(items.value, current.value)
    const members = group ? groupSiblings(items.value, current.value) : [q]
    const payload = {
      child_id: props.childId,
      set_ids: form.set_ids,
      question_no: group?.question_no || form.no,
      title: screenshotOnly ? '' : (group ? group.title : form.title),
      stem: screenshotOnly ? '' : (group ? group.stem : form.stem),
      my_answer: screenshotOnly ? '' : (group ? group.my_answer : form.my_answer),
      correct_answer: screenshotOnly ? '' : (group ? group.correct_answer : form.correct_answer),
      explanation: screenshotOnly ? '' : (group ? group.explanation : form.explanation),
      reason: screenshotOnly ? '' : (group ? group.reason : form.reason),
      knowledge_tags: screenshotOnly ? '' : (group ? group.knowledge.join('、') : form.knowledge_tags),
      unit_ids: screenshotOnly ? [] : form.unit_ids,
      source_type: 'ai',
      source_score_id: props.sourceScoreId,
      source_image_id: props.sourceImageId,
      image_filename: pickedFile.value ? null : filenameFromUrl(props.imageUrl),
      figure_filename: screenshotOnly ? null : (group?.figure_filename || q.figure_filename || null),
      mastered: false,
    }
    const fd = new FormData()
    fd.append('payload', JSON.stringify(payload))
    if (pickedFile.value) fd.append('file', pickedFile.value)
    await api.post('/mistakes', fd, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 })
    const merged = group && members.length > 1
    members.forEach((it) => { if (it) it.done = true })
    addedCount.value += 1
    ElMessage.success(
      screenshotOnly
        ? '已仅存截图'
        : merged
          ? `已将本大题 ${members.length} 道错题合并保存`
          : '已加入错题集',
    )
    next()
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
.upload-box {
  padding: 8px 4px 0;
}
.upload-text {
  padding: 28px 0 6px;
  font-size: 15px;
  color: #303133;
}
.upload-hint {
  padding-bottom: 24px;
  font-size: 12px;
  color: #909399;
}
.tip {
  margin-top: 14px;
  font-size: 12px;
  color: #909399;
}
.loading-box {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 60px 0;
  color: #606266;
}
.src-line {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 14px;
}
.src-thumb {
  width: 90px;
  height: 66px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid #ebeef5;
}
.src-title {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 6px;
}
.muted {
  color: #909399;
}
.small {
  font-size: 12px;
}
.select-item {
  display: flex;
  align-items: flex-start;
  width: 100%;
  margin: 0 0 10px;
  height: auto;
}
.select-item .qn {
  display: inline-block;
  min-width: 72px;
  font-weight: 600;
}
.select-item .stem {
  color: #606266;
  font-size: 13px;
  white-space: normal;
  line-height: 1.5;
}
.select-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 18px;
}
.step-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  color: #606266;
}
.step-nav {
  display: flex;
  align-items: center;
  gap: 10px;
}
.jump-select {
  width: 150px;
}
.step-body {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 16px;
}
.src-big {
  display: block;
  width: 100%;
  max-height: 420px;
  object-fit: contain;
  border-radius: 6px;
  border: 1px solid #ebeef5;
  cursor: zoom-in;
}
.src-big :deep(.el-image__inner) {
  max-height: 420px;
  object-fit: contain;
}
.figure-img {
  max-width: 100%;
  max-height: 220px;
  border-radius: 6px;
  border: 1px solid #ebeef5;
}
.row2 {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 0 12px;
}
.step-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}
.grow {
  flex: 1;
}
.done-box {
  padding: 6px 0;
}
</style>
