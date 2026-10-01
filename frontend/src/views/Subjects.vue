<template>
  <div>
    <div class="page-head">
      <h3>学科管理</h3>
      <el-button type="primary" @click="openAdd">添加学科</el-button>
    </div>
    <p class="hint">点击学科行进入学科详情，可在详情页按学期管理单元（课程）</p>

    <el-table :data="list" v-loading="loading" @row-click="goDetail" class="clickable">
      <el-table-column label="颜色" width="80">
        <template #default="{ row }">
          <span class="color-dot" :style="{ background: row.color }" />
        </template>
      </el-table-column>
      <el-table-column prop="name" label="学科" min-width="110" sortable />
      <el-table-column prop="version" label="主要版本" min-width="110" sortable>
        <template #default="{ row }">{{ row.version || '—' }}</template>
      </el-table-column>
      <el-table-column prop="child_name" label="归属孩子" min-width="110" sortable>
        <template #default="{ row }">{{ row.child_name || '—' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="210" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" text @click.stop="openEdit(row)">编辑</el-button>
          <el-button size="small" text @click.stop="openCopy(row)">复制</el-button>
          <el-button size="small" type="danger" text @click.stop="del(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 学科表单（添加/编辑共用） -->
    <el-dialog v-model="dialog" :title="form.id ? '编辑学科' : '添加学科'" width="400px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" maxlength="50" />
        </el-form-item>
        <el-form-item label="主要版本">
          <el-input v-model="form.version" maxlength="50" placeholder="如 人教版" />
        </el-form-item>
        <el-form-item label="归属孩子">
          <el-select v-model="form.child_id" filterable clearable placeholder="通用（不归属具体孩子）" style="width: 100%">
            <el-option v-for="c in children" :key="c.id" :value="c.id" :label="c.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="颜色">
          <div class="color-grid">
            <span
              v-for="c in COLOR_CHOICES"
              :key="c"
              class="color-swatch"
              :class="{ active: form.color === c }"
              :style="{ background: c }"
              @click="form.color = c"
            />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 复制学科：改好名称/归属后，连带课程（学期+单元）一并复制 -->
    <el-dialog v-model="copyDialog" title="复制学科" width="400px">
      <el-form :model="copyForm" label-width="90px">
        <el-form-item label="来源">
          <el-input :model-value="copySourceName" disabled />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="copyForm.name" maxlength="50" />
        </el-form-item>
        <el-form-item label="主要版本">
          <el-input v-model="copyForm.version" maxlength="50" placeholder="如 人教版" />
        </el-form-item>
        <el-form-item label="归属孩子">
          <el-select v-model="copyForm.child_id" filterable clearable placeholder="通用（不归属具体孩子）" style="width: 100%">
            <el-option v-for="c in children" :key="c.id" :value="c.id" :label="c.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="颜色">
          <div class="color-grid">
            <span
              v-for="c in COLOR_CHOICES"
              :key="c"
              class="color-swatch"
              :class="{ active: copyForm.color === c }"
              :style="{ background: c }"
              @click="copyForm.color = c"
            />
          </div>
        </el-form-item>
      </el-form>
      <p class="hint">将复制该学科的全部课程（各学期的单元），复制后可再自行调整</p>
      <template #footer>
        <el-button @click="copyDialog = false">取消</el-button>
        <el-button type="primary" :loading="copySaving" @click="saveCopy">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, errMsg, confirmDelete } from '../api'

const router = useRouter()
const list = ref([])
const children = ref([])
const loading = ref(false)
const dialog = ref(false)
const saving = ref(false)
const emptyForm = { name: '', color: '#409EFF', version: '', child_id: null }
const form = ref({ ...emptyForm })

const copyDialog = ref(false)
const copySaving = ref(false)
const copySource = ref(null)
const copyForm = ref({ ...emptyForm })
const copySourceName = computed(() => copySource.value?.name || '')

// 36 种预设颜色：色相每 20° 一档（红→黄→绿→青→蓝→紫→洋红），深浅两档成对，区分度最大
const COLOR_CHOICES = [
  '#f42525', '#f46a25', '#f4af25', '#f4f425', '#aff425', '#6af425',
  '#25f425', '#25f46a', '#25f4af', '#25f4f4', '#25aff4', '#256af4',
  '#2525f4', '#6a25f4', '#af25f4', '#f425f4', '#f425af', '#f4256a',
  '#ad1f1f', '#ad4e1f', '#ad7e1f', '#adad1f', '#7ead1f', '#4ead1f',
  '#1fad1f', '#1fad4e', '#1fad7e', '#1fadad', '#1f7ead', '#1f4ead',
  '#1f1fad', '#4e1fad', '#7e1fad', '#ad1fad', '#ad1f7e', '#ad1f4e',
]

async function load() {
  loading.value = true
  try {
    const [subjects, ch] = await Promise.all([api.get('/subjects'), api.get('/children')])
    list.value = subjects.data
    children.value = ch.data
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    loading.value = false
  }
}

function goDetail(row) {
  router.push(`/subject/${row.id}`)
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

// ---------- 复制学科 ----------
function openCopy(row) {
  copySource.value = row
  copyForm.value = {
    name: row.name,
    color: row.color,
    version: row.version || '',
    child_id: row.child_id ?? null,
  }
  copyDialog.value = true
}

async function saveCopy() {
  if (!copyForm.value.name) return ElMessage.warning('请填学科名称')
  copySaving.value = true
  try {
    await api.post(`/subjects/${copySource.value.id}/copy`, copyForm.value)
    copyDialog.value = false
    ElMessage.success('已复制（含课程单元）')
    load()
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    copySaving.value = false
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
  margin-bottom: 12px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.clickable :deep(tbody tr) {
  cursor: pointer;
}
.color-dot {
  display: inline-block;
  width: 18px;
  height: 18px;
  border-radius: 4px;
}
.color-grid {
  display: grid;
  grid-template-columns: repeat(9, 24px);
  gap: 6px;
}
.color-swatch {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  cursor: pointer;
  border: 2px solid #fff;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.1);
}
.color-swatch.active {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px var(--el-color-primary);
  transform: scale(1.1);
}
</style>
