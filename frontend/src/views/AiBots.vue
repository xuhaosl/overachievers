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

    <el-card class="search-card" shadow="never">
      <template #header>原题检索（预留）</template>
      <p class="hint">
        错题 AI 识别后可联网查找原题（先联网、查不到再由 AI 自组织）。本期仅保留配置入口：未填 Key 时自动跳过联网检索，不影响错题整理。
      </p>
      <el-form inline>
        <el-form-item label="服务商">
          <el-select v-model="searchConfig.provider" style="width: 150px">
            <el-option label="Tavily" value="tavily" />
            <el-option label="Serper" value="serper" />
            <el-option label="Bing" value="bing" />
          </el-select>
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="searchConfig.api_key"
            type="password"
            show-password
            style="width: 260px"
            :placeholder="searchConfig.configured ? `已配置 ${searchConfig.api_key_masked}，留空保留` : '暂未接入，可先留空'"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="savingSearch" @click="saveSearchConfig">保存</el-button>
        </el-form-item>
      </el-form>
    </el-card>

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
        <el-form-item label="温度">
          <el-slider v-model="form.temperature" :min="0" :max="2" :step="0.1" show-input />
        </el-form-item>
        <el-form-item label="最大输出">
          <el-input-number v-model="form.max_tokens" :min="64" :max="200000" :step="256" style="width: 160px" />
          <span class="hint inline">tokens</span>
        </el-form-item>
        <el-form-item label="超时">
          <el-input-number v-model="form.timeout" :min="5" :max="600" :step="5" style="width: 160px" />
          <span class="hint inline">秒</span>
        </el-form-item>
        <el-form-item label="故障回退">
          <el-select v-model="form.fallback_bot_id" clearable placeholder="主模型失败时改用" style="width: 100%">
            <el-option v-for="b in bots.filter((x) => x.id !== form.id)" :key="b.id" :value="b.id"
                       :label="`${b.name}（${b.model}）`" />
          </el-select>
        </el-form-item>
        <el-form-item label="额外请求头">
          <el-input
            v-model="form.extra_headers"
            type="textarea"
            :rows="2"
            placeholder='JSON，如 {"HTTP-Referer": "https://example.com"}'
          />
        </el-form-item>
        <el-form-item label="启用 / 默认">
          <el-switch v-model="form.enabled" active-text="启用" inline-prompt />
          <el-switch v-model="form.is_default" active-text="默认" inline-prompt style="margin-left: 12px" />
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

    <!-- Agent 配置 -->
    <el-card class="agent-card" shadow="never">
      <template #header>
        <div class="agent-head">
          <span>Agent 配置</span>
          <el-button size="small" type="primary" :icon="Plus" @click="openProfile()">新增配置</el-button>
        </div>
      </template>
      <p class="hint">
        每个配置决定 Agent 能用哪些工具、是否允许写入、是否需要二次确认，以及独立的隐私级别。
        写工具默认需要确认；勾选“自动执行”会跳过确认，请谨慎使用。
      </p>
      <el-table :data="profiles" size="small">
        <el-table-column prop="name" label="名称" width="140" />
        <el-table-column label="绑定机器人" width="160">
          <template #default="{ row }">{{ botName(row.bot_id) }}</template>
        </el-table-column>
        <el-table-column label="工具" width="120">
          <template #default="{ row }">
            {{ row.tools?.length ? `${row.tools.length} 个` : '全部' }}
          </template>
        </el-table-column>
        <el-table-column label="写入" width="90">
          <template #default="{ row }">{{ row.allow_write ? '允许' : '只读' }}</template>
        </el-table-column>
        <el-table-column label="确认" width="100">
          <template #default="{ row }">{{ row.auto_approve ? '自动执行' : '需确认' }}</template>
        </el-table-column>
        <el-table-column label="隐私" width="100">
          <template #default="{ row }">{{ row.privacy_level || '默认' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-button size="small" text @click="openProfile(row)">编辑</el-button>
            <el-button size="small" text type="danger" @click="removeProfile(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 隐私与安全 -->
    <el-card class="agent-card" shadow="never">
      <template #header>
        <div class="agent-head">
          <span>儿童隐私脱敏</span>
          <el-tag size="small" :type="guardTagType">{{ guardTagText }}</el-tag>
        </div>
      </template>
      <p class="hint">
        发送给第三方模型前，本地会把孩子姓名、学校、班级、学号、电话、邮箱、地址等替换成稳定占位符
        <code v-text="placeholderSample"></code>；模型回复中的占位符会在本地还原。
        架构参考 magpie：占位符可逆、流式分片安全、同一值跨轮次一致。
      </p>
      <el-descriptions :column="2" size="small" border>
        <el-descriptions-item label="密钥加密">
          {{ privacy.secret?.scheme || '-' }}（来源 {{ privacy.secret?.key_source || '-' }}）
        </el-descriptions-item>
        <el-descriptions-item label="密钥往返校验">
          {{ privacy.roundtrip_ok ? '正常' : '异常' }}
        </el-descriptions-item>
        <el-descriptions-item label="AstrLink Guard">
          {{ privacy.privacy?.guard?.installed ? '模型文件已就位' : '未安装（使用内置规则）' }}
        </el-descriptions-item>
        <el-descriptions-item label="模型目录">
          {{ privacy.privacy?.guard?.model_dir || '-' }}
        </el-descriptions-item>
      </el-descriptions>
      <div class="preview-box">
        <el-input
          v-model="previewText"
          type="textarea"
          :rows="3"
          placeholder="粘贴一段文字，预览脱敏效果（不会发送到任何外部服务）"
        />
        <div class="preview-ops">
          <el-select v-model="previewLevel" size="small" style="width: 130px">
            <el-option label="标准" value="standard" />
            <el-option label="严格" value="strict" />
            <el-option label="不脱敏" value="off" />
          </el-select>
          <el-button size="small" type="primary" :loading="previewing" @click="runPreview">预览</el-button>
        </div>
        <div v-if="previewResult" class="preview-result">
          <div class="preview-line"><b>脱敏后：</b>{{ previewResult.redacted }}</div>
          <div class="preview-line">
            <b>还原校验：</b>
            <el-tag size="small" :type="previewResult.roundtrip_ok ? 'success' : 'danger'">
              {{ previewResult.roundtrip_ok ? '一致' : '不一致' }}
            </el-tag>
            <span class="hint inline">{{ previewStats }}</span>
          </div>
        </div>
      </div>
    </el-card>

    <!-- Agent 配置编辑 -->
    <el-dialog v-model="profileVisible" :title="profileForm.id ? '编辑 Agent 配置' : '新增 Agent 配置'" width="560px">
      <el-form :model="profileForm" label-width="100px">
        <el-form-item label="名称" required>
          <el-input v-model="profileForm.name" maxlength="50" placeholder="如：数据录入助手" />
        </el-form-item>
        <el-form-item label="绑定机器人">
          <el-select v-model="profileForm.bot_id" clearable style="width: 100%" placeholder="使用哪个 Provider 机器人">
            <el-option v-for="b in bots" :key="b.id" :value="b.id" :label="`${b.name}（${b.model}）`" />
          </el-select>
        </el-form-item>
        <el-form-item label="可用工具">
          <el-select v-model="profileForm.tools" multiple filterable collapse-tags style="width: 100%"
                     placeholder="留空 = 全部工具">
            <el-option v-for="t in allTools" :key="t" :value="t" :label="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="隐私级别">
          <el-select v-model="profileForm.privacy_level" style="width: 100%">
            <el-option label="跟随全局默认" value="" />
            <el-option label="不脱敏" value="off" />
            <el-option label="标准" value="standard" />
            <el-option label="严格" value="strict" />
          </el-select>
        </el-form-item>
        <el-form-item label="写入权限">
          <el-switch v-model="profileForm.allow_write" active-text="允许新增数据" inline-prompt />
        </el-form-item>
        <el-form-item label="执行方式">
          <el-switch v-model="profileForm.auto_approve" active-text="自动执行" inactive-text="需确认" inline-prompt />
        </el-form-item>
        <el-form-item label="附加提示词">
          <el-input v-model="profileForm.system_prompt" type="textarea" :rows="3"
                    placeholder="追加到 Agent 系统提示，如“回答尽量简短，多给具体练习建议”" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="profileVisible = false">取消</el-button>
        <el-button type="primary" @click="saveProfile">保存</el-button>
      </template>
    </el-dialog>

    <!-- 会话历史：按会话折叠 -->
    <el-dialog v-model="historyVisible" :title="`会话历史 - ${historyBot?.name || ''}`" width="680px" top="6vh">
      <div class="hist-ops">
        <span class="hint" style="margin: 0">{{ conversations.length }} 个会话</span>
        <el-button size="small" type="danger" plain :disabled="!conversations.length" @click="clearHistory">
          清空记录
        </el-button>
      </div>
      <div class="hist-list">
        <el-empty v-if="!conversations.length" description="暂无会话记录" />
        <el-collapse v-model="expandedConvs">
          <el-collapse-item v-for="c in conversations" :key="c.id" :name="c.id">
            <template #title>
              <div class="conv-head">
                <span class="conv-head-title">{{ c.title }}</span>
                <span class="conv-head-meta">{{ fmtTime(c.updated_at) }} · {{ c.msg_count }} 条</span>
                <el-button size="small" text @click.stop="renameConversation(c)">重命名</el-button>
                <el-button size="small" text type="danger" @click.stop="removeConversation(c)">删除会话</el-button>
              </div>
            </template>
            <div v-if="convMsgs[c.id]" class="conv-msgs">
              <div v-for="m in convMsgs[c.id]" :key="m.id" class="hist-item" :class="m.role">
                <div class="hist-meta">
                  <span>{{ m.role === 'user' ? '我' : 'AI' }} · {{ fmtTime(m.created_at) }}</span>
                </div>
                <div class="hist-content">{{ m.content }}</div>
              </div>
            </div>
            <div v-else class="conv-loading">加载中…</div>
          </el-collapse-item>
        </el-collapse>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { agentApi, aiApi, api, confirmDelete, errMsg } from '../api'

