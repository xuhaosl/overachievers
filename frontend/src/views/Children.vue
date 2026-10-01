<template>
  <div>
    <div class="page-head">
      <h3>孩子管理</h3>
      <el-button type="primary" @click="openAdd">添加孩子</el-button>
    </div>
    <p class="hint">孩子的学校/年级/班级/学号等信息从「班级管理」里归属的班级自动提取（按时间推算），此处只维护姓名、首次入学时间、备注</p>

    <el-table :data="list" v-loading="loading" @row-click="goDetail" class="clickable">
      <el-table-column prop="name" label="姓名" width="110" sortable />
      <el-table-column prop="school" label="学校" min-width="140" sortable>
        <template #default="{ row }">{{ row.school || '-' }}</template>
      </el-table-column>
      <el-table-column prop="stage" label="阶段" width="80" sortable>
        <template #default="{ row }">{{ row.stage || '-' }}</template>
      </el-table-column>
      <el-table-column prop="grade" label="年级" width="90" sortable>
        <template #default="{ row }">{{ gradeLabel(row.grade) || '-' }}</template>
      </el-table-column>
      <el-table-column prop="class_name" label="班级" width="90" sortable>
        <template #default="{ row }">{{ row.class_name || '-' }}</template>
      </el-table-column>
      <el-table-column prop="student_no" label="学号" width="90" sortable>
        <template #default="{ row }">{{ row.student_no || '-' }}</template>
      </el-table-column>
      <el-table-column prop="score_count" label="成绩数" width="90" sortable>
        <template #default="{ row }">
          <el-link type="primary" :underline="false" @click.stop="$router.push({ path: '/list', query: { tab: 'single', child_id: row.id } })">
            {{ row.score_count }}
          </el-link>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" text @click.stop="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" text @click.stop="del(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" :title="form.id ? '编辑孩子' : '添加孩子'" width="640px">
      <el-form :model="form" label-position="top">
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="姓名" required>
              <el-input v-model="form.name" maxlength="50" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="首次入学时间">
              <el-date-picker
                v-model="form.first_enroll_year"
                type="year"
                placeholder="小学入学年份"
                value-format="YYYY"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="备注">
              <el-input v-model="form.note" maxlength="200" />
            </el-form-item>
          </el-col>
        </el-row>
        <p class="tip">学校、阶段、年级、班级、学号：请在「设置 → 班级管理」中编辑归属与入学时间，系统自动提取</p>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, errMsg, confirmDelete } from '../api'
import { gradeLabel } from '../utils'
import { store } from '../store'

const router = useRouter()
const list = ref([])
const loading = ref(false)
const dialog = ref(false)
const saving = ref(false)
const emptyForm = { name: '', first_enroll_year: null, note: '' }
const form = ref({ ...emptyForm })

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/children')
    list.value = data
    store.children = data
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    loading.value = false
  }
}

function openAdd() {
  form.value = { ...emptyForm }
  dialog.value = true
}

function goDetail(row) {
  router.push(`/child/${row.id}`)
}

function openEdit(row) {
  form.value = {
    id: row.id,
    name: row.name,
    first_enroll_year: row.first_enroll_year ? String(row.first_enroll_year) : null, // 年份选择器需要字符串
    note: row.note || '',
  }
  dialog.value = true
}

async function save() {
  if (!form.value.name) return ElMessage.warning('请填姓名')
  const payload = { ...form.value, first_enroll_year: form.value.first_enroll_year ? Number(form.value.first_enroll_year) : null }
  saving.value = true
  try {
    if (form.value.id) await api.put(`/children/${form.value.id}`, payload)
    else await api.post('/children', payload)
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
    await confirmDelete(`/children/${row.id}`)
    ElMessage.success('已删除')
    if (store.childId === row.id) store.childId = null
    load()
  } catch {
    /* 用户取消 */
  }
}

onMounted(load)
</script>

<style scoped>
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.page-head h3 {
  margin: 0;
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 0 0 12px;
}
.tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}
.clickable :deep(tbody tr) {
  cursor: pointer;
}
</style>
