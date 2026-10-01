<template>
  <div>
    <!-- ============ 单科成绩 ============ -->
    <div v-if="tab === 'single'">
        <div class="page-head">
          <h3>{{ pageTitle }}</h3>
        </div>
        <!-- 筛选栏 -->
        <el-form inline class="filter">
          <el-form-item label="孩子">
            <el-select v-model="q.child_id" clearable style="width: 110px">
              <el-option v-for="c in store.children" :key="c.id" :value="c.id" :label="c.name" />
            </el-select>
          </el-form-item>
          <el-form-item label="学科">
            <el-select v-model="q.subject_id" clearable style="width: 110px">
              <el-option v-for="s in subjects" :key="s.id" :value="s.id" :label="s.name" />
            </el-select>
          </el-form-item>
          <el-form-item label="类型">
            <el-select v-model="q.type" clearable style="width: 120px">
              <el-option v-for="t in examTypes" :key="t" :value="t" :label="t" />
            </el-select>
          </el-form-item>
          <el-form-item label="年级">
            <el-select v-model="q.grade" clearable style="width: 100px">
              <el-option v-for="g in 9" :key="g" :value="g" :label="gradeLabel(g)" />
            </el-select>
          </el-form-item>
          <el-form-item label="学期">
            <el-select v-model="q.term" clearable filterable style="width: 170px">
              <el-option v-for="t in terms" :key="t" :value="t" :label="t" />
            </el-select>
          </el-form-item>
          <el-form-item label="日期">
            <el-date-picker
              v-model="range"
              type="daterange"
              value-format="YYYY-MM-DD"
              start-placeholder="开始"
              end-placeholder="结束"
              style="width: 240px"
            />
          </el-form-item>
          <el-form-item>
            <el-button :icon="Search" @click="load">查询</el-button>
            <el-button @click="reset">重置</el-button>
            <el-button type="primary" @click="openScoreCreate">新建成绩</el-button>
          </el-form-item>
        </el-form>

        <el-table :data="pagedList" v-loading="loading" size="small" @row-click="(row) => $router.push(`/score/${row.id}`)" style="cursor: pointer">
          <el-table-column prop="starred" label="☆" width="50" sortable :sort-method="(a, b) => (b.starred ? 1 : 0) - (a.starred ? 1 : 0)">
            <template #default="{ row }">
              <span :class="row.starred ? 'star-on' : 'star-off'">{{ row.starred ? '★' : '☆' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="date" label="日期" width="105" sortable />
          <el-table-column prop="subject_name" label="学科" width="90" sortable>
            <template #default="{ row }">
              <span class="color-dot" :style="{ background: row.subject_color }" />{{ row.subject_name }}
            </template>
          </el-table-column>
          <el-table-column prop="type" label="类型" min-width="95" sortable />
          <el-table-column prop="grade" label="年级" min-width="75" sortable :sort-method="(a, b) => (a.grade || 0) - (b.grade || 0)">
            <template #default="{ row }">{{ gradeLabel(row.grade) }}</template>
          </el-table-column>
          <el-table-column prop="term" label="学期" min-width="85" sortable>
            <template #default="{ row }">{{ shortTerm(row.term) }}</template>
          </el-table-column>
          <el-table-column
            prop="unit_names"
            label="单元"
            min-width="100"
            sortable
            :sort-method="(a, b) => (a.exam_name || a.unit_names || '').localeCompare(b.exam_name || b.unit_names || '', 'zh')"
          >
            <template #default="{ row }">{{ row.exam_name || row.unit_names || '-' }}</template>
          </el-table-column>
          <el-table-column prop="regular_score" label="得分" width="85" sortable :sort-method="(a, b) => ((a.regular_score || 0) + (a.bonus_score || 0)) - ((b.regular_score || 0) + (b.bonus_score || 0))">
            <template #default="{ row }">{{ earnedLabel(row) }}</template>
          </el-table-column>
          <el-table-column prop="class_rank" label="名次" width="65" sortable :sort-method="(a, b) => rankNum(a.class_rank ?? Infinity) - rankNum(b.class_rank ?? Infinity)">
            <template #default="{ row }">{{ row.class_rank ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="125">
            <template #default="{ row }">
              <el-button size="small" type="primary" text @click.stop="openEdit(row)">编辑</el-button>
              <el-button size="small" type="danger" text @click.stop="del(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="list.length"
          layout="total, prev, pager, next"
          class="pager"
        />
    </div>

    <!-- ============ 考试场次 ============ -->
    <div v-else>
        <div class="page-head">
          <h3>考试场次</h3>
        </div>
        <el-form inline class="filter">
          <el-form-item label="孩子">
            <el-select v-model="eq.child_id" clearable style="width: 110px">
              <el-option v-for="c in store.children" :key="c.id" :value="c.id" :label="c.name" />
            </el-select>
          </el-form-item>
          <el-form-item label="年级">
            <el-select v-model="eq.grade" clearable style="width: 100px">
              <el-option v-for="g in 9" :key="g" :value="g" :label="gradeLabel(g)" />
            </el-select>
          </el-form-item>
          <el-form-item label="学期">
            <el-select v-model="eq.term" clearable filterable style="width: 170px">
              <el-option v-for="t in examTerms" :key="t" :value="t" :label="t" />
            </el-select>
          </el-form-item>
          <el-form-item label="类型">
            <el-select v-model="eq.type" clearable style="width: 120px">
              <el-option v-for="t in examTypes" :key="t" :value="t" :label="t" />
            </el-select>
          </el-form-item>
          <el-form-item label="日期">
            <el-date-picker
              v-model="erange"
              type="daterange"
              value-format="YYYY-MM-DD"
              start-placeholder="开始"
              end-placeholder="结束"
              style="width: 240px"
            />
          </el-form-item>
          <el-form-item label="名称">
            <el-input v-model="eq.name" clearable placeholder="关键词" style="width: 150px" @keyup.enter="loadExams" />
          </el-form-item>
          <el-form-item>
            <el-button :icon="Search" @click="loadExams">查询</el-button>
            <el-button @click="resetExamFilter">重置</el-button>
            <el-button type="primary" @click="openCreate">新建场次</el-button>
          </el-form-item>
        </el-form>

        <el-table :data="pagedExams" v-loading="examLoading" size="small" @row-click="(row) => $router.push(`/exam/${row.id}`)" style="cursor: pointer">
          <el-table-column prop="starred" label="☆" width="50" sortable :sort-method="(a, b) => (b.starred ? 1 : 0) - (a.starred ? 1 : 0)">
            <template #default="{ row }">
              <span :class="row.starred ? 'star-on' : 'star-off'">{{ row.starred ? '★' : '☆' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="date" label="日期" width="105" sortable />
          <el-table-column prop="name" label="场次名称" width="150" sortable />
          <el-table-column prop="type" label="类型" min-width="100" sortable />
          <el-table-column prop="grade" label="年级" min-width="80" sortable :sort-method="(a, b) => (a.grade || 0) - (b.grade || 0)">
            <template #default="{ row }">{{ gradeLabel(row.grade) }}</template>
          </el-table-column>
          <el-table-column prop="term" label="学期" min-width="85" sortable>
            <template #default="{ row }">{{ shortTerm(row.term) }}</template>
          </el-table-column>
          <el-table-column label="总分" min-width="100" sortable :sort-method="(a, b) => (b.rate ?? 0) - (a.rate ?? 0)">
            <template #default="{ row }">
              {{ row.bonus_earned ? `${row.regular_earned}（${row.bonus_earned}）` : row.regular_earned }}
            </template>
          </el-table-column>
          <el-table-column prop="class_rank" label="名次" min-width="70" sortable :sort-method="(a, b) => rankNum(a.class_rank ?? Infinity) - rankNum(b.class_rank ?? Infinity)">
            <template #default="{ row }">{{ row.class_rank ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="125">
            <template #default="{ row }">
              <el-button size="small" type="primary" text @click.stop="openExamEdit(row)">编辑</el-button>
              <el-button size="small" type="danger" text @click.stop="delExam(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination
          v-model:current-page="epage"
          :page-size="pageSize"
          :total="filteredExams.length"
          layout="total, prev, pager, next"
          class="pager"
        />
    </div>

    <!-- 新建/编辑成绩（列表与详情页共用同一弹窗） -->
    <ScoreEditDialog v-model="showScoreDialog" :score="editingScore" @saved="onScoreSaved" />

    <!-- 新建/编辑考试场次（列表与详情页共用同一弹窗） -->
    <ExamEditDialog v-model="showExamDialog" :exam="editingExam" @saved="onExamSaved" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, errMsg } from '../api'
import { store } from '../store'
import { earnedLabel, examTypes, gradeLabel, rankNum, shortTerm } from '../utils'
import ScoreEditDialog from '../components/ScoreEditDialog.vue'
import ExamEditDialog from '../components/ExamEditDialog.vue'

const route = useRoute()
const router = useRouter()
const tab = ref(route.query.tab === 'exam' ? 'exam' : 'single')

// 新建/编辑弹窗：列表与详情页共用同一组件，editingXxx 为 null 表示新建
const showScoreDialog = ref(false)
const editingScore = ref(null)
const showExamDialog = ref(false)
const editingExam = ref(null)

function openEdit(row) {
  editingScore.value = row
  showScoreDialog.value = true
}

function openScoreCreate() {
  if (!store.children.length) return ElMessage.warning('请先到「孩子管理」添加孩子')
  editingScore.value = null
  showScoreDialog.value = true
}

function openCreate() {
  editingExam.value = null
  showExamDialog.value = true
}

function openExamEdit(row) {
  editingExam.value = row
  showExamDialog.value = true
}

function onScoreSaved() {
  load()
}

function onExamSaved(data, isCreate) {
  if (isCreate) router.push(`/exam/${data.id}`)
  loadExams()
}

// 支持从其他页面带筛选条件跳转进来（如总览的学科卡片）
const q = ref({
  child_id: Number(route.query.child_id) || null,
  subject_id: Number(route.query.subject_id) || null,
  type: route.query.type || null,
  grade: Number(route.query.grade) || null,
  term: route.query.term || null,
})
const range = ref(null)
const list = ref([])
const subjects = ref([])
const loading = ref(false)

const terms = computed(() => {
  const set = new Set()
  list.value.forEach((s) => s.term && set.add(s.term))
  return [...set].sort().reverse()
})

async function load() {
  loading.value = true
  try {
    const params = { ...q.value }
    if (range.value) {
      params.date_from = range.value[0]
      params.date_to = range.value[1]
    }
    Object.keys(params).forEach((k) => params[k] == null && delete params[k])
    const { data } = await api.get('/scores', { params })
    list.value = data
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    loading.value = false
  }
}

function reset() {
  q.value = { child_id: null, subject_id: null, type: null, grade: null, term: null }
  range.value = null
  load()
}

async function del(row) {
  try {
    await api.delete(`/scores/${row.id}`)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

onMounted(async () => {
  try {
    const [s, c] = await Promise.all([api.get('/subjects'), api.get('/children')])
    subjects.value = s.data
    store.children = c.data
    if (store.childId && !store.children.some((x) => x.id === store.childId)) {
      store.childId = store.children[0]?.id ?? null
    }
  } finally {
    load()
  }
  if (tab.value === 'exam') loadExams()
})

// 切到场次 TAB 时再加载（首次进入不用白拉一次）
watch(tab, (v) => {
  if (v === 'exam' && !exams.value.length) loadExams()
})

// 页头标题：单科/场次
const pageTitle = computed(() => {
  if (tab.value === 'exam') return '考试场次'
  return '单科成绩'
})

// 菜单切换「单科成绩/考试场次/竞赛成绩/练习成绩」子项时，组件被复用，需跟随 query 更新
watch(
  () => [route.query.tab, route.query.type],
  ([t, ty]) => {
    const newTab = t === 'exam' ? 'exam' : 'single'
    if (newTab !== tab.value) {
      tab.value = newTab
    }
    const newType = ty || null
    if (newType !== q.value.type) {
      q.value.type = newType
      if (newTab === 'single') load()
    }
  },
)

// ============ 考试场次 TAB ============
const exams = ref([])
const examLoading = ref(false)
const eq = ref({ child_id: null, grade: null, term: null, type: null, name: '' })
const erange = ref(null)

const examTerms = computed(() => {
  const set = new Set()
  exams.value.forEach((e) => e.term && set.add(e.term))
  return [...set].sort().reverse()
})

// 前端过滤：数据量小，不依赖后端检索参数
const filteredExams = computed(() =>
  exams.value.filter(
    (e) =>
      (!eq.value.child_id || e.child_id === eq.value.child_id) &&
      (!eq.value.grade || e.grade === eq.value.grade) &&
      (!eq.value.term || e.term === eq.value.term) &&
      (!eq.value.type || e.type === eq.value.type) &&
      (!eq.value.name || (e.name || '').includes(eq.value.name)) &&
      (!erange.value || (e.date >= erange.value[0] && e.date <= erange.value[1])),
  ),
)

// 分页：每页 10 行，页码在表格右下角
const pageSize = 10
const page = ref(1)
const epage = ref(1)
const pagedList = computed(() => list.value.slice((page.value - 1) * pageSize, page.value * pageSize))
const pagedExams = computed(() => filteredExams.value.slice((epage.value - 1) * pageSize, epage.value * pageSize))
watch(list, () => (page.value = 1))        // 数据刷新后回到第一页
watch(filteredExams, () => (epage.value = 1))

function resetExamFilter() {
  eq.value = { child_id: null, grade: null, term: null, type: null, name: '' }
  erange.value = null
}

async function loadExams() {
  examLoading.value = true
  try {
    exams.value = (await api.get('/exams')).data
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    examLoading.value = false
  }
}

async function delExam(row) {
  try {
    await ElMessageBox.confirm(`确定删除场次「${row.name}」吗？场内成绩会退回独立状态，不会被删除。`, '删除场次', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await api.delete(`/exams/${row.id}`)
    ElMessage.success('已删除')
    loadExams()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}
</script>

<style scoped>
/* 页面标题头：各页统一（标题居左） */
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.page-head h3 {
  margin: 0;
}
/* 分页：靠右下角 */
.pager {
  justify-content: flex-end;
  margin-top: 8px;
}
/* 弹窗表单行距紧凑、底部按钮上提，避免滚动 */
:deep(.el-dialog .el-form-item) {
  margin-bottom: 6px;
}
:deep(.el-dialog .el-form-item__label) {
  padding-bottom: 0;
  line-height: 20px;
}
:deep(.el-dialog__body) {
  padding-bottom: 0;
}
:deep(.el-dialog__footer) {
  padding-top: 6px;
}
.filter :deep(.el-form-item) {
  margin-bottom: 8px;
}
.list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.muted {
  color: #909399;
}
.star-on {
  color: #f7ba2a;
  font-size: 15px;
}
.star-off {
  color: #dcdfe6;
  font-size: 15px;
}
.hint {
  color: #909399;
  font-size: 12px;
  line-height: 1.4;
}
.color-dot {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 3px;
  margin-right: 6px;
}
</style>