const bots = ref([])
const providers = ref([])
const loaded = ref(false)
const searchConfig = ref({ provider: 'tavily', api_key: '', api_key_masked: '', configured: false })
const savingSearch = ref(false)

// Agent 配置 / 隐私
const profiles = ref([])
const allTools = ref([])
const privacy = ref({})
const profileVisible = ref(false)
const profileForm = ref({})
const previewText = ref('')
const previewLevel = ref('standard')
const previewResult = ref(null)
const previewing = ref(false)
const placeholderSample = '{{CHILD_xxxxxxxx}}'

const guardTagType = computed(() => (privacy.value.privacy?.guard?.available ? 'success' : 'info'))
const guardTagText = computed(() => {
  const g = privacy.value.privacy?.guard
  if (!g) return '加载中'
  if (g.available) return 'AstrLink Guard 可用'
  if (g.installed) return '模型已就位但缺少运行时'
  return '内置规则脱敏'
})
const previewStats = computed(() => {
  const counts = previewResult.value?.stats?.counts || {}
  const parts = Object.entries(counts).map(([k, v]) => `${k}×${v}`)
  return parts.length ? `已脱敏：${parts.join(' ')}` : '未命中敏感实体'
})

const editVisible = ref(false)
const form = ref({})
const testing = ref(false)
const testResult = ref(null)
const historyVisible = ref(false)
const historyBot = ref(null)
const conversations = ref([])
const expandedConvs = ref([])
const convMsgs = ref({}) // convId -> messages，展开时懒加载

