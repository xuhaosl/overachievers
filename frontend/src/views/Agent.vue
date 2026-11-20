<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>Agent 工作台</h2>
        <p class="hint">
          用对话完成导入、查询、近况分析与成绩整理。所有写操作都会先生成预览，确认后才落库；
          发送给模型的文本默认经过本地脱敏。
        </p>
      </div>
      <div class="head-ops">
        <el-select v-model="activeBotId" size="small" style="width: 170px" placeholder="选择机器人">
          <el-option v-for="b in bots" :key="b.id" :value="b.id" :label="b.name" />
        </el-select>
        <el-select v-model="activeProfileId" size="small" style="width: 150px" placeholder="Agent 配置">
          <el-option v-for="p in profiles" :key="p.id" :value="p.id" :label="p.name" />
        </el-select>
        <el-select v-model="privacyLevel" size="small" style="width: 130px">
          <el-option label="默认脱敏" value="" />
          <el-option label="不脱敏" value="off" />
          <el-option label="标准" value="standard" />
          <el-option label="严格" value="strict" />
        </el-select>
        <el-button size="small" @click="newConversation">新会话</el-button>
        <el-button size="small" :icon="Setting" @click="$router.push('/ai-bots')">配置</el-button>
      </div>
    </div>

    <div class="workbench">
      <!-- 会话列表 -->
      <aside class="side">
        <el-input v-model="convFilter" size="small" placeholder="搜索会话" clearable />
        <div class="conv-list">
          <el-empty v-if="!filteredConvs.length" description="暂无会话" :image-size="60" />
          <div
            v-for="c in filteredConvs"
            :key="c.id"
            class="conv-item"
            :class="{ active: c.id === conversationId }"
            @click="openConversation(c)"
          >
            <div class="conv-title">{{ c.title }}</div>
            <div class="conv-meta">{{ fmtTime(c.updated_at) }} · {{ c.msg_count }} 条</div>
            <el-button class="conv-del" size="small" text type="danger" @click.stop="removeConversation(c)">
              删除
            </el-button>
          </div>
        </div>
      </aside>

      <!-- 对话区 -->
      <section class="chat">
        <div ref="msgBox" class="msgs">
          <el-empty v-if="!messages.length" description="试试：帮我看看孩子最近的学习情况" />
          <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
            <div class="bubble">
              <div v-if="m.role === 'assistant' && !m.content && streaming && i === messages.length - 1"
                   class="thinking">
                <span class="dot"></span><span class="dot"></span><span class="dot"></span> 正在处理…
              </div>
              <div v-if="m.content" class="md" v-html="md2html(m.content)"></div>

              <div v-if="m.steps?.length" class="steps">
                <div class="steps-title">执行步骤</div>
                <div v-for="(s, j) in m.steps" :key="j" class="step" :class="{ err: s.ok === false }">
                  <span class="step-name">{{ s.name }}</span>
                  <span class="step-text">{{ s.summary || s.error || '' }}</span>
                </div>
              </div>

              <div v-if="m.privacy?.placeholders" class="privacy-tag">
                已脱敏 {{ m.privacy.placeholders }} 处 · {{ privacyLabel(m.privacy.counts) }}
              </div>

              <div v-for="(p, j) in m.pending || []" :key="j" class="pending">
                <div class="pending-text">{{ p.summary }}</div>
                <div class="pending-ops">
                  <el-button size="small" type="primary" :loading="confirming === p.token"
                             @click="confirmPending(p)">确认执行</el-button>
                  <el-button size="small" @click="cancelPending(p)">取消</el-button>
                  <span class="token">token: {{ p.token }}</span>
                </div>
              </div>
            </div>
          </div>
          <div v-if="errorText" class="error">{{ errorText }}</div>
        </div>

        <div class="input">
          <el-input
            v-model="input"
            type="textarea"
            :rows="3"
            resize="none"
            :disabled="streaming"
            placeholder="例如：把这张成绩单录入进去 / 老大最近数学怎么样 / 分析一下这学期的薄弱点（Enter 发送，Shift+Enter 换行）"
            @keydown.enter.exact.prevent="send"
          />
          <div class="input-ops">
            <span class="hint small">{{ streaming ? '处理中…' : `隐私：${privacyLabelText}` }}</span>
            <el-button type="primary" :loading="streaming" :disabled="!canSend" @click="send">发送</el-button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Setting } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { agentApi, aiApi, agentChatStream, errMsg } from '../api'
import { md2html } from '../utils/markdown'

