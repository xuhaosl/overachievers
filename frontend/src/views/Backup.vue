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

    <el-card shadow="never" class="card">
      <template #header><span>版本与升级</span></template>
      <p class="tip">检查 GitHub 仓库是否发布了新版本。升级时自动拉取新镜像并重建服务，成绩数据保存在数据目录中不受影响。</p>
      <div class="ver-row">
        <span>当前版本：<code>{{ version }}</code></span>
        <span v-if="latest">仓库最新：<code>{{ latest }}</code></span>
      </div>
      <el-button :loading="checking" @click="doCheck">检查更新</el-button>
      <el-button v-if="available" type="primary" :loading="upgrading" @click="doUpgrade">一键升级</el-button>
      <p v-if="msg" class="result" :class="{ err: isErr }">{{ msg }}</p>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, errMsg } from '../api'

const exporting = ref(false)

const version = ref('…')
const latest = ref('')
const available = ref(false)
const checking = ref(false)
const upgrading = ref(false)
const msg = ref('')
const isErr = ref(false)

// 启动只取本机版本号（不访问 GitHub），检查更新由用户手动点
api.get('/update/version').then(({ data }) => {
  version.value = data.version
})

async function doCheck() {
  checking.value = true
  msg.value = ''
  isErr.value = false
  try {
    const { data } = await api.get('/update/check')
    version.value = data.current
    latest.value = data.latest
    available.value = data.update_available
    if (data.error) {
      isErr.value = true
      msg.value = data.error
    } else if (data.current === 'dev') {
      msg.value = '当前为本地开发模式，不支持在线升级'
      isErr.value = true
    } else {
      msg.value = data.update_available
        ? `发现新版本 ${data.latest}，可一键升级`
        : '已是最新版本'
    }
  } catch (e) {
    isErr.value = true
    msg.value = errMsg(e)
  } finally {
    checking.value = false
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function doUpgrade() {
  try {
    await ElMessageBox.confirm(
      '升级将自动拉取新版本镜像并重启服务，约 1 分钟，期间页面会短暂无法访问。确定升级吗？',
      '一键升级',
      { type: 'warning', confirmButtonText: '升级', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  upgrading.value = true
  msg.value = '升级指令已发出，等待新版本上线…'
  isErr.value = false
  try {
    await api.post('/update')
  } catch (e) {
    if (e.response) {
      // 服务端明确报错（如未配置升级通道），不进入轮询
      isErr.value = true
      msg.value = errMsg(e)
      upgrading.value = false
      return
    }
    // 网络错误：多半是容器正在重建，属正常现象，继续轮询
  }
  // 轮询等待新容器就绪：只查本机版本号（不访问 GitHub，不受限流影响）
  const oldVersion = version.value
  for (let i = 0; i < 120; i++) {
    await sleep(5000)
    try {
      const { data } = await api.get('/update/version')
      if (data.version && data.version !== oldVersion) {
        version.value = data.version
        ElMessage.success('升级完成')
        setTimeout(() => location.reload(), 800)
        return
      }
    } catch {
      /* 容器重建期间无法访问，继续等 */
    }
  }
  isErr.value = true
  msg.value = '等待升级超时，请稍后刷新页面查看版本'
  upgrading.value = false
}

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
.ver-row {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
  font-size: 13px;
  color: #606266;
}
.ver-row code {
  color: #303133;
  background: #f5f7fa;
  padding: 1px 6px;
  border-radius: 4px;
}
.result {
  margin: 12px 0 0;
  font-size: 13px;
  color: #67c23a;
}
.result.err {
  color: #f56c6c;
}
</style>
