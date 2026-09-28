<template>
  <div>
    <el-alert
      v-if="!store.children.length"
      title="请先到「孩子管理」添加孩子，再到「学科管理」添加学科"
      type="info"
      :closable="false"
      style="margin-bottom: 12px"
    />

    <el-tabs v-model="tab" stretch>
      <!-- ================= 单条录入 ================= -->
      <el-tab-pane label="录一条" name="single">
        <el-form :model="f" label-width="100px" class="form" v-if="store.children.length">
          <el-row :gutter="16">
            <el-col :xs="24" :sm="12" :lg="8">
              <el-form-item label="孩子" required>
                <el-select v-model="f.child_id" @change="onChildChange" style="width: 100%">
                  <el-option v-for="c in store.children" :key="c.id" :value="c.id" :label="c.name" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12" :lg="8">
              <el-form-item label="学科" required>
                <el-select v-model="f.subject_id" @change="onSubjectChange" style="width: 100%">
                  <el-option v-for="s in subjects" :key="s.id" :value="s.id" :label="s.name" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12" :lg="8">
              <el-form-item label="类型" required>
                <el-select v-model="f.type" filterable allow-create default-first-option style="width: 100%">
                  <el-option v-for="t in examTypes" :key="t" :value="t" :label="t" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12" :lg="8" v-if="f.type === '单元测试'">
              <el-form-item label="单元">
                <el-select v-model="f.unit_id" clearable style="width: 100%">
                  <el-option v-for="u in units" :key="u.id" :value="u.id" :label="u.name" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12" :lg="8">
              <el-form-item label="日期" required>
                <el-date-picker v-model="f.date" type="date" value-format="YYYY-MM-DD" @change="onDateChange" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :xs="12" :sm="6" :lg="4">
              <el-form-item label="常规得分" required>
                <el-input-number v-model="f.regular_score" :min="0" :max="1000" controls-position="right" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :xs="12" :sm="6" :lg="4">
              <el-form-item label="常规总分" required>
                <el-input-number v-model="f.regular_total" :min="1" :max="1000" controls-position="right" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>

          <el-row :gutter="16">
            <el-col :xs="24" :sm="8">
              <el-form-item label="有附加分">
                <el-switch v-model="hasBonus" />
              </el-form-item>
            </el-col>
            <template v-if="hasBonus">
              <el-col :xs="12" :sm="8">
                <el-form-item label="附加得分">
                  <el-input-number v-model="f.bonus_score" :min="0" :max="200" controls-position="right" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :xs="12" :sm="8">
                <el-form-item label="附加总分">
                  <el-input-number v-model="f.bonus_total" :min="1" :max="200" controls-position="right" style="width: 100%" />
                </el-form-item>
              </el-col>
            </template>
          </el-row>

          <el-row :gutter="16">
            <el-col :xs="8" :sm="4">
              <el-form-item label="年级">
                <el-select v-model="f.grade" style="width: 100%">
                  <el-option v-for="g in 9" :key="g" :value="g" :label="gradeLabel(g)" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :xs="16" :sm="6">
              <el-form-item label="学期">
                <el-input v-model="f.term" placeholder="按日期自动推断" />
              </el-form-item>
            </el-col>
            <el-col :xs="8" :sm="4">
              <el-form-item label="年级名次">
                <el-input-number v-model="f.grade_rank" :min="1" controls-position="right" style="width: 100%" placeholder="可不填" />
              </el-form-item>
            </el-col>
            <el-col :xs="8" :sm="4">
              <el-form-item label="班级名次">
                <el-input-number v-model="f.class_rank" :min="1" controls-position="right" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :xs="8" :sm="4">
              <el-form-item label="班级人数">
                <el-input-number v-model="f.class_size" :min="1" controls-position="right" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
          <p class="hint">排名都可选填：知道年级名次就填年级名次，知道班级名次就填班级名次和班级总人数</p>

          <el-button type="primary" :loading="saving" @click="saveSingle">保存并继续录入</el-button>
        </el-form>
      </el-tab-pane>

      <!-- ================= 考试场次 ================= -->
      <el-tab-pane label="考试场次" name="exam" v-if="store.children.length">
        <el-row :gutter="16">
          <el-col :xs="24" :sm="10">
            <el-form label-width="100px">
              <el-form-item label="选择场次">
                <el-select v-model="examId" clearable placeholder="选择已有场次，或直接新建" style="width: 100%" @change="loadExam">
                  <el-option v-for="e in exams" :key="e.id" :value="e.id" :label="`${e.name}（${e.date}）`" />
                </el-select>
              </el-form-item>
            </el-form>
          </el-col>
        </el-row>

        <!-- 新建场次 -->
        <el-divider content-position="left">新建考试场次</el-divider>
        <el-form :model="e" label-width="100px" class="form">
          <el-row :gutter="16">
            <el-col :xs="24" :sm="12" :lg="6">
              <el-form-item label="孩子" required>
                <el-select v-model="e.child_id" style="width: 100%">
                  <el-option v-for="c in store.children" :key="c.id" :value="c.id" :label="c.name" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12" :lg="8">
              <el-form-item label="名称" required>
                <el-input v-model="e.name" placeholder="如：2026-2027上学期期中考试" />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12" :lg="6">
              <el-form-item label="日期" required>
                <el-date-picker v-model="e.date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12" :lg="4">
              <el-form-item label="类型">
                <el-select v-model="e.type" filterable allow-create style="width: 100%">
                  <el-option v-for="t in examTypes" :key="t" :value="t" :label="t" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <p class="hint">年级、学期按孩子当前年级和日期自动推断，可稍后在编辑里改</p>
          <el-button type="primary" plain :loading="saving" @click="createExam">创建场次</el-button>
        </el-form>

        <!-- 场次详情 -->
        <template v-if="exam">
          <el-divider content-position="left">场次详情</el-divider>
          <el-descriptions :column="isMobile ? 1 : 4" border size="small" style="margin-bottom: 12px">
            <el-descriptions-item label="场次">{{ exam.name }}</el-descriptions-item>
            <el-descriptions-item label="日期">{{ exam.date }}</el-descriptions-item>
            <el-descriptions-item label="类型">{{ exam.type }}</el-descriptions-item>
            <el-descriptions-item label="年级 / 学期">{{ gradeLabel(exam.grade) }} / {{ exam.term }}</el-descriptions-item>
          </el-descriptions>

          <!-- 总排名 -->
          <el-form inline label-width="90px">
            <el-form-item label="年级名次"><el-input-number v-model="exam.grade_rank" :min="1" controls-position="right" /></el-form-item>
            <el-form-item label="班级名次"><el-input-number v-model="exam.class_rank" :min="1" controls-position="right" /></el-form-item>
            <el-form-item label="班级人数"><el-input-number v-model="exam.class_size" :min="1" controls-position="right" /></el-form-item>
            <el-form-item>
              <el-button type="primary" plain :loading="saving" @click="saveRank">保存总排名</el-button>
            </el-form-item>
          </el-form>

          <!-- 已录成绩 -->
          <el-table :data="exam.scores" size="small" style="margin-bottom: 16px">
            <el-table-column prop="subject_name" label="学科" width="110" />
            <el-table-column label="得分" width="110">
              <template #default="{ row }">{{ earnedLabel(row) }}</template>
            </el-table-column>
            <el-table-column label="总分" width="80">
              <template #default="{ row }">{{ row.total }}</template>
            </el-table-column>
            <el-table-column label="得分率" width="90">
              <template #default="{ row }">{{ ratePercent(row.rate) }}</template>
            </el-table-column>
            <el-table-column label="年级名次" width="90">
              <template #default="{ row }">{{ row.grade_rank ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="班级名次" width="110">
              <template #default="{ row }">{{ row.class_rank != null ? `${row.class_rank}/${row.class_size ?? '?'}` : '-' }}</template>
            </el-table-column>
            <el-table-column>
              <template #default="{ row }">
                <el-button size="small" type="danger" text @click="delScore(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- 添加成绩 -->
          <el-divider content-position="left">添加各科成绩</el-divider>
          <el-form :model="sf" inline label-width="90px">
            <el-form-item label="学科" required>
              <el-select v-model="sf.subject_id" style="width: 130px" @change="onExamSubjectChange">
                <el-option v-for="s in subjects" :key="s.id" :value="s.id" :label="s.name" />
              </el-select>
            </el-form-item>
            <el-form-item label="常规得分" required>
              <el-input-number v-model="sf.regular_score" :min="0" :max="1000" controls-position="right" />
            </el-form-item>
            <el-form-item label="常规总分" required>
              <el-input-number v-model="sf.regular_total" :min="1" :max="1000" controls-position="right" />
            </el-form-item>
            <el-form-item label="附加得分">
              <el-input-number v-model="sf.bonus_score" :min="0" :max="200" controls-position="right" placeholder="无则不填" />
            </el-form-item>
            <el-form-item label="附加总分">
              <el-input-number v-model="sf.bonus_total" :min="1" :max="200" controls-position="right" />
            </el-form-item>
            <el-form-item label="年级名次">
              <el-input-number v-model="sf.grade_rank" :min="1" controls-position="right" />
            </el-form-item>
            <el-form-item label="班级名次">
              <el-input-number v-model="sf.class_rank" :min="1" controls-position="right" />
            </el-form-item>
            <el-form-item label="班级人数">
              <el-input-number v-model="sf.class_size" :min="1" controls-position="right" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving" @click="addScore">添加</el-button>
            </el-form-item>
          </el-form>
        </template>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api'
