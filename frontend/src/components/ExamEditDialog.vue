<template>
  <el-dialog :model-value="modelValue" :title="isCreate ? '新建考试场次' : '编辑考试场次'" width="640px" @update:model-value="$emit('update:modelValue', $event)">
    <el-form :model="ef" label-position="top">
      <el-row :gutter="12">
        <el-col :span="8">
          <el-form-item label="孩子" required>
            <el-select v-model="ef.child_id" @change="onChildChange" style="width: 100%">
              <el-option v-for="c in children" :key="c.id" :value="c.id" :label="c.name" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="场次名称" required>
            <el-input v-model="ef.name" placeholder="如：2026-2027第一学期期中考试" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="类型" required>
            <el-select v-model="ef.type" style="width: 100%">
              <el-option v-for="t in examTypes" :key="t" :value="t" :label="t" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="8">
          <el-form-item label="日期" required>
            <el-date-picker v-model="ef.date" type="date" value-format="YYYY-MM-DD" style="width: 100%" @change="onDateChange" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="年级">
            <el-select v-model="ef.grade" style="width: 100%" :disabled="gradeLocked">
              <el-option v-for="g in 9" :key="g" :value="g" :label="gradeLabel(g)" />
            </el-select>
            <div class="hint" v-if="gradeLocked">按入学年份与日期自动推算</div>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="学期">
            <el-input v-model="ef.term" placeholder="按日期自动推断" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="6">
          <el-form-item label="班级排名">
            <el-input v-model="ef.class_rank" placeholder="如 3 或 前5" clearable />
          </el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label="年级排名（学年）">
            <el-input v-model="ef.year_rank" placeholder="如 3 或 前5" clearable />
          </el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label="标签">
            <el-input v-model="ef.tags" placeholder="如：里程碑、薄弱" />
          </el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label="标星">
            <el-switch v-model="ef.starred" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="6">
          <el-form-item label="最高分">
            <el-input-number v-model="ef.high_score" :min="0" :max="2000" controls-position="right" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="最高得分者">
            <el-select v-model="ef.high_scorer_list" multiple filterable clearable placeholder="可多选" style="width: 100%">
              <el-option v-for="n in rivalOptions(ef.child_id)" :key="n" :value="n" :label="n" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="备注">
        <el-input v-model="ef.note" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ isCreate ? '创建' : '保存' }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api'
import { store } from '../store'
import { currentClassRec, examTypes, gradeLabel, inferTerm, pickClassAt } from '../utils'

const props = defineProps({
  modelValue: Boolean,
  exam: { type: Object, default: null }, // null = 新建
})
const emit = defineEmits(['update:modelValue', 'saved'])

const isCreate = computed(() => !props.exam)
const children = ref([])
const classes = ref([])
const saving = ref(false)
const gradeLocked = ref(false)
const ef = ref({})

onMounted(async () => {
  try {
    const [c, cls] = await Promise.all([api.get('/children'), api.get('/classes')])
    children.value = c.data
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

// 每次打开弹窗：编辑用当前场次数据，新建给默认值
watch(
  () => props.modelValue,
  (v) => {
    if (!v) return
    if (props.exam) {
      const e = props.exam
      gradeLocked.value = hasClassRec(e.child_id)
      ef.value = {
        id: e.id,
        child_id: e.child_id,
        name: e.name,
        type: e.type,
        date: e.date,
        grade: e.grade,
        term: e.term,
        grade_rank: e.grade_rank,
        class_rank: e.class_rank ?? null,
        class_size: e.class_size,
        year_rank: e.year_rank ?? null,
        tags: e.tags || '',
        starred: !!e.starred,
        high_score: e.high_score ?? null,
        high_scorer_list: (e.high_scorer || '').split('、').filter(Boolean),
        note: e.note || '',
      }
    } else {
      gradeLocked.value = hasClassRec(store.childId)
      ef.value = {
        child_id: store.childId ?? null,
        name: '',
        type: examTypes[0],
        date: today(),
        grade: gradeFor(store.childId) ?? 1,
        term: inferTerm(today()),
        grade_rank: null,
        class_rank: null,
        class_size: null,
        year_rank: null,
        tags: '',
        starred: false,
        high_score: null,
        high_scorer_list: [],
        note: '',
      }
    }
  },
)

function onChildChange(id) {
  gradeLocked.value = hasClassRec(id)
  const g = gradeFor(id, ef.value.date)
  if (g != null) ef.value.grade = g
}

function onDateChange(d) {
  if (!d) return
  ef.value.term = inferTerm(d)
  const g = gradeFor(ef.value.child_id, d)
  if (g != null) ef.value.grade = g
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
  if (!ef.value.name) return ElMessage.warning('请填写场次名称')
  if (!ef.value.child_id) return ElMessage.warning('请选择孩子')
  saving.value = true
  try {
    const payload = {
      child_id: ef.value.child_id,
      name: ef.value.name,
      type: ef.value.type,
      date: ef.value.date,
      grade: ef.value.grade,
      term: ef.value.term,
      // 名次为文字输入框：空串转为 null
      grade_rank: ef.value.grade_rank === '' ? null : (ef.value.grade_rank ?? null),
      class_rank: ef.value.class_rank === '' ? null : (ef.value.class_rank ?? null),
      class_size: ef.value.class_size,
      year_rank: ef.value.year_rank === '' ? null : (ef.value.year_rank ?? null),
      tags: ef.value.tags || '',
      starred: !!ef.value.starred,
      high_score: ef.value.high_score ?? null,
      high_scorer: (ef.value.high_scorer_list || []).join('、'),
      note: ef.value.note || '',
    }
    if (isCreate.value) {
      const { data } = await api.post('/exams', payload)
      ElMessage.success('场次已创建，去「录一条」录各科成绩后回来拉取')
      emit('update:modelValue', false)
      emit('saved', data, true)
    } else {
      await api.put(`/exams/${ef.value.id}`, payload)
      ElMessage.success('场次已更新')
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
