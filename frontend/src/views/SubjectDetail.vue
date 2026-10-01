<template>
  <div v-loading="loading">
    <div class="page-head">
      <el-page-header @back="$router.push('/subjects')">
        <template #content>
          <span class="color-dot" :style="{ background: subject?.color }" />
          <b>{{ subject?.name || '' }}</b>
        </template>
      </el-page-header>
      <el-button type="primary" @click="openEdit">编辑</el-button>
    </div>

    <template v-if="subject">
      <el-card shadow="never">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="学科名称">{{ subject.name }}</el-descriptions-item>
          <el-descriptions-item label="主要版本">{{ subject.version || '—' }}</el-descriptions-item>
          <el-descriptions-item label="归属孩子">{{ subject.child_name || '—' }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 课程：按学期（TAB）管理单元 -->
      <el-card shadow="never" style="margin-top: 16px" class="course-card">
        <template #header><span>课程</span></template>

        <el-empty v-if="!terms.length" description="还没有学期，点右侧「+」添加（如 四上、初一上）" :image-size="80" />
        <el-tabs
          v-else
          v-model="activeTerm"
          addable
          closable
          @tab-add="openTermAdd"
          @tab-remove="removeTerm"
        >
          <el-tab-pane v-for="t in terms" :key="t" :name="t" :label="t">
            <el-table :data="termUnits" size="small">
              <el-table-column label="单元序号" width="120">
                <template #default="{ row }">第{{ row.sort_no }}单元</template>
              </el-table-column>
              <el-table-column label="单元名称">
                <template #default="{ row }">
                  <el-input v-model="row.name" size="small" placeholder="填写单元名称" @change="renameUnit(row)" />
                </template>
              </el-table-column>
              <el-table-column width="90" fixed="right">
                <template #default="{ row }">
                  <el-button size="small" type="danger" text @click="delUnit(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>

            <div class="unit-tools">
              <el-input-number v-model="genCount" :min="1" :max="50" size="small" />
              <el-button type="primary" plain size="small" @click="generate">生成"第1~N单元"</el-button>
              <el-button plain size="small" @click="addUnit">添加一个</el-button>
            </div>
          </el-tab-pane>
        </el-tabs>
      </el-card>

      <!-- 学科编辑弹窗 -->
      <el-dialog v-model="dialog" title="编辑学科" width="400px">
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
          <el-button type="primary" :loading="saving" @click="saveSubject">保存</el-button>
        </template>
      </el-dialog>

      <!-- 添加学期弹窗 -->
      <el-dialog v-model="termDialog" title="添加学期" width="380px">
        <el-form label-width="80px">
          <el-form-item label="学期" required>
            <el-select v-model="termName" filterable allow-create default-first-option
              placeholder="选择或输入，如 四上、初一上" style="width: 100%">
              <el-option v-for="t in termSuggestions" :key="t" :value="t" :label="t" />
            </el-select>
          </el-form-item>
          <p class="hint">建议用"年级＋上/下册"，如 四上、五下、初一上；归属孩子后可从下拉里选</p>
        </el-form>
        <template #footer>
          <el-button @click="termDialog = false">取消</el-button>
          <el-button type="primary" :loading="termSaving" @click="saveTerm">保存</el-button>
        </template>
      </el-dialog>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, errMsg, confirmDelete } from '../api'

const route = useRoute()
const subject = ref(null)
const children = ref([])
const loading = ref(true)
const dialog = ref(false)
const saving = ref(false)
const form = ref({ name: '', color: '#409EFF', version: '', child_id: null })

// ---------- 学期（TAB） ----------
const terms = ref([]) // 短学期名列表，语义排序
const activeTerm = ref('')
const termDialog = ref(false)
const termSaving = ref(false)
const termName = ref('')
const termSuggestions = ref([])

// ---------- 单元 ----------
const units = ref([]) // 该学科全部单元
const genCount = ref(8)

const termUnits = computed(() =>
  units.value.filter((u) => u.term === activeTerm.value).sort((a, b) => a.sort_no - b.sort_no)
)

async function loadAll() {
  loading.value = true
  try {
    const [sub, t, u, ch] = await Promise.all([
      api.get(`/subjects/${route.params.id}`),
      api.get(`/subjects/${route.params.id}/terms`),
      api.get(`/subjects/${route.params.id}/units`),
      api.get('/children'),
    ])
    subject.value = sub.data
    terms.value = t.data
    units.value = u.data
    children.value = ch.data
    // 支持从成绩列表/详情跳转过来时定位学期TAB（?term=五上）
    if (route.query.term && terms.value.includes(route.query.term)) {
      activeTerm.value = route.query.term
    } else if (!terms.value.includes(activeTerm.value)) {
      activeTerm.value = terms.value[terms.value.length - 1] || ''
    }
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    loading.value = false
  }
}

