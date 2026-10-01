<template>
  <el-dialog :model-value="modelValue" :title="isCreate ? '新建成绩' : '编辑成绩'" width="640px" @update:model-value="$emit('update:modelValue', $event)">
    <el-form :model="form" label-position="top">
      <p v-if="!isCreate && form.exam_id" class="hint" style="margin: 0 0 8px">该成绩挂在场次下：孩子/日期/年级/学期跟随场次，请在场次编辑中修改</p>
      <el-row :gutter="12">
        <el-col :span="6">
          <el-form-item label="孩子" required>
            <el-select v-model="form.child_id" :disabled="!isCreate && !!form.exam_id" @change="onChildChange" style="width: 100%">
              <el-option v-for="c in children" :key="c.id" :value="c.id" :label="c.name" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label="学科" required>
            <el-select v-model="form.subject_id" @change="onSubjectChange" style="width: 100%">
              <el-option v-for="s in subjects" :key="s.id" :value="s.id" :label="s.name" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label="日期" required>
            <el-date-picker v-model="form.date" type="date" value-format="YYYY-MM-DD" style="width: 100%" :disabled="!isCreate && !!form.exam_id" @change="onDateChange" />
          </el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label="类型" required>
            <el-select v-model="form.type" filterable allow-create default-first-option @change="onTypeChange" style="width: 100%">
              <el-option v-for="t in examTypes" :key="t" :value="t" :label="t" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="6">
          <el-form-item label="年级">
            <el-select v-model="form.grade" :disabled="(!isCreate && !!form.exam_id) || gradeLocked" style="width: 100%">
              <el-option v-for="g in 9" :key="g" :value="g" :label="gradeLabel(g)" />
            </el-select>
            <div class="hint" v-if="isCreate && gradeLocked">按入学年份与日期自动推算</div>
          </el-form-item>
        </el-col>
        <el-col :span="9">
          <el-form-item label="学期">
            <el-input v-model="form.term" :disabled="!isCreate && !!form.exam_id" />
          </el-form-item>
        </el-col>
        <el-col v-if="form.type === '单元测试'" :span="9">
          <el-form-item label="单元">
            <el-select v-model="form.unit_ids" multiple clearable placeholder="可勾选多个单元" style="width: 100%">
              <el-option
                v-for="u in units"
                :key="u.id"
                :value="u.id"
                :label="`第${u.sort_no}单元${u.name ? `（${u.name}）` : ''}`"
              />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="6">
          <el-form-item label="常规得分" required>
            <el-input-number v-model="form.regular_score" :min="0" :max="1000" controls-position="right" style="width: 100%" @change="autoRank" />
          </el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label="常规总分" required>
            <el-input-number v-model="form.regular_total" :min="1" :max="1000" controls-position="right" style="width: 100%" @change="autoRank" />
          </el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label="附加得分">
            <el-input-number v-model="form.bonus_score" :min="0" :max="200" controls-position="right" style="width: 100%" @change="autoRank" />
          </el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label="附加总分">
            <el-input-number v-model="form.bonus_total" :min="1" :max="200" controls-position="right" style="width: 100%" @change="autoRank" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="6">
          <el-form-item label="年级名次">
            <el-input v-model="form.grade_rank" placeholder="如 3 或 前5" clearable />
          </el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label="班级名次">
            <el-input v-model="form.class_rank" placeholder="如 3 或 前5" clearable />
          </el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label="标签">
            <el-input v-model="form.tags" placeholder="如：粗心、难题" />
          </el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label="标星">
            <el-switch v-model="form.starred" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="6">
          <el-form-item label="最高分">
            <el-input-number v-model="form.high_score" :min="0" :max="1000" controls-position="right" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="18">
          <el-form-item label="最高得分者">
            <el-select v-model="form.high_scorer_list" multiple filterable clearable placeholder="班级最高分的同学，可多选" style="width: 100%">
              <el-option v-for="n in rivalOptions(form.child_id)" :key="n" :value="n" :label="n" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="备注">
        <el-input v-model="form.note" type="textarea" :rows="2" placeholder="选填，如：粗心丢了2分" />
      </el-form-item>
      <p class="hint">排名都可选填：知道年级名次就填年级名次，知道班级名次就填班级名次和班级总人数</p>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ isCreate ? '保存并继续录入' : '保存' }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, errMsg } from '../api'
import { store } from '../store'
import { currentClassRec, earnedLabel, examTypes, gradeLabel, inferTerm, pickClassAt } from '../utils'

const props = defineProps({
  modelValue: Boolean,
  score: { type: Object, default: null }, // null = 新建（录一条）
})
const emit = defineEmits(['update:modelValue', 'saved'])

const isCreate = computed(() => !props.score)
const children = ref([])
const classes = ref([])
const subjects = ref([])
const units = ref([])
const saving = ref(false)
const gradeLocked = ref(false)
const form = ref({})

