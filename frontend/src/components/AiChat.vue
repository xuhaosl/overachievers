<template>
  <!-- 呼出按钮 -->
  <el-button
    v-if="!visible"
    class="ai-fab"
    type="primary"
    circle
    size="large"
    title="智能助手"
    @click="open()"
  >
    <el-icon :size="22"><ChatDotRound /></el-icon>
  </el-button>

  <!-- 侧栏 -->
  <teleport to="body">
    <div v-if="visible" class="ai-mask" @click="close()"></div>
    <div v-if="visible" class="ai-panel">
      <div class="ai-head">
        <el-select
          v-model="activeBotId"
          size="small"
          style="width: 180px"
          placeholder="选择机器人"
          @change="onBotChange"
        >
          <el-option v-for="b in bots" :key="b.id" :value="b.id" :label="b.name" />
        </el-select>
        <div class="ai-head-ops">
          <el-button size="small" text :icon="Setting" @click="gotoSettings">管理</el-button>
          <el-button size="small" text :icon="Close" @click="close()" />
        </div>
      </div>

      <!-- 数据范围 -->
      <div class="ai-scope">
        <div class="ai-scope-row">
          <span class="ai-scope-label">孩子</span>
          <el-select
            v-model="scope.child_id"
            size="small"
            placeholder="全部"
            clearable
            style="flex: 1"
            @change="scope.exam_id = null; loadExams()"
          >
            <el-option v-for="c in children" :key="c.id" :value="c.id" :label="c.name" />
          </el-select>
        </div>
        <div class="ai-scope-row">
          <span class="ai-scope-label">场次</span>
          <el-select
            v-model="scope.exam_id"
            size="small"
            placeholder="不限"
            clearable
            filterable
            style="flex: 1"
          >
            <el-option v-for="e in exams" :key="e.id" :value="e.id" :label="`${e.date} ${e.name || e.type}`" />
          </el-select>
        </div>
        <div class="ai-scope-row">
          <span class="ai-scope-label">学科</span>
          <el-select v-model="scope.subject_id" size="small" placeholder="全部" clearable style="flex: 1">
            <el-option v-for="s in subjects" :key="s.id" :value="s.id" :label="s.name" />
          </el-select>
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            size="small"
            value-format="YYYY-MM-DD"
            start-placeholder="开始"
            end-placeholder="结束"
            style="flex: 1.4"
          />
        </div>
        <div v-if="focusLabel" class="ai-focus">
          评语目标：{{ focusLabel }}
          <el-button size="small" text type="danger" @click="clearFocus">取消</el-button>
        </div>
      </div>

      <!-- 消息区 -->
      <div ref="msgBox" class="ai-msgs">
        <div v-if="!bots.length" class="ai-empty">
          <p>还没有添加 AI 机器人</p>
          <el-button type="primary" size="small" @click="gotoSettings">去添加</el-button>
        </div>
        <template v-for="(m, i) in messages" :key="i">
          <div class="ai-msg" :class="m.role">
            <div class="ai-bubble">
              <!-- 等待首个回复片段时显示分析中提示 -->
              <div v-if="m.role === 'assistant' && !m.content && streaming && i === messages.length - 1" class="ai-thinking">
                <span class="dot"></span><span class="dot"></span><span class="dot"></span>
                正在分析中…
              </div>
              <template v-for="(seg, j) in segments(m.content)" :key="j">
                <div v-if="seg.type === 'text'" class="ai-text md" v-html="md2html(seg.text)"></div>
                <div v-else class="ai-comment-card">
                  <div class="ai-comment-title">AI 评语</div>
                  <div class="ai-comment-body">{{ seg.text }}</div>
                  <el-button
                    v-if="focusLabel && m.role === 'assistant'"
                    size="small"
                    type="primary"
                    @click="writeComment(seg.text)"
                  >
                    写入
                  </el-button>
                </div>
              </template>
            </div>
          </div>
        </template>
        <div v-if="errorText" class="ai-error">{{ errorText }}</div>
      </div>

      <!-- 输入区 -->
      <div class="ai-input">
        <el-input
          v-model="input"
          type="textarea"
          :rows="2"
          resize="none"
          placeholder="问点什么…（Enter 发送，Shift+Enter 换行）"
          :disabled="streaming || !activeBotId"
          @keydown.enter.exact.prevent="send"
        />
        <el-button type="primary" :loading="streaming" :disabled="!activeBotId || !input.trim()" @click="send">
          发送
        </el-button>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ChatDotRound, Close, Setting } from '@element-plus/icons-vue'
import { aiApi, aiChatStream, errMsg } from '../api'

