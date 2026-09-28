<template>
  <div>
    <div class="toolbar">
      <el-button type="primary" :icon="Plus" @click="openAdd">添加孩子</el-button>
    </div>

    <el-table :data="list" v-loading="loading">
      <el-table-column prop="name" label="姓名" width="120" />
      <el-table-column prop="gender" label="性别" width="80" />
      <el-table-column label="年级" width="100">
        <template #default="{ row }">{{ gradeLabel(row.grade) }}</template>
      </el-table-column>
      <el-table-column prop="birth_date" label="出生日期" width="130" />
      <el-table-column prop="school" label="学校" />
      <el-table-column prop="note" label="备注" />
      <el-table-column label="成绩数" width="90">
        <template #default="{ row }">{{ row.score_count }}</template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-popconfirm
            :title="`确认把 ${row.name} 升到 ${gradeLabel(Math.min(row.grade + 1, 9))}？新成绩将自动记录新年级`"
            @confirm="advance(row)"
          >
            <template #reference>
              <el-button size="small" type="success" :disabled="row.grade >= 9">升年级</el-button>
            </template>
          </el-popconfirm>
          <el-button size="small" type="danger" @click="del(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" :title="form.id ? '编辑孩子' : '添加孩子'" width="420px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="姓名" required>
          <el-input v-model="form.name" maxlength="50" />
        </el-form-item>
        <el-form-item label="性别">
          <el-radio-group v-model="form.gender">
            <el-radio value="男">男</el-radio>
            <el-radio value="女">女</el-radio>
            <el-radio value="">不填</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="出生日期">
          <el-date-picker v-model="form.birth_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="年级" required>
          <el-select v-model="form.grade" style="width: 100%">
            <el-option v-for="g in 9" :key="g" :value="g" :label="gradeLabel(g)" />
          </el-select>
        </el-form-item>
        <el-form-item label="学校">
          <el-input v-model="form.school" maxlength="100" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.note" type="textarea" :rows="2" />
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
import { onMounted, ref } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api, errMsg, confirmDelete } from '../api'
import { gradeLabel } from '../utils'
import { store } from '../store'

const list = ref([])
const loading = ref(false)
const dialog = ref(false)
const saving = ref(false)
const emptyForm = { name: '', gender: '', birth_date: null, grade: 1, school: '', note: '' }
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
function openEdit(row) {
  form.value = { ...row }
  dialog.value = true
}

async function save() {
  if (!form.value.name) return ElMessage.warning('请填姓名')
  saving.value = true
  try {
    if (form.value.id) await api.put(`/children/${form.value.id}`, form.value)
    else await api.post('/children', form.value)
    dialog.value = false
    ElMessage.success('已保存')
    load()
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    saving.value = false
  }
}

async function advance(row) {
  try {
    await api.post(`/children/${row.id}/advance-grade`)
    ElMessage.success(`${row.name} 已升级`)
    load()
  } catch (e) {
    ElMessage.error(errMsg(e))
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
.toolbar {
  margin-bottom: 12px;
}
</style>