// ---------- 学科编辑 ----------
function openEdit() {
  form.value = {
    name: subject.value.name,
    color: subject.value.color,
    version: subject.value.version || '',
    child_id: subject.value.child_id ?? null,
  }
  dialog.value = true
}

async function saveSubject() {
  if (!form.value.name) return ElMessage.warning('请填学科名称')
  saving.value = true
  try {
    await api.put(`/subjects/${subject.value.id}`, form.value)
    dialog.value = false
    ElMessage.success('已保存')
    loadAll()
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    saving.value = false
  }
}

// ---------- 学期 ----------
async function openTermAdd() {
  termName.value = ''
  termSuggestions.value = []
  termDialog.value = true
  try {
    const { data } = await api.get(`/subjects/${route.params.id}/term-suggestions`)
    termSuggestions.value = data
  } catch {
    /* 忽略，可手输 */
  }
}

async function saveTerm() {
  const name = (termName.value || '').trim()
  if (!name) return ElMessage.warning('请填学期名称')
  termSaving.value = true
  try {
    await api.post(`/subjects/${route.params.id}/terms`, { term: name })
    termDialog.value = false
    ElMessage.success('学期已添加')
    activeTerm.value = name
    loadAll()
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    termSaving.value = false
  }
}

async function removeTerm(name) {
  try {
    await ElMessageBox.confirm(
      `确定删除学期「${name}」？该学期下的单元会一并删除（关联成绩保留，仅不再标注单元）。`,
      '删除学期',
      { type: 'warning', confirmButtonText: '删除' }
    )
  } catch {
    return
  }
  try {
    await api.delete(`/subjects/${route.params.id}/terms`, { params: { term: name } })
    ElMessage.success('已删除')
    loadAll()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

// ---------- 单元管理 ----------
async function generate() {
  const subjectId = route.params.id
  const doGen = (confirm = false) =>
    api.post(`/subjects/${subjectId}/units/generate`, {
      count: genCount.value,
      term: activeTerm.value,
      confirm,
    })
  try {
    await doGen()
    ElMessage.success('已生成')
  } catch (e) {
    if (e?.response?.status === 409) {
      try {
        await ElMessageBox.confirm(errMsg(e), '调整单元', { type: 'warning', confirmButtonText: '确定' })
      } catch {
        return
      }
      try {
        await doGen(true)
        ElMessage.success('已生成')
      } catch (err) {
        ElMessage.error(errMsg(err))
        return
      }
    } else {
      ElMessage.error(errMsg(e))
      return
    }
  }
  loadAll()
}

async function renameUnit(row) {
  try {
    await api.put(`/subjects/units/${row.id}`, { name: row.name, sort_no: row.sort_no })
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

// 添加一个单元：序号接着当前学期最大序号往后排
async function addUnit() {
  const next = (termUnits.value.length ? Math.max(...termUnits.value.map((u) => u.sort_no)) : 0) + 1
  try {
    await api.post(`/subjects/${route.params.id}/units`, {
      name: '',
      sort_no: next,
      term: activeTerm.value,
    })
    ElMessage.success(`已添加"第${next}单元"`)
    loadAll()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function delUnit(row) {
  try {
    await confirmDelete(`/subjects/units/${row.id}`)
    loadAll()
  } catch {
    /* 取消 */
  }
}

watch(() => route.params.id, loadAll)
onMounted(loadAll)
</script>

<style scoped>
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.course-card :deep(.el-card__header) {
  padding: 8px 20px;
}
.course-card :deep(.el-card__body) {
  padding-top: 4px;
}
.course-card :deep(.el-tabs__header) {
  margin: 0 0 10px;
}
.color-dot {
  display: inline-block;
  width: 14px;
  height: 14px;
  border-radius: 4px;
  margin-right: 8px;
}
.unit-tools {
  display: flex;
  gap: 10px;
  margin-top: 12px;
  align-items: center;
}
.hint {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
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
  border: 2px #fff solid;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.1);
}
.color-swatch.active {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px var(--el-color-primary);
  transform: scale(1.1);
}
</style>