const currentProvider = computed(() => providers.value.find((p) => p.key === form.value.provider))

// 展开折叠项时懒加载该会话消息
watch(expandedConvs, async (names) => {
  for (const id of names) {
    if (!convMsgs.value[id]) {
      const { data } = await aiApi.convMessages(id)
      convMsgs.value = { ...convMsgs.value, [id]: data }
    }
  }
})

function fmtTime(t) {
  return (t || '').replace('T', ' ').slice(0, 16)
}

async function load() {
  const [b, p, sc, pr, tls, st] = await Promise.all([
    aiApi.bots(),
    aiApi.providers(),
    api.get('/mistakes/search-config'),
    agentApi.profiles(),
    agentApi.tools(),
    agentApi.status(),
  ])
  bots.value = b.data
  providers.value = p.data
  searchConfig.value = { ...sc.data, api_key: '' }
  profiles.value = pr.data || []
  allTools.value = tls.data?.names || []
  privacy.value = st.data || {}
  loaded.value = true
}
onMounted(load)

// ---------- Agent 配置 ----------
function botName(id) {
  return bots.value.find((b) => b.id === id)?.name || '未绑定'
}

function openProfile(row) {
  profileForm.value = row
    ? { ...row, tools: [...(row.tools || [])] }
    : { name: '通用助手', bot_id: bots.value[0]?.id || null, tools: [], privacy_level: '', allow_write: true, auto_approve: false, system_prompt: '' }
  profileVisible.value = true
}

