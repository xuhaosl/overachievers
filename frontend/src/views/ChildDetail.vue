<template>
  <div v-loading="loading">
    <template v-if="child">
      <div class="page-head">
        <el-page-header @back="$router.push('/children')">
          <template #content>
            <b>{{ headTitle }}</b>
          </template>
        </el-page-header>
        <el-button type="primary" @click="openEdit">编辑</el-button>
      </div>

      <el-card shadow="never">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="姓名">{{ child.name }}</el-descriptions-item>
          <el-descriptions-item label="首次入学时间">{{ child.first_enroll_year || '—' }}</el-descriptions-item>
          <el-descriptions-item label="备注">{{ child.note || '—' }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 绑定的班级（就读经历） -->
      <el-card shadow="never" style="margin-top: 16px">
        <template #header><span>绑定的班级</span></template>
        <el-empty v-if="!classRows.length" description="还没有绑定班级，去「设置 → 班级管理」新建并归属到该孩子" :image-size="70" />
        <el-table v-else :data="classRows" size="small">
          <el-table-column label="学校" min-width="140">
            <template #default="{ row }">{{ row.school || '—' }}</template>
          </el-table-column>
          <el-table-column label="阶段" width="80">
            <template #default="{ row }">{{ row.stage }}</template>
          </el-table-column>
          <el-table-column label="年级" width="130">
            <template #default="{ row }">
              <span v-if="row.grade">{{ gradeLabel(row.grade) }}</span>
              <span v-else-if="row.graduated" class="graduated">已毕业（{{ classGraduateYear(row.stage, row.enroll_year) }}级）</span>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="班级" width="90">
            <template #default="{ row }">{{ row.name || '—' }}</template>
          </el-table-column>
          <el-table-column label="学号" width="90">
            <template #default="{ row }">{{ row.student_no || '—' }}</template>
          </el-table-column>
          <el-table-column label="入学时间" width="90">
            <template #default="{ row }">{{ row.enroll_year || '—' }}</template>
          </el-table-column>
          <el-table-column width="110" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" text @click="$router.push(`/class/${row.id}`)">班级详情</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 编辑孩子 -->
      <el-dialog v-model="dialog" title="编辑孩子" width="640px">
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
        </el-form>
        <template #footer>
          <el-button @click="dialog = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="save">保存</el-button>
        </template>
      </el-dialog>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api'
import { classGraduateYear, gradeLabel } from '../utils'

const route = useRoute()
const child = ref(null)
const classes = ref([])
const loading = ref(true)
const dialog = ref(false)
const saving = ref(false)
const form = ref({})

// 标题：孩子名字（当前阶段年级），如「某某（初中2年级）」；全部毕业则显示（小学已毕业）
const headTitle = computed(() => {
  const c = child.value
  if (!c) return ''
  if (c.grade) return `${c.name}（${c.stage}${gradeLabel(c.grade)}）`
  if (c.stage) return `${c.name}（${c.stage}已毕业）`
  return c.name
})

function openEdit() {
  form.value = {
    id: child.value.id,
    name: child.value.name,
    first_enroll_year: child.value.first_enroll_year ? String(child.value.first_enroll_year) : null, // 年份选择器需要字符串
    note: child.value.note || '',
  }
  dialog.value = true
}

async function save() {
  if (!form.value.name) return ElMessage.warning('请填姓名')
  const payload = { ...form.value, first_enroll_year: form.value.first_enroll_year ? Number(form.value.first_enroll_year) : null }
  saving.value = true
  try {
    await api.put(`/children/${form.value.id}`, payload)
    dialog.value = false
    ElMessage.success('已保存')
    load()
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    saving.value = false
  }
}

const classRows = computed(() => classes.value.filter((c) => c.child_id === Number(route.params.id)))

async function load() {
  loading.value = true
  try {
    const [childRes, classRes] = await Promise.all([api.get(`/children/${route.params.id}`), api.get('/classes')])
    child.value = childRes.data
    classes.value = classRes.data
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
</style>
