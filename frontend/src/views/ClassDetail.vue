<template>
  <div v-loading="loading">
    <template v-if="rec">
      <div class="page-head">
        <el-page-header @back="$router.push('/classes')">
          <template #content>
            <b>{{ headTitle }}</b>
          </template>
        </el-page-header>
        <el-button type="primary" @click="dialog = true">编辑</el-button>
      </div>

      <el-card shadow="never">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="归属孩子">{{ rec.child_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="学校">{{ rec.school || '—' }}</el-descriptions-item>
          <el-descriptions-item label="阶段">{{ rec.stage || '—' }}</el-descriptions-item>
          <el-descriptions-item label="年级">
            <span v-if="rec.grade">{{ gradeLabel(rec.grade) }}（自动推算）</span>
            <span v-else-if="rec.graduated" class="graduated">已毕业（{{ classGraduateYear(rec.stage, rec.enroll_year) }}级）</span>
            <span v-else>—</span>
          </el-descriptions-item>
          <el-descriptions-item label="班级名称">{{ rec.name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="班级人数">{{ rec.size || '—' }}</el-descriptions-item>
          <el-descriptions-item label="学号">{{ rec.student_no || '—' }}</el-descriptions-item>
          <el-descriptions-item label="入学时间">{{ rec.enroll_year || '—' }}</el-descriptions-item>
          <el-descriptions-item label="备注" :span="2">{{ rec.note || '—' }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 主要竞争对手：单独管理 -->
      <el-card shadow="never" style="margin-top: 16px">
        <template #header><span>主要竞争对手</span></template>
        <el-table :data="rivalRows" size="small" empty-text="还没有添加竞争对手">
          <el-table-column label="学号" width="120">
            <template #default="{ row }">{{ row.no || '—' }}</template>
          </el-table-column>
          <el-table-column label="姓名" min-width="160">
            <template #default="{ row }">{{ row.name || '—' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="80">
            <template #default="{ $index }">
              <el-button size="small" type="danger" text @click="removeRival($index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="rival-add">
          <el-input v-model="newRival.no" placeholder="学号" style="width: 120px" />
          <el-input v-model="newRival.name" placeholder="姓名" style="width: 160px" @keyup.enter="addRival" />
          <el-button type="primary" :loading="saving" @click="addRival">添加</el-button>
        </div>
      </el-card>

      <ClassEditDialog v-model:visible="dialog" :class-row="rec" @saved="load" />
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api'
import { classGraduateYear, gradeLabel } from '../utils'
import ClassEditDialog from '../components/ClassEditDialog.vue'

const route = useRoute()
const rec = ref(null)
const loading = ref(true)
const dialog = ref(false)
const saving = ref(false)
const newRival = ref({ no: '', name: '' })

// 标题：学校+年级+班级（归属孩子），如「德培小学5年级6班（朵朵）」
const headTitle = computed(() => {
  const r = rec.value
  if (!r) return ''
  const school = r.school || ''
  const grade = r.grade ? gradeLabel(r.grade) : r.graduated ? '已毕业' : ''
  const cls = r.name || ''
  const child = r.child_name ? `（${r.child_name}）` : ''
  return `${school}${grade}${cls}${child}`.trim() || '班级详情'
})

// 竞争对手结构化数组 [{no, name}]；兼容旧格式（顿号分隔纯姓名）
const rivalRows = computed(() => {
  const str = rec.value?.rivals
  if (!str) return []
  try {
    const arr = JSON.parse(str)
    if (Array.isArray(arr)) return arr.map((r) => ({ no: r.no || '', name: r.name || '' }))
  } catch {
    /* 旧格式 */
  }
  return str
    .split(/[、,，]/)
    .filter((s) => s.trim())
    .map((n) => ({ no: '', name: n.trim() }))
})

// 持久化竞争对手列表（PUT 全字段防清空）
async function persistRivals(rows) {
  saving.value = true
  try {
    await api.put(`/classes/${rec.value.id}`, { ...rec.value, rivals: JSON.stringify(rows) })
    await load()
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    saving.value = false
  }
}

async function addRival() {
  if (!newRival.value.name.trim()) return ElMessage.warning('请填姓名')
  const rows = [...rivalRows.value, { no: newRival.value.no.trim(), name: newRival.value.name.trim() }]
  newRival.value = { no: '', name: '' }
  await persistRivals(rows)
}

async function removeRival(i) {
  const rows = rivalRows.value.filter((_, idx) => idx !== i)
  await persistRivals(rows)
}

async function load() {
  loading.value = true
  try {
    rec.value = (await api.get(`/classes/${route.params.id}`)).data
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.graduated {
  color: var(--el-text-color-secondary);
}
.rival-add {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 12px;
}
</style>
