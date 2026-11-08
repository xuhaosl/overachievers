<template>
  <div v-loading="loading" class="detail-page">
    <template v-if="s">
      <div class="page-head">
        <el-page-header @back="$router.back()">
          <template #content>
            <span class="color-dot" :style="{ background: s.subject_color }" />
            <b>{{ pageTitle }}</b>
            <span class="star" :class="{ on: s.starred }" title="加星/取消星" @click="toggleStar">★</span>
            <el-tag size="small" type="info" style="margin-left: 8px">{{ s.type }}</el-tag>
          </template>
          <template #extra>
            <el-button :disabled="!prevId" @click="go(prevId)">上一个</el-button>
            <el-button :disabled="!nextId" @click="go(nextId)">下一个</el-button>
            <el-button type="success" plain :icon="ChatDotRound" @click="askAi">问 AI</el-button>
            <el-button type="primary" @click="showEdit = true">编辑</el-button>
          </template>
        </el-page-header>
      </div>

      <el-card shadow="never">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="孩子">{{ s.child_name }}</el-descriptions-item>
          <el-descriptions-item label="日期">{{ s.date }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ s.type }}</el-descriptions-item>
          <el-descriptions-item label="学科">{{ s.subject_name }}</el-descriptions-item>
          <el-descriptions-item label="单元">
            <template v-if="s.unit_names">
              <el-link type="primary" @click="goSubject">{{ s.unit_names }}</el-link>
            </template>
            <template v-else>—</template>
          </el-descriptions-item>
          <el-descriptions-item label="年级">
            {{ [s.stage, s.grade ? `${s.grade}年级` : '', shortTerm(s.term)].filter(Boolean).join('') || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="学期">{{ s.term }}</el-descriptions-item>
          <el-descriptions-item label="成绩">
            <b>{{ displayScore(s) }}</b>
            <span class="muted"> / {{ displayTotal(s) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="得分率">
            <b>{{ ratePercent(s.rate) }}</b>
            <span class="muted" style="margin-left: 4px">（自动计算）</span>
          </el-descriptions-item>
          <el-descriptions-item label="年级排名">{{ rankText(s.grade_rank) }}</el-descriptions-item>
          <el-descriptions-item label="班级排名">
            <!-- 数字名次显示"第 x 名（共 n 人）"，文字名次（如"前5"）原样显示 -->
            {{ s.class_rank != null && s.class_rank !== ''
              ? (/^\d+(\.\d+)?$/.test(String(s.class_rank))
                ? `第 ${s.class_rank} 名${s.class_size ? `（共 ${s.class_size} 人）` : ''}`
                : String(s.class_rank))
              : '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="所属场次">
            <template v-if="s.exam_id">
              <el-link type="primary" @click="$router.push(`/exam/${s.exam_id}`)">{{ s.exam_name }}</el-link>
            </template>
            <template v-else>—（独立成绩）</template>
          </el-descriptions-item>
          <el-descriptions-item label="班级最高分">
            {{ s.high_score != null ? s.high_score : '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="最高得分者" :span="2">
            {{ s.high_scorer || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="标签">{{ s.tags || '—' }}</el-descriptions-item>
          <el-descriptions-item label="备注" :span="2">{{ s.note || '—' }}</el-descriptions-item>
          <el-descriptions-item label="AI 评语" :span="3">
            <template v-if="s.ai_comment">
              <span>{{ s.ai_comment }}</span>
              <el-button size="small" text type="danger" style="margin-left: 8px" @click="clearAiComment">
                清除
              </el-button>
            </template>
            <template v-else>—</template>
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card shadow="never" style="margin-top: 16px">
        <template #header>
          <div class="card-head">
            <span class="card-title">试卷图片 / 错题整理</span>
            <div class="head-ops">
              <el-select
                v-model="linkNotebookId"
                clearable
                size="small"
                placeholder="错题本"
                style="width: 140px"
                @change="onLinkNotebookChange"
              >
                <el-option v-for="nb in notebooks" :key="nb.id" :value="nb.id" :label="nb.name" />
              </el-select>
              <el-select v-model="linkSetId" clearable size="small" placeholder="错题集" style="width: 160px">
                <el-option v-for="st in linkSetOptions" :key="st.id" :value="st.id" :label="st.name" />
              </el-select>
              <el-button size="small" :disabled="!linkSetId" @click="openPicker">从错题集选取</el-button>
              <el-button size="small" :disabled="!linkedMistakes.length" @click="goMistakes">
                查看错题整理{{ linkedMistakes.length ? `（${linkedMistakes.length}）` : '' }}
              </el-button>
              <el-upload
                :show-file-list="false"
                :auto-upload="true"
                :http-request="doUpload"
                accept=".jpg,.jpeg,.png,.gif,.webp"
                multiple
              >
                <el-button type="primary" :loading="uploading">上传图片</el-button>
              </el-upload>
            </div>
          </div>
        </template>

        <div v-if="images.length || linkedMistakes.length" class="img-grid">
          <div
            v-for="(img, idx) in images"
            :key="'img-' + img.id"
            class="img-item"
            :class="{ dragging: dragIndex === idx, 'drag-over': dragOverIndex === idx }"
            draggable="true"
            @dragstart="onDragStart(idx, $event)"
            @dragover.prevent="onDragOver(idx)"
            @dragleave="onDragLeave(idx)"
            @drop.prevent="onDrop(idx)"
            @dragend="onDragEnd"
          >
            <el-image
              :src="img.url"
              :preview-src-list="images.map((i) => i.url)"
              :initial-index="images.findIndex((i) => i.id === img.id)"
              fit="cover"
              class="img-thumb"
            />
            <div class="img-op">
              <span class="img-name">{{ img.original_name || '图片' }}</span>
              <el-button size="small" type="danger" text @click="delImage(img)">删除</el-button>
            </div>
            <div class="img-actions">
              <el-button size="small" text type="primary" :icon="MagicStick" @click="openMistakeAi(img)">AI 识别</el-button>
              <el-button size="small" text @click="addToMistakes(img)">加入错题集</el-button>
            </div>
          </div>
          <div v-for="m in linkedMistakes" :key="'m-' + m.id" class="img-item linked-item" @click="goMistakes">
            <el-image
              v-if="m.image_url"
              :src="m.image_url"
              :preview-src-list="linkedImageUrls"
              :initial-index="linkedImageUrls.indexOf(m.image_url)"
              preview-teleported
              fit="cover"
              class="img-thumb"
              @click.stop
            />
            <div v-else class="img-thumb img-empty">仅文字</div>
            <div class="img-op">
              <span class="img-name" :title="m.title || ''">{{ m.title || '错题' }}</span>
              <el-button link size="small" type="danger" @click.stop="detach(m)">移除</el-button>
            </div>
          </div>
        </div>
      </el-card>
    </template>

    <!-- 从错题集选取错题，加入本场成绩的错题整理 -->
    <el-dialog v-model="pickerVisible" title="从错题集选取" width="720px" top="8vh">
      <div class="picker-tip">
        错题本：{{ pickerNotebookName || '全部' }}　错题集：{{ pickerSetName || '未选择' }}
      </div>
      <el-table
        v-loading="pickerLoading"
        :data="pickerMistakes"
        size="small"
        border
        max-height="420"
        @selection-change="onPickerChange"
      >
        <el-table-column type="selection" width="44" :selectable="(row) => !row._linked" />
        <el-table-column label="题目" min-width="320">
          <template #default="{ row }">
            <div class="brief-title">{{ row.title || '错题' }}</div>
            <div class="brief-line">{{ briefStem(row) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="题号" width="80">
          <template #default="{ row }">{{ row.question_no || '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag v-if="row._linked" size="small" type="info">已加入</el-tag>
            <span v-else class="muted">可选取</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!pickerLoading && !pickerMistakes.length" description="该错题集下还没有错题" :image-size="70" />
      <template #footer>
        <el-button @click="pickerVisible = false">取消</el-button>
        <el-button type="primary" :loading="attaching" :disabled="!pickerChecked.length" @click="attachSelected">
          加入（{{ pickerChecked.length }}）
        </el-button>
      </template>
    </el-dialog>

    <!-- 编辑成绩 -->
    <ScoreEditDialog v-model="showEdit" :score="s" @saved="load" />

    <!-- 错题：AI 识别 / 直接加入错题集 -->
    <MistakeAiDialog
      v-model="mistakeAiVisible"
      :child-id="s?.child_id"
      :source-score-id="s?.id"
      :source-image-id="mistakeImage?.id"
      :image-url="mistakeImage?.url || ''"
      @saved="loadLinked"
    />
    <MistakeEditDialog
      v-model="mistakeEditVisible"
      :child-id="s?.child_id"
      :defaults="mistakeDefaults"
      @saved="onMistakeSaved"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ChatDotRound, MagicStick } from '@element-plus/icons-vue'
import { api, errMsg } from '../api'
import { gradeLabel, ratePercent, rankText, shortTerm } from '../utils'
import ScoreEditDialog from '../components/ScoreEditDialog.vue'
import MistakeAiDialog from '../components/MistakeAiDialog.vue'
import MistakeEditDialog from '../components/MistakeEditDialog.vue'

const route = useRoute()
const router = useRouter()
const s = ref(null)
const images = ref([])
// 试卷图片拖动排序
const dragIndex = ref(-1)
const dragOverIndex = ref(-1)
const loading = ref(true)
const uploading = ref(false)
const showEdit = ref(false)
const mistakeAiVisible = ref(false)
const mistakeEditVisible = ref(false)
const mistakeImage = ref(null)
const mistakeDefaults = ref({})

// 错题整理关联：从错题本/错题集里挑选已有错题，挂到本场成绩下
const notebooks = ref([])
const allSets = ref([])
const linkNotebookId = ref(null)
const linkSetId = ref(null)
const linkedMistakes = ref([])
const linkedImageUrls = computed(() => linkedMistakes.value.map((m) => m.image_url).filter(Boolean))
const pickerVisible = ref(false)
const pickerLoading = ref(false)
const pickerMistakes = ref([])
const pickerChecked = ref([])
const attaching = ref(false)

const linkSetOptions = computed(() =>
  allSets.value.filter((st) => !linkNotebookId.value || st.notebook_id === linkNotebookId.value),
)
const pickerNotebookName = computed(
  () => notebooks.value.find((nb) => nb.id === linkNotebookId.value)?.name || '',
)
const pickerSetName = computed(
  () => linkSetOptions.value.find((st) => st.id === linkSetId.value)?.name || '',
)

function onLinkNotebookChange() {
  if (linkSetId.value && !linkSetOptions.value.some((st) => st.id === linkSetId.value)) linkSetId.value = null
}

async function loadTargets(childId) {
  if (!childId) return
  try {
    const [nbRes, setRes] = await Promise.all([
      api.get('/mistakes/notebooks', { params: { child_id: childId } }),
      api.get('/mistakes/set-options', { params: { child_id: childId } }),
    ])
    notebooks.value = nbRes.data
    allSets.value = setRes.data
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

// 本场成绩下已整理的错题（按来源关联）
async function loadLinked() {
  if (!s.value?.id) return
  try {
    const { data } = await api.get('/mistakes', { params: { source_score_id: s.value.id } })
    linkedMistakes.value = data
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

function briefStem(row) {
  const line = String(row.stem || '').split(/\n+/).map((x) => x.trim()).filter(Boolean)[0] || ''
  return line.length > 60 ? `${line.slice(0, 60)}…` : line || '（仅截图）'
}

async function openPicker() {
  pickerChecked.value = []
  pickerVisible.value = true
  pickerLoading.value = true
  try {
    const { data } = await api.get('/mistakes', {
      params: { child_id: s.value?.child_id, set_id: linkSetId.value },
    })
    const linkedIds = new Set(linkedMistakes.value.map((m) => m.id))
    pickerMistakes.value = data.map((m) => ({ ...m, _linked: linkedIds.has(m.id) }))
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    pickerLoading.value = false
  }
}

function onPickerChange(rows) {
  pickerChecked.value = rows
}

async function attachSelected() {
  if (!pickerChecked.value.length) return
  attaching.value = true
  try {
    await api.post('/mistakes/attach-score', {
      score_id: s.value.id,
      mistake_ids: pickerChecked.value.map((m) => m.id),
    })
    ElMessage.success(`已加入 ${pickerChecked.value.length} 道错题`)
    pickerVisible.value = false
    await loadLinked()
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    attaching.value = false
  }
}

async function detach(m) {
  try {
    await api.post('/mistakes/detach-score', { mistake_ids: [m.id] })
    ElMessage.success('已从本场成绩移除')
    await loadLinked()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

function goMistakes() {
  router.push('/mistakes')
}

function openMistakeAi(img) {
  mistakeImage.value = img
  mistakeAiVisible.value = true
}

function addToMistakes(img) {
  mistakeDefaults.value = {
    imageUrl: img.url,
    sourceScoreId: s.value?.id,
    sourceImageId: img.id,
    setIds: [],
  }
  mistakeEditVisible.value = true
}

function onMistakeSaved() {
  ElMessage.success('已加入错题整理')
  loadLinked()
}

// 标题：阶段年级学期学科单元，如"某年级第N学期某学科第N单元"
const pageTitle = computed(() => {
  const v = s.value
  if (!v) return ''
  const units = v.unit_names
    ? v.unit_names.split('、').map((x) => x.split('（')[0]).join('、')
    : ''
  const termPart = v.term ? v.term.split(' ').pop() : ''
  return [v.stage, v.grade ? `${v.grade}年级` : '', termPart, v.subject_name, units]
    .filter(Boolean)
    .join('')
})

function displayScore(row) {
  const base = `${row.regular_score}${row.bonus_score != null ? `（${row.bonus_score}）` : ''}`
  return base
}

// 总分同样带附加分："100（5）"
function displayTotal(row) {
  return `${row.regular_total}${row.bonus_total != null ? `（${row.bonus_total}）` : ''}`
}

function earned(row) {
  return (row.regular_score || 0) + (row.bonus_score || 0)
}

function totalSum(row) {
  return (row.regular_total || 0) + (row.bonus_total || 0)
}

// 点星直接切换星标
async function toggleStar() {
  try {
    const { data } = await api.patch(`/scores/${s.value.id}/star`, { starred: !s.value.starred })
    s.value.starred = data.starred
  } catch (err) {
    ElMessage.error(errMsg(err))
  }
}

// 呼出 AI 侧栏：预填当前成绩为数据范围与评语目标
function askAi() {
  const v = s.value
  window.$openAi?.({
    child_id: v.child_id,
    subject_id: v.subject_id,
    date_from: v.date,
    date_to: v.date,
    focus: { type: 'score', id: v.id, label: `${v.subject_name} ${v.date} ${v.regular_score}分` },
  })
}

// AI 侧栏写入评语后刷新显示
function onAiComment(e) {
  if (e.detail?.type === 'score' && e.detail?.id === s.value?.id) load()
}
onMounted(() => window.addEventListener('ai-comment-updated', onAiComment))
onUnmounted(() => window.removeEventListener('ai-comment-updated', onAiComment))

async function clearAiComment() {
  try {
    await api.patch(`/scores/${s.value.id}/ai-comment`, { content: '' })
    s.value.ai_comment = ''
    ElMessage.success('已清除')
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get(`/scores/${route.params.id}`)
    s.value = data
    images.value = (await api.get(`/scores/${route.params.id}/images`)).data
    // 关联错题本/错题集与本场已整理的错题
    linkNotebookId.value = null
    linkSetId.value = null
    await loadTargets(data.child_id)
    await loadLinked()
    // 同孩子全部成绩（按列表顺序：日期倒序），用于上一个/下一个导航
    const { data: list } = await api.get('/scores', { params: { child_id: data.child_id } })
    listIds.value = list.map((x) => x.id)
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    loading.value = false
  }
}

// 上一个/下一个：列表中当前成绩的前一条/后一条
const listIds = ref([])
const idx = computed(() => listIds.value.indexOf(s.value?.id))
const prevId = computed(() => (idx.value > 0 ? listIds.value[idx.value - 1] : null))
const nextId = computed(() =>
  idx.value >= 0 && idx.value < listIds.value.length - 1 ? listIds.value[idx.value + 1] : null,
)
function go(id) {
  if (id) router.push(`/score/${id}`)
}

// 点单元跳到学科详情页对应学期TAB，用于修改单元内容
function goSubject() {
  const q = s.value?.term_short ? { term: s.value.term_short } : {}
  router.push({ path: `/subject/${s.value.subject_id}`, query: q })
}
// 同组件路由切换（点上一个/下一个）时重新加载
watch(
  () => route.params.id,
  (v, o) => {
    if (v && v !== o) load()
  },
)

async function doUpload({ file }) {
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    await api.post(`/scores/${route.params.id}/images`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    ElMessage.success('已上传')
    images.value = (await api.get(`/scores/${route.params.id}/images`)).data
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    uploading.value = false
  }
}

async function delImage(img) {
  try {
    await api.delete(`/scores/images/${img.id}`)
    images.value = images.value.filter((i) => i.id !== img.id)
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

function onDragStart(idx, e) {
  dragIndex.value = idx
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(idx))
  }
}

function onDragOver(idx) {
  if (dragIndex.value >= 0 && dragIndex.value !== idx) dragOverIndex.value = idx
}

function onDragLeave(idx) {
  if (dragOverIndex.value === idx) dragOverIndex.value = -1
}

function onDragEnd() {
  dragIndex.value = -1
  dragOverIndex.value = -1
}

async function onDrop(idx) {
  const from = dragIndex.value
  dragIndex.value = -1
  dragOverIndex.value = -1
  if (from < 0 || from === idx) return
  const list = images.value.slice()
  const [moved] = list.splice(from, 1)
  list.splice(idx, 0, moved)
  images.value = list
  try {
    await api.patch(`/scores/${route.params.id}/images/order`, { ids: list.map((i) => i.id) })
  } catch (e) {
    ElMessage.error(errMsg(e))
    images.value = (await api.get(`/scores/${route.params.id}/images`)).data
  }
}

onMounted(load)
</script>

<style scoped>
.page-head {
  margin-bottom: 16px;
}
.star {
  cursor: pointer;
  color: #c0c4cc;
  font-size: 20px;
  margin-left: 6px;
  vertical-align: -2px;
  user-select: none;
  transition: color 0.15s;
}
.star.on {
  color: #f7ba2a;
}
.color-dot {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 3px;
  margin-right: 6px;
  vertical-align: middle;
}
.muted {
  color: #909399;
  font-size: 13px;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px 12px;
}
.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  white-space: nowrap;
}
.card-title::before {
  content: '';
  width: 3px;
  height: 14px;
  border-radius: 2px;
  background: #409eff;
}
.head-ops {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.linked-item {
  cursor: pointer;
}
.img-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  color: #909399;
  font-size: 12px;
}
.picker-tip {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}
.brief-title {
  font-weight: 600;
  color: #303133;
}
.brief-line {
  font-size: 12px;
  color: #606266;
  white-space: pre-wrap;
}
.img-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
}
.img-item {
  width: 172px;
  padding: 8px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fff;
  cursor: grab;
  transition: box-shadow 0.2s, border-color 0.2s, opacity 0.2s;
}
.img-item.dragging {
  opacity: 0.45;
  cursor: grabbing;
}
.img-item.drag-over {
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.15);
}
.img-item:hover {
  border-color: #dcdfe6;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
}
.img-thumb {
  display: block;
  width: 100%;
  height: 118px;
  border-radius: 6px;
  background: #f5f7fa;
}
.img-op {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin-top: 8px;
}
.img-name {
  font-size: 12px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.img-actions {
  display: flex;
  justify-content: space-between;
  gap: 4px;
  margin-top: 4px;
  padding-top: 4px;
  border-top: 1px dashed #ebeef5;
}
.img-actions :deep(.el-button) {
  padding: 2px 4px;
  font-size: 12px;
}
</style>