const props = defineProps({ modelValue: Boolean, presetScope: Object })
const emit = defineEmits(['update:modelValue'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const router = useRouter()
const bots = ref([])
const activeBotId = ref(null)
const children = ref([])
const subjects = ref([])
const exams = ref([])
const messages = ref([])
const input = ref('')
const streaming = ref(false)
const errorText = ref('')
const msgBox = ref(null)
const dateRange = ref(null)
const scope = ref({ child_id: null, exam_id: null, subject_id: null })
const focus = ref(null) // {type:'score'|'exam', id, label}

const focusLabel = computed(() => focus.value?.label || '')

async function loadBots() {
  const { data } = await aiApi.bots()
  bots.value = data
  if (!activeBotId.value && data.length) {
    activeBotId.value = data[0].id
    loadHistory()
  }
}

async function loadHistory() {
  if (!activeBotId.value) return
  const { data } = await aiApi.messages(activeBotId.value)
  messages.value = data.map((m) => ({ role: m.role, content: m.content }))
  scrollBottom()
}

function onBotChange() {
  errorText.value = ''
  loadHistory()
}

async function loadExams() {
  if (!scope.value.child_id) {
    exams.value = []
    return
  }
  const { data } = await api.get('/exams', { params: { child_id: scope.value.child_id } })
  exams.value = data
}

function open(preset) {
  visible.value = true
  loadBots()
  loadBase()
  // 详情页打开自动聚焦当前对象；外部传入 preset（"问 AI"按钮）优先
  if (preset) applyPreset(preset)
  else detectFromRoute()
}

// 当前路由是成绩/场次详情页时，自动加载并预填为数据范围与评语目标
async function detectFromRoute() {
  const m = router.currentRoute.value.path.match(/^\/(score|exam)\/(\d+)$/)
  if (!m) return
  const [, kind, id] = m
  try {
    if (kind === 'score') {
      const { data } = await api.get(`/scores/${id}`)
      applyPreset({
        child_id: data.child_id,
        subject_id: data.subject_id,
        date_from: data.date,
        date_to: data.date,
        focus: { type: 'score', id: data.id, label: `${data.subject_name} ${data.date} ${data.regular_score}分` },
      })
    } else {
      const { data } = await api.get(`/exams/${id}`)
      applyPreset({
        child_id: data.child_id,
        exam_id: data.id,
        focus: { type: 'exam', id: data.id, label: `${data.name || data.type} ${data.date}` },
      })
    }
  } catch {
    /* 详情加载失败则不预填 */
  }
}

function applyPreset(p) {
  scope.value = {
    child_id: p.child_id ?? null,
    exam_id: p.exam_id ?? null,
    subject_id: p.subject_id ?? null,
  }
  dateRange.value = p.date_from ? [p.date_from, p.date_to] : null
  focus.value = p.focus || null
  loadExams()
}

function clearFocus() {
  focus.value = null
}

function gotoSettings() {
  visible.value = false
  router.push('/ai-bots')
}

async function loadBase() {
  if (!children.value.length) {
    const [c, s] = await Promise.all([api.get('/children'), api.get('/subjects')])
    children.value = c.data
    subjects.value = s.data
    // 未选孩子时默认聚焦第一个（可手动清除，清除后后端会带全部孩子数据）
    if (!scope.value.child_id && children.value.length) {
      scope.value.child_id = children.value[0].id
    }
  }
}

onMounted(() => {
  // 详情页通过全局事件呼出：window.dispatchEvent(new CustomEvent('ai-open', {detail: scope}))
  window.addEventListener('ai-open', (e) => open(e.detail || {}))
})

watch(
  () => props.presetScope,
  (v) => {
    if (v && visible.value) applyPreset(v)
  },
)

function scrollBottom() {
  nextTick(() => {
    if (msgBox.value) msgBox.value.scrollTop = msgBox.value.scrollHeight
  })
}

// <comment> 标签解析：评语卡片 + 普通文本段
function segments(content) {
  const segs = []
  const re = /<comment>([\s\S]*?)<\/comment>/g
  let last = 0
  let m
  while ((m = re.exec(content))) {
    if (m.index > last) segs.push({ type: 'text', text: content.slice(last, m.index) })
    segs.push({ type: 'comment', text: m[1].trim() })
    last = m.index + m[0].length
  }
  if (last < content.length) segs.push({ type: 'text', text: content.slice(last) })
  return segs.length ? segs : [{ type: 'text', text: content }]
}

// 极简 Markdown 渲染（先转义 HTML 防注入）：标题/加粗/行内代码/列表/换行
function md2html(text) {
  let h = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  h = h
    .replace(/^#{1,6}\s+(.+)$/gm, '<div class="md-h">$1</div>')
    .replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>')
    .replace(/`([^`\n]+)`/g, '<code>$1</code>')
  // 无序/有序列表块
  h = h.replace(/(?:^|\n)((?:[-*]\s+.+(?:\n|$))+)/g, (_, block) =>
    '\n<ul>' +
    block.trim().split('\n').map((l) => `<li>${l.replace(/^[-*]\s+/, '')}</li>`).join('') +
    '</ul>',
  )
  h = h.replace(/(?:^|\n)((?:\d+[.、]\s+.+(?:\n|$))+)/g, (_, block) =>
    '\n<ol>' +
    block.trim().split('\n').map((l) => `<li>${l.replace(/^\d+[.、]\s+/, '')}</li>`).join('') +
    '</ol>',
  )
  // 剩余换行变 <br>（列表结构除外）
  h = h
    .replace(/\n*(<\/?(?:ul|ol)>)/g, '$1')
    .replace(/(<\/li>)\n/g, '$1')
    .replace(/\n/g, '<br>')
  return h
}

async function writeComment(text) {
  if (!focus.value) return
  try {
    if (focus.value.type === 'score') await aiApi.setScoreComment(focus.value.id, text)
    else await aiApi.setExamComment(focus.value.id, text)
    ElMessage.success('评语已写入')
    window.dispatchEvent(new CustomEvent('ai-comment-updated', { detail: focus.value }))
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function send() {
  const q = input.value.trim()
  if (!q || streaming.value || !activeBotId.value) return
  errorText.value = ''
  input.value = ''
  messages.value.push({ role: 'user', content: q })
  const aiMsg = { role: 'assistant', content: '' }
  messages.value.push(aiMsg)
  streaming.value = true
  scrollBottom()
  const body = {
    bot_id: activeBotId.value,
    question: q,
    scope: {
      child_id: scope.value.child_id || null,
      exam_id: scope.value.exam_id || null,
      subject_id: scope.value.subject_id || null,
      date_from: dateRange.value?.[0] || '',
      date_to: dateRange.value?.[1] || '',
    },
  }
  try {
    await aiChatStream(body, (delta) => {
      aiMsg.content += delta
      scrollBottom()
    })
  } catch (e) {
    errorText.value = e.message || '请求失败'
    if (!aiMsg.content) messages.value.pop()
  } finally {
    streaming.value = false
    scrollBottom()
  }
}

function close() {
  visible.value = false
}

import { api } from '../api'
defineExpose({ open })
</script>

<style scoped>
.ai-fab {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 2000;
  width: 48px;
  height: 48px;
  box-shadow: var(--el-box-shadow-light);
}
.ai-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.25);
  z-index: 2000;
}
.ai-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: min(440px, 100vw);
  height: 100vh;
  background: var(--el-bg-color);
  border-left: 1px solid var(--el-border-color-light);
  z-index: 2001;
  display: flex;
  flex-direction: column;
}
.ai-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-light);
}
.ai-head-ops {
  display: flex;
}
.ai-scope {
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-light);
  background: var(--el-fill-color-lighter);
}
.ai-scope-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.ai-scope-row:last-child {
  margin-bottom: 0;
}
.ai-scope-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  width: 28px;
  flex-shrink: 0;
}
.ai-focus {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-color-primary);
}
.ai-msgs {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}
.ai-empty {
  text-align: center;
  color: var(--el-text-color-secondary);
  padding-top: 40px;
}
.ai-msg {
  display: flex;
  margin-bottom: 10px;
}
.ai-msg.user {
  justify-content: flex-end;
}
.ai-bubble {
  max-width: 86%;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 13px;
  line-height: 1.6;
  background: var(--el-fill-color);
}
.ai-msg.user .ai-bubble {
  background: var(--el-color-primary-light-8);
}
.ai-text {
  white-space: pre-wrap;
  word-break: break-word;
}
.ai-text.md {
  white-space: normal;
}
.ai-text.md :deep(.md-h) {
  font-weight: bold;
  margin: 4px 0 2px;
}
.ai-text.md :deep(ul),
.ai-text.md :deep(ol) {
  margin: 4px 0;
  padding-left: 18px;
}
.ai-text.md :deep(li) {
  margin: 2px 0;
}
.ai-text.md :deep(code) {
  background: var(--el-fill-color-dark);
  border-radius: 3px;
  padding: 0 4px;
  font-size: 12px;
}
.ai-thinking {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.ai-thinking .dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--el-color-primary);
  animation: ai-blink 1.2s infinite ease-in-out;
}
.ai-thinking .dot:nth-child(2) {
  animation-delay: 0.2s;
}
.ai-thinking .dot:nth-child(3) {
  animation-delay: 0.4s;
}
@keyframes ai-blink {
  0%,
  80%,
  100% {
    opacity: 0.25;
  }
  40% {
    opacity: 1;
  }
}
.ai-comment-card {
  margin: 8px 0 4px;
  border: 1px solid var(--el-color-primary-light-5);
  border-radius: 6px;
  padding: 8px;
  background: var(--el-color-primary-light-9);
}
.ai-comment-title {
  font-size: 12px;
  font-weight: bold;
  color: var(--el-color-primary);
  margin-bottom: 4px;
}
.ai-comment-body {
  margin-bottom: 6px;
}
.ai-error {
  color: var(--el-color-danger);
  font-size: 12px;
  padding: 6px 0;
}
.ai-input {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid var(--el-border-color-light);
  align-items: flex-end;
}
</style>
