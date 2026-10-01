<template>
  <div>
    <div class="page-head">
      <h3>班级管理</h3>
      <el-button type="primary" @click="dialog = true">新建班级</el-button>
    </div>
    <p class="hint">
      班级 = 孩子的就读经历：归属、阶段、入学时间等信息在这里录入，孩子管理里的学校/年级/学号等自动按时间推算提取；点击任意一行可查看班级详情
    </p>

    <el-table :data="list" v-loading="loading" @row-click="goDetail" class="clickable">
      <el-table-column prop="child_name" label="归属孩子" width="110" sortable />
      <el-table-column prop="school" label="学校" min-width="140" sortable />
      <el-table-column prop="stage" label="阶段" width="80" sortable />
      <el-table-column prop="grade" label="年级" width="140" sortable>
        <template #default="{ row }">
          <span v-if="row.grade">{{ gradeLabel(row.grade) }}</span>
          <span v-else-if="row.graduated" class="graduated">已毕业（{{ classGraduateYear(row.stage, row.enroll_year) }}级）</span>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="班级" width="100" sortable>
        <template #default="{ row }">{{ row.name || '—' }}</template>
      </el-table-column>
      <el-table-column prop="student_no" label="学号" width="100" sortable>
        <template #default="{ row }">{{ row.student_no || '—' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" text @click.stop="editRow = row; dialog = true">编辑</el-button>
          <el-button size="small" type="danger" text @click.stop="del(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <ClassEditDialog v-model:visible="dialog" :class-row="editRow" @saved="load" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, errMsg } from '../api'
import { classGraduateYear, gradeLabel } from '../utils'
import ClassEditDialog from '../components/ClassEditDialog.vue'

const router = useRouter()
const list = ref([])
const loading = ref(false)
const dialog = ref(false)
const editRow = ref(null) // null = 新建

async function load() {
  loading.value = true
  try {
    list.value = (await api.get('/classes')).data
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    loading.value = false
  }
}

function goDetail(row) {
  router.push(`/class/${row.id}`)
}

async function del(row) {
  try {
    await ElMessageBox.confirm(`确定删除${row.child_name ? `「${row.child_name}」的` : '该'}班级记录？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/classes/${row.id}`)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(errMsg(e))
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
.graduated {
  color: var(--el-text-color-secondary);
}
.clickable :deep(tbody tr) {
  cursor: pointer;
}
</style>
