<template>
  <div>
    <div class="toolbar">
      <el-button type="primary" :icon="Plus" @click="openAdd">添加学科</el-button>
    </div>

    <el-table :data="list" v-loading="loading">
      <el-table-column label="颜色" width="70">
        <template #default="{ row }">
          <span class="color-dot" :style="{ background: row.color }" />
        </template>
      </el-table-column>
      <el-table-column prop="name" label="学科" width="140" />
      <el-table-column prop="sort" label="排序" width="80" />
      <el-table-column label="默认总分" width="100">
        <template #default="{ row }">{{ row.default_total ?? '-' }}</template>
      </el-table-column>
      <el-table-column prop="unit_count" label="单元数" width="90" />
      <el-table-column prop="score_count" label="成绩数" width="90" />
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openUnits(row)">单元({{ row.unit_count }})</el-button>
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="del(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 学科表单 -->
    <el-dialog v-model="dialog" :title="form.id ? '编辑学科' : '添加学科'" width="400px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" maxlength="50" />
        </el-form-item>
        <el-form-item label="颜色">
          <el-color-picker v-model="form.color" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort" :min="0" />
        </el-form-item>
        <el-form-item label="默认总分">
          <el-input-number v-model="form.default_total" :min="1" :max="1000" />
          <span class="hint">录成绩时自动带出，可改</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 单元管理 -->
    <el-dialog v-model="unitDialog" :title="`单元管理 - ${current?.name}`" width="420px">
      <div class="unit-gen">
        <el-input-number v-model="genCount" :min="1" :max="50" />
        <el-button type="primary" plain @click="generate">一键生成"第1~N单元"</el-button>
      </div>
      <el-table :data="units" size="small" max-height="360">
        <el-table-column label="单元名称">
          <template #default="{ row }">
            <el-input v-model="row.name" size="small" @change="renameUnit(row)" />
          </template>
        </el-table-column>
        <el-table-column width="80">
          <template #default="{ row }">
            <el-button size="small" type="danger" text @click="delUnit(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api, errMsg, confirmDelete } from '../api'

const list = ref([])
const loading = ref(false)
const dialog = ref(false)
const saving = ref(false)
const emptyForm = { name: '', color: '#409EFF', sort: 0, default_total: 100 }
const form = ref({ ...emptyForm })

const unitDialog = ref(false)
const current = ref(null)
const units = ref([])
const genCount = ref(8)

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/subjects')
    list.value = data
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    loading.value = false
  }
}

function openAdd() {
  form.value = { ...emptyForm, sort: list.value.length }
  dialog.value = true
}
function openEdit(row) {
  form.value = { ...row }
  dialog.value = true
}

async function save() {
  if (!form.value.name) return ElMessage.warning('请填学科名称')
  saving.value = true
  try {
    if (form.value.id) await api.put(`/subjects/${form.value.id}`, form.value)
    else await api.post('/subjects', form.value)
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
    await confirmDelete(`/subjects/${row.id}`)
    ElMessage.success('已删除')
    load()
  } catch {
    /* 取消 */
  }
}

// ---------- 单元 ----------
async function openUnits(row) {
  current.value = row
  unitDialog.value = true
  await loadUnits()
}
async function loadUnits() {
  const { data } = await api.get(`/subjects/${current.value.id}/units`)
  units.value = data
}
async function generate() {
  try {
    await api.post(`/subjects/${current.value.id}/units/generate`, { count: genCount.value })
    ElMessage.success('已生成')
    loadUnits()
    load()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}
async function renameUnit(row) {
  try {
    await api.put(`/subjects/units/${row.id}`, { name: row.name, sort: row.sort })
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}
async function delUnit(row) {
  try {
    await api.delete(`/subjects/units/${row.id}`)
    loadUnits()
    load()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  margin-bottom: 12px;
}
.color-dot {
  display: inline-block;
  width: 18px;
  height: 18px;
  border-radius: 4px;
}
.hint {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.unit-gen {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}
</style>