import { store } from '../store'
import { examTypes, gradeLabel, inferTerm, earnedLabel, ratePercent } from '../utils'

const tab = ref('single')
const isMobile = ref(window.innerWidth < 768)
const saving = ref(false)
const subjects = ref([])
const units = ref([])
const exams = ref([])

// 本地时区的今天（toISOString 是 UTC，晚上会错一天）
const today = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// ---------- 单条录入 ----------
const hasBonus = ref(false)
const emptySingle = () => ({
  child_id: store.childId || null,
  subject_id: null,
  type: '单元测试',
  unit_id: null,
  date: today(),
  regular_score: null,
  regular_total: null,
  bonus_score: null,
  bonus_total: null,
  grade: null,
  term: '',
  grade_rank: null,
  class_rank: null,
  class_size: null,
})
const f = ref(emptySingle())

function onChildChange(id) {
  const c = store.children.find((x) => x.id === id)
  if (c) f.value.grade = c.grade
}
function onSubjectChange(id) {
  const s = subjects.value.find((x) => x.id === id)
  if (s && s.default_total && !f.value.regular_total) f.value.regular_total = s.default_total
  f.value.unit_id = null
  units.value = []
  if (id) loadUnits(id)
}
function onDateChange(v) {
  f.value.term = inferTerm(v)
}

