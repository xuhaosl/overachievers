<template>
  <el-dialog :model-value="visible" :title="classRow ? '编辑班级' : '新建班级'" width="640px" @update:model-value="$emit('update:visible', $event)">
    <el-form :model="form" label-position="top">
      <el-row :gutter="12">
        <el-col :span="8">
          <el-form-item label="归属（孩子）">
            <el-select v-model="form.child_id" clearable filterable style="width: 100%" @change="onChildOrStageChange">
              <el-option v-for="c in children" :key="c.id" :value="c.id" :label="c.name" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="阶段" required>
            <el-select v-model="form.stage" style="width: 100%" @change="onChildOrStageChange">
              <el-option v-for="s in stages" :key="s" :value="s" :label="s" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="入学时间">
            <el-date-picker
              v-model="form.enroll_year"
              type="year"
              placeholder="该阶段入学年份"
              value-format="YYYY"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="14">
          <el-form-item label="学校">
            <el-input v-model="form.school" maxlength="100" />
          </el-form-item>
        </el-col>
        <el-col :span="10">
          <el-form-item label="班级名称">
            <el-input v-model="form.name" placeholder="如：6班" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="8">
          <el-form-item label="班级人数">
            <el-input-number v-model="form.size" :min="0" :max="100" controls-position="right" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="学号">
            <el-input v-model="form.student_no" maxlength="50" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="年级（自动推算）">
            <el-input :model-value="gradePreview" disabled />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="备注">
        <el-input v-model="form.note" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api'
import { classGradeAt, gradeLabel, todayStr } from '../utils'

const props = defineProps({
  visible: Boolean,
  classRow: { type: Object, default: null }, // null = 新建
})
const emit = defineEmits(['update:visible', 'saved'])

const stages = ['小学', '初中', '高中']
const children = ref([])
const saving = ref(false)
const form = ref({})

const emptyForm = { child_id: null, stage: '小学', enroll_year: null, school: '', name: '', size: 45, student_no: '', rivals: '', note: '' }

// 年级预览：按阶段+入学时间推算（同后端规则：8月起算新学年，超出阶段年数即毕业）
const gradePreview = computed(() => {
  if (!form.value.enroll_year) return '填入学时间后自动推算'
  const g = classGradeAt(form.value, todayStr())
  return g != null ? gradeLabel(g) : '已毕业'
})

// 归属/阶段联动入学时间：小学=孩子首次入学时间；初中=+6年；高中=+9年。计算后仍可手动修改
function onChildOrStageChange() {
  const child = children.value.find((c) => c.id === form.value.child_id)
  const base = Number(child?.first_enroll_year)
  if (!base || !form.value.stage) return
  const y = form.value.stage === '初中' ? base + 6 : form.value.stage === '高中' ? base + 9 : base
  form.value.enroll_year = String(y) // 年份选择器 value-format 为 "YYYY"，必须是字符串才能显示
}

async function loadChildren() {
  try {
    children.value = (await api.get('/children')).data
  } catch {
    /* 孩子列表拉取失败不阻塞弹窗 */
  }
}

// 弹窗打开时初始化表单（rivals 原样透传，不在此弹窗中编辑）
watch(
  () => props.visible,
  (v) => {
    if (!v) return
    if (props.classRow) {
      form.value = { ...emptyForm, ...props.classRow, enroll_year: props.classRow.enroll_year ? String(props.classRow.enroll_year) : null }
    } else {
      form.value = { ...emptyForm }
    }
    loadChildren()
  },
  { immediate: true }
)

async function save() {
  saving.value = true
  try {
    const payload = { ...form.value, enroll_year: form.value.enroll_year ? Number(form.value.enroll_year) : null }
    if (form.value.id) await api.put(`/classes/${form.value.id}`, payload)
    else await api.post('/classes', payload)
    ElMessage.success('已保存')
    emit('update:visible', false)
    emit('saved')
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    saving.value = false
  }
}
</script>
