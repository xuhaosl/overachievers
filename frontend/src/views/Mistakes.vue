<template>
  <div>
    <div class="page-head">
      <h3>错题整理</h3>
      <div class="head-ops">
        <el-select v-if="store.children.length > 1" v-model="childId" style="width: 110px" @change="onChildChange">
          <el-option v-for="c in store.children" :key="c.id" :value="c.id" :label="c.name" />
        </el-select>
        <el-button :icon="MagicStick" @click="openAi">上传图片识别</el-button>
        <el-button v-if="!selectedNotebook" type="primary" :icon="Plus" @click="openNotebookCreate">新建错题本</el-button>
        <el-button v-else type="primary" :icon="Plus" @click="openMistakeCreate">新建错题</el-button>
      </div>
    </div>

    <!-- ============ 错题本卡片墙 ============ -->
    <template v-if="!selectedNotebook">
      <el-empty v-if="!notebooks.length" description="还没有错题本，先建一个吧（例如「数学错题本」）">
        <el-button type="primary" @click="openNotebookCreate">新建错题本</el-button>
      </el-empty>
      <div v-else class="nb-grid">
        <div v-for="nb in notebooks" :key="nb.id" class="nb-card" @click="openNotebook(nb)">
          <div class="nb-top">
            <el-icon :size="20"><Collection /></el-icon>
            <span class="nb-name">{{ nb.name }}</span>
          </div>
          <div class="nb-meta">{{ nb.set_count }} 个错题集 · {{ nb.mistake_count }} 道错题</div>
          <div class="nb-ops" @click.stop>
            <el-button link size="small" @click="promptRenameNotebook(nb)">重命名</el-button>
            <el-button link size="small" type="danger" @click="removeNotebook(nb)">删除</el-button>
          </div>
        </div>
      </div>
    </template>

    <!-- ============ 错题本内部 ============ -->
    <template v-else>
      <div class="crumb">
        <el-button link @click="backToWall">← 全部错题本</el-button>
        <span class="crumb-title">{{ selectedNotebook.name }}</span>
        <span class="muted">{{ childName }}</span>
        <span class="grow" />
        <el-button size="small" @click="openSetCreate">新建错题集</el-button>
        <el-button size="small" @click="setManageVisible = true">管理错题集</el-button>
        <el-button size="small" type="warning" plain @click="openReview">开始重做</el-button>
        <el-button size="small" @click="printVisible = true">打印</el-button>
      </div>

      <div class="set-tabs">
        <el-check-tag
          v-for="s in sets"
          :key="s.id"
          :checked="selectedSet === s.id"
          @change="selectSet(s.id)"
        >
          {{ s.name }}（{{ s.mistake_count }}）
        </el-check-tag>
      </div>

      <el-form inline class="filter">
        <el-form-item label="状态">
          <el-select v-model="q.mastered" clearable placeholder="全部" style="width: 110px">
            <el-option label="未掌握" value="false" />
            <el-option label="已掌握" value="true" />
          </el-select>
        </el-form-item>
        <el-form-item label="知识点">
          <el-select v-model="q.unit_id" clearable filterable placeholder="全部" style="width: 200px">
            <el-option v-for="u in unitOptions" :key="u.id" :value="u.id" :label="u.label" />
          </el-select>
        </el-form-item>
        <el-form-item label="搜索">
          <el-input v-model="q.keyword" clearable placeholder="题干/错因/标签" style="width: 180px" @keyup.enter="loadMistakes" />
        </el-form-item>
        <el-form-item>
          <el-button :icon="Search" @click="loadMistakes">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>

      <el-empty v-if="!loading && !mistakes.length" description="当前范围内还没有错题">
        <el-button v-if="sets.length" type="primary" @click="openMistakeCreate">新增错题</el-button>
        <el-button v-else type="primary" @click="openSetCreate">先建一个错题集</el-button>
      </el-empty>

      <el-table
        v-else
        v-loading="loading"
        :data="mistakes"
        size="small"
        border
        style="cursor: pointer"
        @row-click="openDetail"
      >
        <el-table-column label="图" width="64">
          <template #default="{ row }">
            <el-image
              v-if="row.image_url"
              :src="row.image_url"
              :preview-src-list="[row.image_url]"
              preview-teleported
              fit="cover"
              class="thumb"
              @click.stop
            />
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="题目" min-width="300">
          <template #default="{ row }">
            <div class="brief">
              <div class="brief-title">{{ row.title || '错题' }}</div>
              <div v-for="(line, i) in briefLines(row.stem)" :key="i" class="brief-line">{{ line }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="知识点" min-width="150">
          <template #default="{ row }">
            <span>{{ [row.unit_names, row.knowledge_tags].filter(Boolean).join('、') || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="错因" min-width="150">
          <template #default="{ row }">
            <div v-if="row.reason" class="reason-cell">{{ row.reason }}</div>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-switch
              :model-value="row.mastered"
              inline-prompt
              active-text="会"
              inactive-text="不会"
              @click.stop
              @change="toggleMastered(row)"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="110">
          <template #default="{ row }">
            <el-button link size="small" @click.stop="openEdit(row)">编辑</el-button>
            <el-button link size="small" type="danger" @click.stop="removeMistake(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- 错题本新建/重命名 -->
    <el-dialog v-model="notebookDialog.visible" :title="notebookDialog.id ? '重命名错题本' : '新建错题本'" width="420px">
      <el-input v-model="notebookDialog.name" placeholder="例如 数学错题本" maxlength="100" @keyup.enter="saveNotebook" />
      <template #footer>
        <el-button @click="notebookDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="saveNotebook">保存</el-button>
      </template>
    </el-dialog>

    <!-- 新建错题集 -->
    <el-dialog v-model="setDialog.visible" title="新建错题集" width="420px">
      <el-input v-model="setDialog.name" placeholder="例如 五上错题集" maxlength="100" @keyup.enter="saveSet" />
      <template #footer>
        <el-button @click="setDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="saveSet">保存</el-button>
      </template>
    </el-dialog>

    <!-- 管理错题集 -->
    <el-dialog v-model="setManageVisible" title="管理错题集" width="520px">
      <el-table :data="sets" size="small" border>
        <el-table-column prop="name" label="名称" />
        <el-table-column prop="mistake_count" label="错题数" width="90" />
        <el-table-column label="操作" width="130">
          <template #default="{ row }">
            <el-button link size="small" @click="promptRenameSet(row)">重命名</el-button>
            <el-button link size="small" type="danger" @click="removeSet(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="setManageVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 错题详情 -->
    <el-dialog v-model="detailVisible" title="错题详情" width="720px" top="6vh">
      <div v-if="detail" class="detail">
        <el-image
          v-if="detail.image_url"
          :src="detail.image_url"
          :preview-src-list="[detail.image_url]"
          preview-teleported
          fit="contain"
          class="detail-img"
        />
        <el-image
          v-if="detail.figure_url"
          :src="detail.figure_url"
          :preview-src-list="[detail.figure_url]"
          preview-teleported
          fit="contain"
          class="detail-img detail-figure"
        />
        <div class="detail-row" v-if="detail.title"><b>标题：</b>{{ detail.title }}</div>
        <div class="detail-row"><b>题目：</b><span v-if="detail.question_no">第 {{ detail.question_no }} 题 </span>{{ detail.stem || '（仅截图）' }}</div>
        <div class="detail-row"><b>我的答案：</b>{{ detail.my_answer || '-' }}</div>
        <div class="detail-row"><b>正确答案：</b>{{ detail.correct_answer || '-' }}</div>
        <div class="detail-row"><b>解析：</b>{{ detail.explanation || '-' }}</div>
        <div class="detail-row"><b>错因：</b>{{ detail.reason || '-' }}</div>
        <div class="detail-row"><b>知识点：</b>{{ [detail.unit_names, detail.knowledge_tags].filter(Boolean).join('、') || '-' }}</div>
        <div class="detail-row"><b>所属错题集：</b>{{ detail.sets.map((s) => s.name).join('、') }}</div>
        <div class="detail-row"><b>状态：</b>{{ detail.mastered ? '已掌握' : '未掌握' }}</div>
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button type="primary" @click="editFromDetail">编辑</el-button>
      </template>
    </el-dialog>

    <!-- 重做模式 -->
    <el-dialog v-model="reviewVisible" title="错题重做" width="640px" top="6vh" @close="reviewList = []">
      <template v-if="reviewList.length">
        <div class="review-head">
          <span>第 {{ reviewIndex + 1 }} / {{ reviewList.length }} 道</span>
          <span class="grow" />
          <el-radio-group v-model="reviewOrder" size="small" :disabled="reviewIndex > 0" @change="reorderReview">
            <el-radio-button value="order">顺序</el-radio-button>
            <el-radio-button value="random">随机</el-radio-button>
          </el-radio-group>
        </div>
        <div v-if="reviewCurrent?.image_url" class="review-img-wrap">
          <el-image :src="reviewCurrent.image_url" :preview-src-list="[reviewCurrent.image_url]" preview-teleported fit="contain" class="review-img" />
        </div>
        <div v-if="reviewCurrent?.figure_url" class="review-img-wrap">
          <el-image :src="reviewCurrent.figure_url" :preview-src-list="[reviewCurrent.figure_url]" preview-teleported fit="contain" class="review-img review-figure" />
        </div>
        <div class="review-stem">
          <span v-if="reviewCurrent?.question_no" class="qn">第 {{ reviewCurrent.question_no }} 题</span>
          {{ reviewCurrent?.stem || '（仅截图，请对照上方图片）' }}
        </div>
        <div v-if="showAnswer" class="review-answer">
          <div><b>我的答案：</b>{{ reviewCurrent?.my_answer || '-' }}</div>
          <div><b>正确答案：</b>{{ reviewCurrent?.correct_answer || '-' }}</div>
          <div><b>解析：</b>{{ reviewCurrent?.explanation || '-' }}</div>
        </div>
        <div class="review-actions">
          <el-button v-if="!showAnswer" @click="showAnswer = true">显示答案</el-button>
          <span class="grow" />
          <el-button @click="nextReview(false)">还不会</el-button>
          <el-button type="success" @click="nextReview(true)">会了</el-button>
        </div>
      </template>
      <el-result v-else icon="success" title="本轮完成" :sub-title="`已掌握 ${reviewGot} 道错题`" />
    </el-dialog>

    <!-- 打印 -->
    <el-dialog v-model="printVisible" title="打印错题" width="420px">
      <p class="muted">范围：{{ printScopeLabel }}，共 {{ filteredMistakes.length }} 道</p>
      <el-checkbox v-model="printWithAnswer">打印答案与解析</el-checkbox>
      <template #footer>
        <el-button @click="printVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!filteredMistakes.length" @click="doPrint">开始打印</el-button>
      </template>
    </el-dialog>

    <MistakeEditDialog
      v-model="editVisible"
      :child-id="childId"
      :mistake="editingMistake"
      :defaults="editDefaults"
      @saved="onMistakeSaved"
    />
    <MistakeAiDialog
      v-model="aiVisible"
      :child-id="childId"
      :set-ids="aiDefaultSetIds"
      @saved="onMistakeSaved"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Collection, MagicStick, Plus, Search } from '@element-plus/icons-vue'
import { api, errMsg } from '../api'
import { store, setChild } from '../store'
import MistakeEditDialog from '../components/MistakeEditDialog.vue'
import MistakeAiDialog from '../components/MistakeAiDialog.vue'

const childId = ref(null)
const notebooks = ref([])
const sets = ref([])
const mistakes = ref([])
const selectedNotebook = ref(null)
const selectedSet = ref(0)
const loading = ref(false)
const unitGroups = ref([])
const q = reactive({ mastered: '', unit_id: '', keyword: '' })

const notebookDialog = reactive({ visible: false, id: null, name: '' })
const setDialog = reactive({ visible: false, name: '' })
const setManageVisible = ref(false)
const editVisible = ref(false)
const editingMistake = ref(null)
const editDefaults = ref({})
const aiVisible = ref(false)
const aiDefaultSetIds = ref([])
const detailVisible = ref(false)
const detail = ref(null)

const reviewVisible = ref(false)
const reviewList = ref([])
const reviewIndex = ref(0)
const reviewOrder = ref('order')
const showAnswer = ref(false)
const reviewGot = ref(0)

const printVisible = ref(false)
const printWithAnswer = ref(false)

const childName = computed(() => store.children.find((c) => c.id === childId.value)?.name || '')
const filteredMistakes = computed(() => mistakes.value)
const printScopeLabel = computed(() => {
  const nb = selectedNotebook.value?.name || ''
  if (selectedSet.value) {
    const s = sets.value.find((x) => x.id === selectedSet.value)
    return `${nb} / ${s?.name || ''}`
  }
  return nb
})
const unitOptions = computed(() => {
  const out = []
  for (const g of unitGroups.value) {
    for (const u of g.units) {
      out.push({
        id: u.id,
        label: `${g.subject_name} · 第${u.sort_no}单元${u.name ? '（' + u.name + '）' : ''}`,
      })
    }
  }
  return out
})
const reviewCurrent = computed(() => reviewList.value[reviewIndex.value] || null)

onMounted(async () => {
  if (!store.children.length) {
    try {
      const { data } = await api.get('/children')
      store.children = data
    } catch (e) {
      ElMessage.error(errMsg(e))
    }
  }
  childId.value = store.childId || store.children[0]?.id || null
  if (childId.value) {
    setChild(childId.value)
    await loadNotebooks()
    await loadUnits()
  }
})

function onChildChange() {
  setChild(childId.value)
  selectedNotebook.value = null
  selectedSet.value = 0
  loadNotebooks()
  loadUnits()
}

async function loadNotebooks() {
  if (!childId.value) return
  try {
    const { data } = await api.get('/mistakes/notebooks', { params: { child_id: childId.value } })
    notebooks.value = data
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function loadUnits() {
  try {
    const { data } = await api.get('/mistakes/units', { params: { child_id: childId.value } })
    unitGroups.value = data
  } catch {
    unitGroups.value = []
  }
}

async function loadSets() {
  if (!selectedNotebook.value) return
  const { data } = await api.get('/mistakes/notebooks/' + selectedNotebook.value.id + '/sets')
  sets.value = data
}

async function loadMistakes() {
  if (!childId.value) return
  loading.value = true
  try {
    const params = { child_id: childId.value, notebook_id: selectedNotebook.value?.id }
    if (selectedSet.value) params.set_id = selectedSet.value
    if (q.mastered !== '') params.mastered = q.mastered
    if (q.unit_id) params.unit_id = q.unit_id
    if (q.keyword.trim()) params.keyword = q.keyword.trim()
    const { data } = await api.get('/mistakes', { params })
    mistakes.value = data
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    loading.value = false
  }
}

async function openNotebook(nb) {
  selectedNotebook.value = nb
  await loadSets()
  selectedSet.value = sets.value[0]?.id || 0
  await loadMistakes()
}

async function backToWall() {
  selectedNotebook.value = null
  sets.value = []
  mistakes.value = []
  await loadNotebooks()
}

function selectSet(id) {
  selectedSet.value = id
  loadMistakes()
}

function resetFilters() {
  q.mastered = ''
  q.unit_id = ''
  q.keyword = ''
  loadMistakes()
}

async function refreshAll() {
  await loadNotebooks()
  if (selectedNotebook.value) {
    await loadSets()
    await loadMistakes()
    const fresh = notebooks.value.find((n) => n.id === selectedNotebook.value.id)
    if (fresh) selectedNotebook.value = fresh
  }
}

function openNotebookCreate() {
  notebookDialog.id = null
  notebookDialog.name = ''
  notebookDialog.visible = true
}

function promptRenameNotebook(nb) {
  notebookDialog.id = nb.id
  notebookDialog.name = nb.name
  notebookDialog.visible = true
}

async function saveNotebook() {
  const name = notebookDialog.name.trim()
  if (!name) return ElMessage.warning('请输入名称')
  try {
    if (notebookDialog.id) {
      await api.patch('/mistakes/notebooks/' + notebookDialog.id, { name })
    } else {
      await api.post('/mistakes/notebooks', { child_id: childId.value, name })
    }
    notebookDialog.visible = false
    await loadNotebooks()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function removeNotebook(nb) {
  await confirmThen(
    (confirm) => api.delete('/mistakes/notebooks/' + nb.id, { params: { confirm } }),
    `删除「${nb.name}」？`,
  )
  await loadNotebooks()
}

function openSetCreate() {
  setDialog.name = ''
  setDialog.visible = true
}

async function saveSet() {
  const name = setDialog.name.trim()
  if (!name) return ElMessage.warning('请输入名称')
  try {
    const { data } = await api.post('/mistakes/notebooks/' + selectedNotebook.value.id + '/sets', { name })
    setDialog.visible = false
    await loadSets()
    selectedSet.value = data.id
    await loadMistakes()
    await loadNotebooks()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

function promptRenameSet(s) {
  ElMessageBox.prompt('新的错题集名称', '重命名错题集', {
    inputValue: s.name,
    inputValidator: (v) => (!!v?.trim() || '名称不能为空'),
  })
    .then(async ({ value }) => {
      await api.patch('/mistakes/sets/' + s.id, { name: value.trim() })
      await loadSets()
      await loadNotebooks()
    })
    .catch(() => {})
}

async function removeSet(s) {
  await confirmThen(
    (confirm) => api.delete('/mistakes/sets/' + s.id, { params: { confirm } }),
    `删除错题集「${s.name}」？`,
  )
  if (selectedSet.value === s.id) selectedSet.value = 0
  await loadSets()
  if (!selectedSet.value) selectedSet.value = sets.value[0]?.id || 0
  await loadMistakes()
  await loadNotebooks()
}

async function confirmThen(fn, title) {
  try {
    await fn(false)
  } catch (e) {
    if (e.response?.status === 409) {
      try {
        await ElMessageBox.confirm(e.response.data.detail, title, { type: 'warning' })
        await fn(true)
        ElMessage.success('已删除')
      } catch {
        /* 取消 */
      }
    } else {
      ElMessage.error(errMsg(e))
    }
  }
}

function openMistakeCreate() {
  if (!sets.value.length) {
    ElMessage.warning('请先新建一个错题集')
    return
  }
  editingMistake.value = null
  editDefaults.value = { setIds: selectedSet.value ? [selectedSet.value] : [] }
  editVisible.value = true
}

function openEdit(row) {
  editingMistake.value = row
  editDefaults.value = {}
  editVisible.value = true
}

function editFromDetail() {
  detailVisible.value = false
  openEdit(detail.value)
}

function openDetail(row) {
  detail.value = row
  detailVisible.value = true
}

function openAi() {
  if (!sets.value.length) {
    ElMessage.warning('请先新建一个错题集，再识别试卷')
    return
  }
  aiDefaultSetIds.value = selectedSet.value ? [selectedSet.value] : []
  aiVisible.value = true
}

async function onMistakeSaved() {
  await refreshAll()
}

/** 列表摘要：大题合并记录优先列出各错小题，单题只取题干前两行。 */
function briefLines(stem) {
  const lines = String(stem || '')
    .split(/\n+/)
    .map((x) => x.trim())
    .filter(Boolean)
  if (!lines.length) return ['（仅截图）']
  const subLines = lines.filter((x) => /^[（(]\s*\d+\s*[）)]/.test(x))
  if (subLines.length) {
    return subLines.slice(0, 6).map((x) => x.replace(/^[（(]\s*(\d+)\s*[）)]\s*/, '$1. '))
  }
  return lines.slice(0, 2)
}

async function toggleMastered(row) {
  try {
    await api.patch(`/mistakes/${row.id}/mastered`, { mastered: !row.mastered })
    row.mastered = !row.mastered
    if (detail.value?.id === row.id) detail.value.mastered = row.mastered
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function removeMistake(row) {
  try {
    await ElMessageBox.confirm('删除这道错题？', '提示', { type: 'warning' })
    await api.delete('/mistakes/' + row.id)
    ElMessage.success('已删除')
    await refreshAll()
  } catch {
    /* 取消 */
  }
}

/* ---------- 重做 ---------- */
async function openReview() {
  try {
    const params = { child_id: childId.value, notebook_id: selectedNotebook.value?.id, mastered: false }
    if (selectedSet.value) params.set_id = selectedSet.value
    if (q.unit_id) params.unit_id = q.unit_id
    const { data } = await api.get('/mistakes', { params })
    if (!data.length) {
      ElMessage.info('当前范围没有未掌握的错题')
      return
    }
    reviewOrder.value = 'order'
    reviewList.value = data
    reviewIndex.value = 0
    showAnswer.value = false
    reviewGot.value = 0
    reviewVisible.value = true
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

function reorderReview() {
  if (reviewOrder.value === 'random') {
    reviewList.value = [...reviewList.value].sort(() => Math.random() - 0.5)
  } else {
    reviewList.value = [...reviewList.value].sort((a, b) => a.id - b.id)
  }
  reviewIndex.value = 0
  showAnswer.value = false
}

async function nextReview(got) {
  const cur = reviewCurrent.value
  if (got) {
    reviewGot.value += 1
    try {
      await api.patch(`/mistakes/${cur.id}/mastered`, { mastered: true })
    } catch {
      /* 失败不阻塞重做 */
    }
  }
  if (reviewIndex.value < reviewList.value.length - 1) {
    reviewIndex.value += 1
    showAnswer.value = false
  } else {
    reviewList.value = []
    await refreshAll()
  }
}

/* ---------- 打印 ---------- */
function esc(s) {
  return String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))
}

function doPrint() {
  const rows = filteredMistakes.value
  const origin = location.origin
  const body = rows
    .map((m, i) => {
      const img = m.image_url ? `<div class="img"><img src="${origin}${m.image_url}" /></div>` : ''
      const figure = m.figure_url ? `<div class="img fig"><img src="${origin}${m.figure_url}" /></div>` : ''
      const answer = printWithAnswer.value
        ? `<div class="ans"><p><b>我的答案：</b>${esc(m.my_answer) || '-'}</p>
           <p><b>正确答案：</b>${esc(m.correct_answer) || '-'}</p>
           <p><b>解析：</b>${esc(m.explanation) || '-'}</p>
           <p><b>错因：</b>${esc(m.reason) || '-'}</p></div>`
        : ''
      return `<section class="q">
        <div class="q-head">${i + 1}. ${m.question_no ? `第 ${esc(m.question_no)} 题` : ''}</div>
        ${img}
        ${figure}
        <div class="stem">${esc(m.stem) || '（仅截图）'}</div>
        ${answer}
      </section>`
    })
    .join('')
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>错题本</title>
  <style>
    body{font-family:"Microsoft YaHei",sans-serif;margin:24px;color:#222;font-size:14px;}
    h2{font-size:18px;margin:0 0 4px;}
    .meta{color:#888;font-size:12px;margin-bottom:16px;}
    .q{page-break-inside:avoid;border-bottom:1px dashed #ccc;padding:10px 0;}
    .q-head{font-weight:600;margin-bottom:6px;}
    .img img{max-width:100%;max-height:360px;object-fit:contain;}
    .img.fig img{max-height:240px;}
    .stem{line-height:1.7;margin:6px 0;}
    .ans{color:#555;font-size:13px;background:#f7f7f7;padding:6px 10px;border-radius:4px;}
    .ans p{margin:2px 0;}
  </style></head><body>
  <h2>${esc(childName.value)} · ${esc(printScopeLabel.value)}</h2>
  <div class="meta">共 ${rows.length} 道 · 打印日期 ${new Date().toLocaleDateString('zh-CN')}</div>
  ${body}
  </body></html>`
  const w = window.open('', '_blank')
  if (!w) return ElMessage.warning('浏览器拦截了新窗口，请允许弹窗后重试')
  w.document.write(html)
  w.document.close()
  setTimeout(() => {
    w.focus()
    w.print()
  }, 1200)
  printVisible.value = false
}
</script>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.page-head h3 {
  margin: 0;
}
.head-ops {
  display: flex;
  gap: 8px;
  align-items: center;
}
.nb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 14px;
}
.nb-card {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.15s;
  background: #fff;
}
.nb-card:hover {
  border-color: #409eff;
  box-shadow: 0 2px 10px rgba(64, 158, 255, 0.12);
}
.nb-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.nb-name {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}
.nb-meta {
  color: #909399;
  font-size: 13px;
}
.nb-ops {
  margin-top: 10px;
  height: 22px;
}
.crumb {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.crumb-title {
  font-size: 16px;
  font-weight: 600;
}
.muted {
  color: #909399;
  font-size: 13px;
}
.grow {
  flex: 1;
}
.set-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.filter {
  margin-bottom: 4px;
}
.thumb {
  width: 46px;
  height: 34px;
  border-radius: 4px;
  border: 1px solid #ebeef5;
}
.qn {
  color: #409eff;
  font-weight: 600;
  margin-right: 6px;
}
.brief {
  line-height: 1.6;
}
.brief-title {
  font-weight: 600;
  color: #303133;
  margin-bottom: 2px;
}
.brief-line {
  white-space: pre-wrap;
  font-size: 12px;
  color: #606266;
}
.reason-cell {
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
  white-space: pre-wrap;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.stem-clip {
  display: inline-block;
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
.detail-img {
  max-width: 100%;
  max-height: 360px;
  margin-bottom: 12px;
}
.detail-figure {
  max-height: 240px;
}
.detail-row {
  line-height: 1.8;
  font-size: 14px;
  white-space: pre-wrap;
}
.review-head {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
  color: #606266;
}
.review-img-wrap {
  text-align: center;
}
.review-img {
  max-width: 100%;
  max-height: 300px;
}
.review-figure {
  max-height: 200px;
  margin-top: 6px;
}
.review-stem {
  font-size: 15px;
  line-height: 1.8;
  margin: 10px 0;
}
.review-answer {
  background: #f7f8fa;
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.8;
}
.review-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 14px;
}
</style>
