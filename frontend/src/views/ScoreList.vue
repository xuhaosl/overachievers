<template>
  <div>
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
      </el-form-item>
    </el-form>

    <el-table :data="list" v-loading="loading" size="small">
      <el-table-column prop="date" label="日期" width="110" sortable />
      <el-table-column prop="child_name" label="孩子" width="90" />
      <el-table-column label="学科" width="100">
        <template #default="{ row }">
          <span class="color-dot" :style="{ background: row.subject_color }" />{{ row.subject_name }}
        </template>
      </el-table-column>
      <el-table-column prop="type" label="类型" width="100" />
      <el-table-column label="单元 / 场次" min-width="150">
        <template #default="{ row }">{{ row.exam_name || row.unit_name || '-' }}</template>
      </el-table-column>
      <el-table-column label="得分" width="100">
        <template #default="{ row }">{{ earnedLabel(row) }}</template>
      </el-table-column>
      <el-table-column label="总分" width="80">
        <template #default="{ row }">{{ row.total }}</template>
      </el-table-column>
      <el-table-column label="得分率" width="90" sortable :sort-method="(a, b) => a.rate - b.rate">
        <template #default="{ row }">{{ ratePercent(row.rate) }}</template>
      </el-table-column>
      <el-table-column label="年级名次" width="90">
        <template #default="{ row }">{{ row.grade_rank ?? '-' }}</template>
      </el-table-column>
      <el-table-column label="班级名次" width="100">
        <template #default="{ row }">{{ row.class_rank != null ? `${row.class_rank}/${row.class_size ?? '?'}` : '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" text @click="del(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 编辑 -->
    <el-dialog v-model="dialog" title="编辑成绩" width="480px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="日期">
          <el-date-picker v-model="form.date" type="date" value-format="YYYY-MM-DD" style="width: 100%" :disabled="!!form.exam_id" />
        </el-form-item>
        <el-form-item label="学期">
          <el-input v-model="form.term" :disabled="!!form.exam_id" />
        </el-form-item>
        <el-form-item label="常规得分" required>
          <el-input-number v-model="form.regular_score" :min="0" :max="1000" controls-position="right" style="width: 100%" />
        </el-form-item>
        <el-form-item label="常规总分" required>
          <el-input-number v-model="form.regular_total" :min="1" :max="1000" controls-position="right" style="width: 100%" />
        </el-form-item>
        <el-form-item label="有附加分">
          <el-switch v-model="hasBonus" />
        </el-form-item>
        <template v-if="hasBonus">
          <el-form-item label="附加得分">
            <el-input-number v-model="form.bonus_score" :min="0" :max="200" controls-position="right" style="width: 100%" />
          </el-form-item>
          <el-form-item label="附加总分">
            <el-input-number v-model="form.bonus_total" :min="1" :max="200" controls-position="right" style="width: 100%" />
          </el-form-item>
        </template>
        <el-form-item label="年级名次">
          <el-input-number v-model="form.grade_rank" :min="1" controls-position="right" style="width: 100%" />
        </el-form-item>
        <el-form-item label="班级名次">
          <el-input-number v-model="form.class_rank" :min="1" controls-position="right" style="width: 100%" />
        </el-form-item>
        <el-form-item label="班级人数">
          <el-input-number v-model="form.class_size" :min="1" controls-position="right" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api'
import { store } from '../store'
import { examTypes, gradeLabel, earnedLabel, ratePercent } from '../utils'

const q = ref({ child_id: null, subject_id: null, type: null, grade: null, term: null })
const range = ref(null)
const list = ref([])
const subjects = ref([])
const loading = ref(false)
const dialog = ref(false)
const saving = ref(false)
const hasBonus = ref(false)
const form = ref({})

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

function openEdit(row) {
  form.value = { ...row }
  hasBonus.value = row.bonus_score != null
  dialog.value = true
}

async function save() {
  saving.value = true
  try {
    await api.put(`/scores/${form.value.id}`, {
      child_id: form.value.child_id,
      subject_id: form.value.subject_id,
      exam_id: form.value.exam_id,
      unit_id: form.value.unit_id,
      date: form.value.date,
      grade: form.value.grade,
      term: form.value.term,
      type: form.value.type,
      regular_score: form.value.regular_score,
      regular_total: form.value.regular_total,
      bonus_score: hasBonus.value ? form.value.bonus_score : null,
      bonus_total: hasBonus.value ? form.value.bonus_total : null,
      grade_rank: form.value.grade_rank,
      class_rank: form.value.class_rank,
      class_size: form.value.class_size,
    })
    dialog.value = false
    ElMessage.success('已保存')
    load()
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    saving.value = false
  }
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
    const { data } = await api.get('/subjects')
    subjects.value = data
  } finally {
    load()
  }
})
</script>

<style scoped>
.filter :deep(.el-form-item) {
  margin-bottom: 8px;
}
.color-dot {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 3px;
  margin-right: 6px;
}
</style>