async function saveProfile() {
  if (!profileForm.value.name?.trim()) {
    ElMessage.warning('请填写名称')
    return
  }
  try {
    if (profileForm.value.id) await agentApi.updateProfile(profileForm.value.id, profileForm.value)
    else await agentApi.createProfile(profileForm.value)
    ElMessage.success('已保存')
    profileVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function removeProfile(row) {
  await ElMessageBox.confirm(`删除 Agent 配置「${row.name}」？`, '确认删除', { type: 'warning' })
  await agentApi.deleteProfile(row.id)
  ElMessage.success('已删除')
  await load()
}

async function runPreview() {
  if (!previewText.value.trim()) {
    ElMessage.warning('请先输入一段文字')
    return
  }
  previewing.value = true
  try {
    const { data } = await agentApi.privacyPreview({ text: previewText.value, level: previewLevel.value })
    previewResult.value = data
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    previewing.value = false
  }
}

async function saveSearchConfig() {
  savingSearch.value = true
  try {
    await api.put('/mistakes/search-config', {
      provider: searchConfig.value.provider,
      api_key: searchConfig.value.api_key,
    })
    const { data } = await api.get('/mistakes/search-config')
    searchConfig.value = { ...data, api_key: '' }
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    savingSearch.value = false
  }
}

function onProviderChange(key) {
  const p = providers.value.find((x) => x.key === key)
  form.value.base_url = p?.base_url || ''
  form.value.model = p?.models?.[0] || ''
}

function openEdit(bot) {
  form.value = bot
    ? { ...bot, api_key: '' }
    : {
        name: '', provider: 'deepseek', base_url: '', api_key: '', model: '',
        temperature: 0.7, max_tokens: 1600, timeout: 120, extra_headers: '{}',
        enabled: true, is_default: false, fallback_bot_id: null,
      }
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
  expandedConvs.value = []
  convMsgs.value = {}
  const { data } = await aiApi.conversations(bot.id)
  conversations.value = data
  // 默认展开最近一个会话
  if (data.length) expandedConvs.value = [data[0].id]
}

async function removeConversation(c) {
  await aiApi.deleteConversation(c.id)
  conversations.value = conversations.value.filter((x) => x.id !== c.id)
}

async function renameConversation(c) {
  try {
    const { value } = await ElMessageBox.prompt('修改会话名称', '重命名', {
      inputValue: c.title,
      inputPattern: /\S/,
      inputErrorMessage: '名称不能为空',
      maxLength: 60,
    })
    await aiApi.renameConversation(c.id, value.trim())
    const idx = conversations.value.findIndex((x) => x.id === c.id)
    if (idx >= 0) conversations.value[idx].title = value.trim()
  } catch (e) {
    if (e !== 'cancel' && e?.message) ElMessage.error(e.message)
  }
}

async function clearHistory() {
  await aiApi.clearMessages(historyBot.value.id)
  conversations.value = []
  convMsgs.value = {}
  ElMessage.success('已清空')
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
.conv-head {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding-right: 8px;
}
.conv-head-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}
.conv-head-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
.conv-msgs {
  padding: 4px 0;
}
.conv-loading {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  padding: 8px;
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
.hint.inline {
  margin: 0 0 0 8px;
  font-size: 12px;
}
.agent-card {
  margin-top: 16px;
}
.agent-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.preview-box {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.preview-ops {
  display: flex;
  gap: 8px;
  align-items: center;
}
.preview-result {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 8px 10px;
  background: var(--el-fill-color-lighter);
  font-size: 13px;
  word-break: break-word;
}
.preview-line + .preview-line {
  margin-top: 6px;
}
</style>
