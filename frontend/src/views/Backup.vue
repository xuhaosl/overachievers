<template>
  <div>
    <div class="page-head">
      <h3>数据备份</h3>
    </div>

    <el-card shadow="never" class="card">
      <template #header><span>数据导出</span></template>
      <p class="tip">
        把系统里的全部数据（孩子、班级、学科、课程单元、考试场次、单科成绩、成绩图片及相互关联）导出为一个 JSON 备份文件。
      </p>
      <el-button type="primary" :loading="exporting" @click="doExport">导出数据</el-button>
    </el-card>

    <el-card shadow="never" class="card">
      <template #header><span>数据导入</span></template>
      <p class="tip">选择之前导出的备份文件，导入后系统将整体恢复为备份时的数据（覆盖现有全部数据），请谨慎操作。</p>
      <el-upload :show-file-list="false" accept=".json,application/json" :auto-upload="false" :on-change="onPick">
        <el-button type="danger">选择备份文件并导入</el-button>
      </el-upload>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, errMsg } from '../api'

const exporting = ref(false)

async function doExport() {
  exporting.value = true
  try {
    const res = await api.get('/backup/export', { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `backup_${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    exporting.value = false
  }
}

async function onPick(file) {
  const raw = file.raw
  if (!raw) return
  try {
    await ElMessageBox.confirm(
      '导入将覆盖系统里现有的全部数据（孩子、班级、学科、成绩等都会变成备份文件里的内容），确定继续吗？',
      '数据导入',
      { type: 'warning', confirmButtonText: '导入', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  const fd = new FormData()
  fd.append('file', raw)
  try {
    const { data } = await api.post('/backup/import', fd)
    const c = data.counts || {}
    ElMessage.success(
      `导入完成：孩子 ${c.children ?? 0}、班级 ${c.classes ?? 0}、学科 ${c.subjects ?? 0}、单元 ${c.units ?? 0}、场次 ${c.exams ?? 0}、成绩 ${c.scores ?? 0}`,
    )
    setTimeout(() => location.reload(), 1200)
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}
</script>

<style scoped>
.card {
  margin-bottom: 12px;
  max-width: 640px;
}
.tip {
  margin: 0 0 12px;
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
}
</style>