const router = useRouter()
const bots = ref([])
const profiles = ref([])
const conversations = ref([])
const conversationId = ref(null)
const messages = ref([])
const input = ref('')
const streaming = ref(false)
const errorText = ref('')
const msgBox = ref(null)
const convFilter = ref('')
const activeBotId = ref(null)
const activeProfileId = ref(null)
const privacyLevel = ref('')
const confirming = ref('')

const filteredConvs = computed(() =>
  conversations.value.filter((c) => !convFilter.value || (c.title || '').includes(convFilter.value)),
)
const canSend = computed(() => !!activeBotId.value && !!input.value.trim() && !streaming.value)
const privacyLabelText = computed(() => {
  if (privacyLevel.value === 'off') return '不脱敏'
  if (privacyLevel.value === 'strict') return '严格'
  if (privacyLevel.value === 'standard') return '标准'
  return '默认'
})

function fmtTime(t) {
  return (t || '').replace('T', ' ').slice(0, 16)
}

function privacyLabel(counts) {
  if (!counts) return ''
  const labels = { CHILD: '孩子姓名', PERSON: '姓名', SCHOOL: '学校', CLASS: '班级', PHONE: '电话', EMAIL: '邮箱', ID_CARD: '证件号', ADDRESS: '地址', STUDENT_NO: '学号' }
  return Object.entries(counts).map(([k, v]) => `${labels[k] || k}×${v}`).join(' ')
}

async function loadBase() {
  const [b, p] = await Promise.all([aiApi.bots(), agentApi.profiles()])
  bots.value = b.data || []
  profiles.value = p.data || []
  const saved = Number(localStorage.getItem('oa_active_bot') || 0)
  activeBotId.value = bots.value.find((x) => x.id === saved)?.id || bots.value[0]?.id || null
  const savedProfile = Number(localStorage.getItem('oa_active_profile') || 0)
  activeProfileId.value = profiles.value.find((x) => x.id === savedProfile)?.id || profiles.value[0]?.id || null
  privacyLevel.value = localStorage.getItem('oa_privacy_level') || ''
}

async function loadConversations() {
  if (!activeBotId.value) {
    conversations.value = []
    return
  }
  const { data } = await agentApi.conversations({ bot_id: activeBotId.value })
  conversations.value = data || []
  if (!conversationId.value && conversations.value.length) {
    await openConversation(conversations.value[0])
  }
}

watch(activeBotId, async (v) => {
  if (v) localStorage.setItem('oa_active_bot', String(v))
  conversationId.value = null
  messages.value = []
  await loadConversations()
})
watch(activeProfileId, (v) => v && localStorage.setItem('oa_active_profile', String(v)))
watch(privacyLevel, (v) => localStorage.setItem('oa_privacy_level', v || ''))

onMounted(async () => {
  await loadBase()
  await loadConversations()
})

async function openConversation(c) {
  conversationId.value = c.id
  const { data } = await agentApi.messages(c.id)
  messages.value = (data || [])
    .filter((m) => m.role === 'user' || m.role === 'assistant')
    .map((m) => ({
      role: m.role,
      content: m.content,
      steps: m.meta?.steps || [],
      privacy: m.meta?.privacy || null,
      pending: [],
    }))
  await scrollBottom()
}

async function newConversation() {
  if (!activeBotId.value) {
    ElMessage.warning('请先添加一个机器人')
    return
  }
  const { data } = await agentApi.createConversation({
    bot_id: activeBotId.value,
    profile_id: activeProfileId.value,
    privacy_level: privacyLevel.value,
  })
  conversations.value = [data, ...conversations.value]
  conversationId.value = data.id
  messages.value = []
  errorText.value = ''
}

async function removeConversation(c) {
  await ElMessageBox.confirm(`删除会话「${c.title}」？`, '确认删除', { type: 'warning' })
  await agentApi.deleteConversation(c.id)
  conversations.value = conversations.value.filter((x) => x.id !== c.id)
  if (conversationId.value === c.id) {
    conversationId.value = null
    messages.value = []
  }
}

async function scrollBottom() {
  await nextTick()
  if (msgBox.value) msgBox.value.scrollTop = msgBox.value.scrollHeight
}