onMounted(async () => {
  try {
    const [c, s, cls] = await Promise.all([api.get('/children'), api.get('/subjects'), api.get('/classes')])
    children.value = c.data
    subjects.value = s.data
    classes.value = cls.data
    store.children = children.value
  } catch {}
})

// 本地时区的今天（toISOString 是 UTC，晚上会错一天）
function today() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// 按孩子+日期推算年级：从孩子归属的班级记录里找该日期在读的那条（按其入学时间推算）
function gradeFor(childId, dateStr) {
  return pickClassAt(classes.value, childId, dateStr || today())?.grade ?? null
}

// 孩子是否有班级记录（有则年级自动推算锁定）
function hasClassRec(childId) {
  return classes.value.some((c) => c.child_id === childId && c.enroll_year)
}

// 新建（录一条）的默认值
function emptySingle() {
  const child = children.value.find((c) => c.id === store.childId)
  return {
    child_id: store.childId ?? null,
    subject_id: null,
    type: '单元测试',
    unit_ids: [],
    date: today(),
    regular_score: null,
    regular_total: null,
    bonus_score: null,
    bonus_total: null,
    grade: gradeFor(store.childId) ?? child?.grade ?? 1,
    term: inferTerm(today()),
    grade_rank: null,
    class_rank: null,
    tags: '',
    starred: false,
    high_score: null,
    high_scorer_list: [],
    note: '',
  }
}

// 每次打开弹窗：编辑用当前成绩数据，新建给默认值
watch(
  () => props.modelValue,
  (v) => {
    if (!v) return
    if (props.score) {
      const s = props.score
      gradeLocked.value = hasClassRec(s.child_id)
      form.value = { ...s, unit_ids: [...(s.unit_ids || [])], high_scorer_list: (s.high_scorer || '').split('、').filter(Boolean) }
      loadUnits(s)
    } else {
      if (!children.value.length) {
        ElMessage.warning('请先到「孩子管理」添加孩子')
        emit('update:modelValue', false)
        return
      }
      gradeLocked.value = hasClassRec(store.childId)
      form.value = emptySingle()
      units.value = []
    }
  },
)

// 满分自动记年级/班级第 1 名（名次留空时才自动填，可手动改）；
// 满分（含附加分）时孩子就是班级最高分：最高分自动=得分，最高得分者自动加孩子本人
function autoRank() {
  const f = form.value
  const earned = (f.regular_score || 0) + (f.bonus_score || 0)
  const total = (f.regular_total || 0) + (f.bonus_total || 0)
  if (total > 0 && earned === total) {
    if (f.grade_rank == null) f.grade_rank = 1
    if (f.class_rank == null) f.class_rank = 1
    f.high_score = earned
    const name = children.value.find((c) => c.id === f.child_id)?.name
    if (name && !(f.high_scorer_list || []).includes(name)) {
      f.high_scorer_list = [...(f.high_scorer_list || []), name]
    }
  }
}

// 单元下拉：按学科+学期过滤（学期由孩子+日期推算短名，如 四上）；已勾选但不在列表里的单元补进来保证回显
async function loadUnits(s) {
  units.value = []
  if (s.type !== '单元测试' || !s.subject_id) return
  try {
    const params = {}
    if (s.child_id && s.date) {
      params.child_id = s.child_id
      params.date = s.date
    } else if (s.term) {
      params.term = s.term
    }
    const { data } = await api.get(`/subjects/${s.subject_id}/units`, { params })
    units.value = [...data]
    for (const uid of s.unit_ids || []) {
      if (!units.value.some((u) => u.id === uid)) {
        units.value.push({ id: uid, sort_no: 0, name: `单元${uid}` })
      }
    }
  } catch {}
}

function onChildChange(id) {
  if (!isCreate.value && form.value.exam_id) return
  gradeLocked.value = hasClassRec(id)
  const g = gradeFor(id, form.value.date)
  if (g != null) form.value.grade = g
  // 换孩子后学期推算（短名）可能变化，单元列表跟着换
  form.value.unit_ids = []
  if (form.value.subject_id) loadUnits(form.value)
}

function onSubjectChange() {
  form.value.unit_ids = []
  units.value = []
  if (form.value.subject_id) loadUnits(form.value)
}

function onTypeChange() {
  if (form.value.type !== '单元测试') form.value.unit_ids = []
}

function onDateChange(v) {
  if (!v) return
  // 挂场次的成绩日期跟随场次，不联动
  if (!isCreate.value && form.value.exam_id) return
  form.value.term = inferTerm(v)
  // 年级按日期+孩子班级记录推算（有班级记录时）
  const g = gradeFor(form.value.child_id, v)
  if (g != null) form.value.grade = g
  // 学期变了，单元列表跟着换（单元按学期区分）
  form.value.unit_ids = []
  if (form.value.subject_id) loadUnits(form.value)
}