async function loadUnits(subjectId) {
  const { data } = await api.get(`/subjects/${subjectId}/units`)
  units.value = data
}

async function saveSingle() {
  if (!f.value.child_id || !f.value.subject_id) return ElMessage.warning('请选择孩子和学科')
  if (f.value.regular_score == null || !f.value.regular_total) return ElMessage.warning('请填得分和总分')
  saving.value = true
  try {
    await api.post('/scores', { ...f.value, bonus_score: hasBonus.value ? f.value.bonus_score : null, bonus_total: hasBonus.value ? f.value.bonus_total : null })
    ElMessage.success('已保存')
    // 保留孩子/学科/类型，清空分数，方便连续录入
    const keep = { child_id: f.value.child_id, subject_id: f.value.subject_id, type: f.value.type, grade: f.value.grade, unit_id: f.value.unit_id, regular_total: f.value.regular_total }
    f.value = { ...emptySingle(), ...keep }
    hasBonus.value = false
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    saving.value = false
  }
}

// ---------- 场次 ----------
const examId = ref(null)
const exam = ref(null)
const emptyExam = () => ({
  child_id: store.childId || null,
  name: '',
  date: today(),
  type: '期中测试',
})
const e = ref(emptyExam())
const emptyScore = () => ({
  subject_id: null,
  regular_score: null,
  regular_total: null,
  bonus_score: null,
  bonus_total: null,
  grade_rank: null,
  class_rank: null,
  class_size: null,
})
const sf = ref(emptyScore())

async function loadExams() {
  const { data } = await api.get('/exams', { params: { child_id: e.value.child_id || undefined } })
  exams.value = data
}
async function createExam() {
  if (!e.value.child_id || !e.value.name || !e.value.date) return ElMessage.warning('请填孩子、名称和日期')
  saving.value = true
  try {
    const { data } = await api.post('/exams', e.value)
    ElMessage.success('场次已创建，可逐科录分')
    await loadExams()
    examId.value = data.id
    loadExam(data.id)
    e.value = { ...emptyExam(), child_id: e.value.child_id, date: e.value.date }
  } catch (err) {
    ElMessage.error(errMsg(err))
  } finally {
    saving.value = false
  }
}
async function loadExam(id) {
  exam.value = null
  if (!id) return
  const { data } = await api.get(`/exams/${id}`)
  exam.value = data
}
async function saveRank() {
  try {
    await api.put(`/exams/${exam.value.id}`, {
      child_id: exam.value.child_id,
      name: exam.value.name,
      date: exam.value.date,
      type: exam.value.type,
      grade_rank: exam.value.grade_rank,
      class_rank: exam.value.class_rank,
      class_size: exam.value.class_size,
    })
    ElMessage.success('总排名已保存')
    loadExams()
  } catch (err) {
    ElMessage.error(errMsg(err))
  }
}
function onExamSubjectChange(id) {
  const s = subjects.value.find((x) => x.id === id)
  if (s && s.default_total) sf.value.regular_total = s.default_total
}
async function addScore() {
  if (!sf.value.subject_id || sf.value.regular_score == null || !sf.value.regular_total)
    return ElMessage.warning('请选学科并填得分和总分')
  saving.value = true
  try {
    await api.post('/scores', { ...sf.value, child_id: exam.value.child_id, exam_id: exam.value.id, type: exam.value.type })
    ElMessage.success('已添加')
    sf.value = emptyScore()
    loadExam(exam.value.id)
    loadExams()
  } catch (err) {
    ElMessage.error(errMsg(err))
  } finally {
    saving.value = false
  }
}
async function delScore(row) {
  try {
    await api.delete(`/scores/${row.id}`)
    loadExam(exam.value.id)
    loadExams()
  } catch (err) {
    ElMessage.error(errMsg(err))
  }
}

watch(
  () => store.childId,
  (v) => {
    if (v && tab.value === 'exam') loadExams()
  },
)

onMounted(async () => {
  try {
    const { data } = await api.get('/subjects')
    subjects.value = data
    if (f.value.child_id) onChildChange(f.value.child_id)
    if (store.childId) loadExams()
  } catch (err) {
    ElMessage.error(errMsg(err))
  }
})
</script>

<style scoped>
.form {
  max-width: 1100px;
}
.hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin: 4px 0 12px 8px;
}
</style>
