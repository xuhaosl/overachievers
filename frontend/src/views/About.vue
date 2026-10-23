<template>
  <div>
    <div class="page-head">
      <h3>关于软件</h3>
    </div>

    <el-card shadow="never" class="card">
      <template #header><span>软件介绍</span></template>
      <p class="intro">
        <strong>Overachievers</strong> 是一款面向家庭的孩子成绩记录与分析系统，本地部署、数据完全自主掌控。
      </p>
      <ul class="feature-list">
        <li><strong>成绩管理</strong>：录入单科成绩（含单元测验）与考试场次，支持成绩图片留档、加星收藏、备注与 AI 评语</li>
        <li><strong>成长曲线</strong>：得分曲线、班级/年级排名曲线，直观看到每个孩子的成长轨迹</li>
        <li><strong>学期排名</strong>：统计孩子与竞争对手的最高得分次数，按学科对比</li>
        <li><strong>智能助手</strong>：接入大模型，随时分析成绩、诊断薄弱点、给出学习建议，并为成绩自动生成评语</li>
        <li><strong>数据安全</strong>：一键导出/导入全量备份；未配置智能助手时无任何外部网络请求</li>
      </ul>
      <p class="tip">
        支持 Docker 一键部署（如 NAS），浏览器访问即用，多设备数据同步。
      </p>
      <p class="repo-row">
        GitHub 仓库：<a href="https://github.com/xuhaosl/overachievers" target="_blank" rel="noopener">github.com/xuhaosl/overachievers</a>
      </p>
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
</script>

<style scoped>
.card {
  margin-bottom: 12px;
  max-width: 640px;
}
.intro {
  margin: 0 0 10px;
  color: #303133;
  font-size: 14px;
  line-height: 1.7;
}
.feature-list {
  margin: 0 0 10px;
  padding-left: 20px;
  color: #606266;
  font-size: 13px;
  line-height: 1.9;
}
.tip {
  margin: 0 0 12px;
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
}
.repo-row {
  margin: 0;
  font-size: 13px;
  color: #606266;
}
.repo-row a {
  color: var(--el-color-primary);
  text-decoration: none;
}
.repo-row a:hover {
  text-decoration: underline;
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