// 某个孩子的"最高得分者"候选：归属班级的主要竞争对手 + 孩子本人
function rivalOptions(childId) {
  const cls = currentClassRec(classes.value, childId)
  const names = []
  if (cls && cls.rivals) {
    try {
      names.push(...JSON.parse(cls.rivals).map((r) => r.name).filter(Boolean))
    } catch {
      names.push(...cls.rivals.split(/[、,，]/).filter((s) => s.trim()))
    }
  }
  const child = children.value.find((c) => c.id === childId)
  if (child?.name && !names.includes(child.name)) names.push(child.name)
  return names
}

async function save() {
  if (!form.value.child_id || !form.value.subject_id) return ElMessage.warning('请选择孩子和学科')
  if (form.value.regular_score == null || !form.value.regular_total) return ElMessage.warning('请填得分和总分')
  saving.value = true
  try {
    if (isCreate.value) {
      // 疑似重复提醒：同单元已录过 / 完全相同的一条
      let dupMsg = ''
      try {
        const { data: existing } = await api.get('/scores', {
          params: { child_id: form.value.child_id, subject_id: form.value.subject_id },
        })
        for (const s of existing) {
          // 单元重叠提醒：新成绩的任一单元在已有成绩中出现过
          if (form.value.unit_ids?.length) {
            const overlap = (s.unit_ids || []).filter((uid) => form.value.unit_ids.includes(uid))
            if (overlap.length) {
              const names = overlap
                .map((uid) => units.value.find((u) => u.id === uid)?.name || `单元${uid}`)
                .join('、')
              dupMsg = `${names} 已有一条成绩：${s.date} ${earnedLabel(s)}`
              break
            }
          }
          const same =
            s.date === form.value.date &&
            s.type === form.value.type &&
            s.regular_score === form.value.regular_score &&
            s.regular_total === form.value.regular_total &&
            (s.bonus_score || 0) === (form.value.bonus_score || 0) &&
            (s.bonus_total || 0) === (form.value.bonus_total || 0)
          if (same) {
            dupMsg = `${s.date} 的「${s.type}」已有一条完全相同的成绩：${earnedLabel(s)}`
            break
          }
        }
      } catch {
        /* 查询失败不阻断录入 */
      }
      if (dupMsg) {
        try {
          await ElMessageBox.confirm(`${dupMsg}。确定还要再录一条吗？`, '疑似重复录入', {
            type: 'warning',
            confirmButtonText: '继续录入',
            cancelButtonText: '取消',
          })
        } catch {
          return
        }
      }
      await api.post('/scores', {
        ...form.value,
        bonus_score: form.value.bonus_score || null,
        bonus_total: form.value.bonus_total || null,
        high_scorer: (form.value.high_scorer_list || []).join('、'),
      })
      ElMessage.success('已保存')
      emit('saved', null, true)
      // 保留孩子/学科/类型，清空分数，方便连续录入
      const keep = {
        child_id: form.value.child_id,
        subject_id: form.value.subject_id,
        type: form.value.type,
        grade: form.value.grade,
        unit_ids: [...(form.value.unit_ids || [])],
        regular_total: form.value.regular_total,
      }
      form.value = { ...emptySingle(), ...keep }
    } else {
      await api.put(`/scores/${form.value.id}`, {
        child_id: form.value.child_id,
        subject_id: form.value.subject_id,
        exam_id: form.value.exam_id,
        unit_ids: form.value.unit_ids,
        date: form.value.date,
        grade: form.value.grade,
        term: form.value.term,
        type: form.value.type,
        regular_score: form.value.regular_score,
        regular_total: form.value.regular_total,
        bonus_score: form.value.bonus_score || null,
        bonus_total: form.value.bonus_total || null,
        // 名次为文字输入框：空串转为 null
        grade_rank: form.value.grade_rank === '' ? null : (form.value.grade_rank ?? null),
        class_rank: form.value.class_rank === '' ? null : (form.value.class_rank ?? null),
        class_size: form.value.class_size,
        tags: form.value.tags || '',
        starred: !!form.value.starred,
        high_score: form.value.high_score ?? null,
        high_scorer: (form.value.high_scorer_list || []).join('、'),
        note: form.value.note || '',
      })
      ElMessage.success('已保存')
      emit('update:modelValue', false)
      emit('saved', null, false)
    }
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.hint {
  color: #909399;
  font-size: 12px;
  line-height: 1.4;
}
:deep(.el-form-item) {
  margin-bottom: 6px;
}
:deep(.el-form-item__label) {
  padding-bottom: 0;
  line-height: 20px;
}
:deep(.el-dialog__body) {
  padding-bottom: 0;
}
:deep(.el-dialog__footer) {
  padding-top: 6px;
}
</style>