async function send() {
  if (!canSend.value) return
  const question = input.value.trim()
  input.value = ''
  errorText.value = ''
  const userMsg = { role: 'user', content: question }
  const assistantMsg = { role: 'assistant', content: '', steps: [], pending: [], privacy: null }
  messages.value.push(userMsg, assistantMsg)
  streaming.value = true
  await scrollBottom()

  const last = () => messages.value[messages.value.length - 1]
  try {
    await agentChatStream(
      {
        bot_id: activeBotId.value,
        profile_id: activeProfileId.value,
        conversation_id: conversationId.value,
        question,
        privacy_level: privacyLevel.value,
      },
      (ev) => {
        if (ev.type === 'delta') {
          last().content += ev.text || ''
          scrollBottom()
        } else if (ev.type === 'tool_call') {
          last().steps.push({ name: ev.name, summary: '调用中…', ok: null })
        } else if (ev.type === 'tool_result') {
          const step = last().steps[last().steps.length - 1]
          if (step && step.name === ev.name) {
            step.ok = ev.ok
            step.summary = ev.summary || ev.error || ''
          } else {
            last().steps.push({ name: ev.name, summary: ev.summary || ev.error, ok: ev.ok })
          }
        } else if (ev.type === 'pending_action') {
          last().pending.push({ token: ev.token, summary: ev.summary })
        } else if (ev.type === 'done') {
          if (ev.conversation_id) conversationId.value = ev.conversation_id
          if (ev.privacy) last().privacy = ev.privacy
          if (ev.title) {
            const found = conversations.value.find((c) => c.id === conversationId.value)
            if (found) found.title = ev.title
          }
        }
      },
    )
    await loadConversations()
  } catch (e) {
    errorText.value = e?.message || 'Agent 运行失败'
  } finally {
    streaming.value = false
    await scrollBottom()
  }
}

async function confirmPending(p) {
  confirming.value = p.token
  try {
    const { data } = await agentApi.confirm(p.token)
    ElMessage.success(data?.result?.summary || '已执行')
    messages.value.push({
      role: 'assistant',
      content: `已确认执行：${data?.result?.summary || ''}`,
      steps: [],
      pending: [],
    })
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    confirming.value = ''
  }
}

async function cancelPending(p) {
  try {
    await agentApi.cancel(p.token)
    ElMessage.success('已取消')
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}
</script>

<style scoped>
.page {
  padding: 16px;
  display: flex;
  flex-direction: column;
  height: calc(100vh - 32px);
  box-sizing: border-box;
}
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}
.page-head h2 {
  margin: 0 0 4px;
}
.hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin: 0;
}
.hint.small {
  font-size: 12px;
}
.head-ops {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.workbench {
  display: flex;
  gap: 12px;
  flex: 1;
  min-height: 0;
  margin-top: 12px;
}
.side {
  width: 230px;
  flex: 0 0 230px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
}
.conv-list {
  overflow: auto;
  flex: 1;
}
.conv-item {
  position: relative;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  border: 1px solid transparent;
}
.conv-item:hover {
  background: var(--el-fill-color-light);
}
.conv-item.active {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-7);
}
.conv-title {
  font-size: 13px;
  line-height: 1.4;
  padding-right: 34px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.conv-meta {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}
.conv-del {
  position: absolute;
  right: 4px;
  top: 6px;
  opacity: 0;
}
.conv-item:hover .conv-del {
  opacity: 1;
}
.chat {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  overflow: hidden;
}
.msgs {
  flex: 1;
  overflow: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.msg {
  display: flex;
}
.msg.user {
  justify-content: flex-end;
}
.bubble {
  max-width: min(760px, 88%);
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--el-fill-color-light);
  font-size: 14px;
  line-height: 1.65;
}
.msg.user .bubble {
  background: var(--el-color-primary-light-9);
}
.steps {
  margin-top: 8px;
  border-top: 1px dashed var(--el-border-color);
  padding-top: 6px;
}
.steps-title {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.step {
  font-size: 12px;
  color: var(--el-text-color-regular);
  display: flex;
  gap: 6px;
}
.step.err {
  color: var(--el-color-danger);
}
.step-name {
  font-family: ui-monospace, Menlo, monospace;
}
.privacy-tag {
  margin-top: 6px;
  font-size: 11px;
  color: var(--el-color-success);
}
.pending {
  margin-top: 8px;
  padding: 8px 10px;
  border: 1px solid var(--el-color-warning-light-5);
  background: var(--el-color-warning-light-9);
  border-radius: 8px;
}
.pending-text {
  font-size: 13px;
  margin-bottom: 6px;
}
.pending-ops {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.token {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  font-family: ui-monospace, Menlo, monospace;
}
.thinking {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.dot {
  display: inline-block;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--el-color-primary);
  margin-right: 3px;
  animation: blink 1.2s infinite;
}
.dot:nth-child(2) {
  animation-delay: 0.2s;
}
.dot:nth-child(3) {
  animation-delay: 0.4s;
}
@keyframes blink {
  0%, 100% { opacity: 0.25; }
  50% { opacity: 1; }
}
.error {
  color: var(--el-color-danger);
  font-size: 13px;
}
.input {
  border-top: 1px solid var(--el-border-color-lighter);
  padding: 10px;
}
.input-ops {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
}
@media (max-width: 900px) {
  .side {
    display: none;
  }
}
</style>
