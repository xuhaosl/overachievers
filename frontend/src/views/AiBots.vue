<template>
  <div class="page">
    <div class="page-head">
      <h2>智能助手</h2>
      <el-button type="primary" :icon="Plus" @click="openEdit()">添加机器人</el-button>
    </div>
    <p class="hint">
      添加机器人需要对应厂商的 API Key（在各厂商官网注册获取）。选择厂商后接口地址与模型自动填好，一般只需填 Key。
      提醒：对话时选中的成绩数据会发送给所选厂商的模型服务。
    </p>

    <el-empty v-if="!bots.length && loaded" description="还没有添加机器人" />

    <div class="bot-grid">
      <el-card v-for="b in bots" :key="b.id" class="bot-card" shadow="hover">
        <div class="bot-title">
          <span class="bot-name">{{ b.name }}</span>
          <el-tag size="small" type="info">{{ b.provider_label }}</el-tag>
        </div>
        <div class="bot-line">模型：{{ b.model }}</div>
        <div class="bot-line">Key：{{ b.has_key ? b.api_key_masked : '未配置' }}</div>
        <div class="bot-line">接口：{{ b.base_url || '（厂商默认）' }}</div>
        <div class="bot-ops">
          <el-button size="small" @click="openHistory(b)">会话历史</el-button>
          <el-button size="small" @click="openEdit(b)">编辑</el-button>
          <el-button size="small" type="danger" plain @click="removeBot(b)">删除</el-button>
        </div>
      </el-card>
    </div>

    <!-- 添加/编辑 -->
    <el-dialog v-model="editVisible" :title="form.id ? '编辑机器人' : '添加机器人'" width="480px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如：DeepSeek 分析助手" maxlength="50" />
        </el-form-item>
        <el-form-item label="厂商" required>
          <el-select v-model="form.provider" style="width: 100%" @change="onProviderChange">
            <el-option v-for="p in providers" :key="p.key" :value="p.key" :label="p.label" />
          </el-select>
        </el-form-item>
        <el-form-item label="接口地址">
          <el-input v-model="form.base_url" :placeholder="currentProvider?.base_url || 'https://.../v1'" />
        </el-form-item>
        <el-form-item label="API Key" :required="!form.id">
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            :placeholder="form.id ? '留空则保留原 Key' : 'sk-...'"
          />
        </el-form-item>
        <el-form-item label="模型" required>
          <el-select
            v-model="form.model"
            style="width: 100%"
            filterable
            allow-create
            default-first-option
            placeholder="选择或直接输入模型名"
          >
            <el-option v-for="m in currentProvider?.models || []" :key="m" :value="m" :label="m" />
          </el-select>
        </el-form-item>
        <el-form-item label=" ">
          <el-button :loading="testing" @click="testConnection">测试连接</el-button>
          <span v-if="testResult" class="test-result" :class="{ ok: testResult.ok }">
            {{ testResult.message }}
          </span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" @click="saveBot">保存</el-button>
      </template>
    </el-dialog>

    <!-- 会话历史 -->
    <el-dialog v-model="historyVisible" :title="`会话历史 - ${historyBot?.name || ''}`" width="640px" top="6vh">
      <div class="hist-ops">
        <span class="hint" style="margin: 0">{{ historyMsgs.length }} 条记录</span>
        <el-button size="small" type="danger" plain :disabled="!historyMsgs.length" @click="clearHistory">
          清空记录
        </el-button>
      </div>
      <div class="hist-list">
        <el-empty v-if="!historyMsgs.length" description="暂无会话记录" />
        <div v-for="m in historyMsgs" :key="m.id" class="hist-item" :class="m.role">
          <div class="hist-meta">
            <span>{{ m.role === 'user' ? '我' : 'AI' }} · {{ (m.created_at || '').replace('T', ' ').slice(0, 16) }}</span>
            <el-button size="small" text type="danger" @click="delMessage(m)">删除</el-button>
          </div>
          <div class="hist-content">{{ m.content }}</div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { aiApi, confirmDelete, errMsg } from '../api'

const bots = ref([])
const providers = ref([])
const loaded = ref(false)

const editVisible = ref(false)
const form = ref({})
const testing = ref(false)
const testResult = ref(null)
const historyVisible = ref(false)
const historyBot = ref(null)
const historyMsgs = ref([])

const currentProvider = computed(() => providers.value.find((p) => p.key === form.value.provider))

async function load() {
  const [b, p] = await Promise.all([aiApi.bots(), aiApi.providers()])
  bots.value = b.data
  providers.value = p.data
  loaded.value = true
}
onMounted(load)

function onProviderChange(key) {
  const p = providers.value.find((x) => x.key === key)
  form.value.base_url = p?.base_url || ''
  form.value.model = p?.models?.[0] || ''
}

function openEdit(bot) {
  form.value = bot
    ? { ...bot, api_key: '' }
    : { name: '', provider: 'deepseek', base_url: '', api_key: '', model: '' }
  if (!bot) onProviderChange('deepseek')
  else form.value.base_url = bot.base_url
  testResult.value = null
  editVisible.value = true
}

// 连接测试：发一个极小请求验证配置（编辑时 key 留空用已存 key）
async function testConnection() {
  if (!form.value.model) {
    ElMessage.warning('请先选择或填写模型名')
    return
  }
  testing.value = true
  testResult.value = null
  try {
    const { data } = await aiApi.testBot({
      provider: form.value.provider,
      base_url: form.value.base_url,
      api_key: form.value.api_key,
      model: form.value.model,
      bot_id: form.value.id || null,
    })
    testResult.value = data
  } catch (e) {
    testResult.value = { ok: false, message: errMsg(e) }
  } finally {
    testing.value = false
  }
}

async function saveBot() {
  try {
    if (form.value.id) await aiApi.updateBot(form.value.id, form.value)
    else await aiApi.createBot(form.value)
    ElMessage.success('已保存')
    editVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function removeBot(bot) {
  await confirmDelete(`/ai/bots/${bot.id}`, '删除机器人将一并删除其会话记录')
  ElMessage.success('已删除')
  await load()
}

async function openHistory(bot) {
  historyBot.value = bot
  historyVisible.value = true
  const { data } = await aiApi.messages(bot.id)
  historyMsgs.value = data
}

async function clearHistory() {
  await aiApi.clearMessages(historyBot.value.id)
  historyMsgs.value = []
  ElMessage.success('已清空')
}

async function delMessage(m) {
  await aiApi.deleteMessage(m.id)
  historyMsgs.value = historyMsgs.value.filter((x) => x.id !== m.id)
}
</script>

<style scoped>
.page {
  padding: 16px;
}
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.page-head h2 {
  margin: 0 0 8px;
}
.hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin: 4px 0 16px;
}
.bot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
}
.bot-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.bot-name {
  font-weight: bold;
  font-size: 15px;
}
.bot-line {
  font-size: 13px;
  color: var(--el-text-color-regular);
  line-height: 1.8;
  word-break: break-all;
}
.bot-ops {
  margin-top: 10px;
  display: flex;
  gap: 0;
}
.test-result {
  margin-left: 10px;
  font-size: 13px;
  color: var(--el-color-danger);
}
.test-result.ok {
  color: var(--el-color-success);
}
.hist-ops {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.hist-list {
  max-height: 60vh;
  overflow-y: auto;
}
.hist-item {
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 8px;
}
.hist-item.assistant {
  background: var(--el-fill-color-lighter);
}
.hist-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.hist-content {
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
