import axios from 'axios'

export const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use((cfg) => {
  const token = localStorage.getItem('sa_token')
  if (token) cfg.headers['X-Auth-Token'] = token
  return cfg
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('sa_token')
      if (!location.hash.startsWith('#/login')) location.hash = '#/login'
    }
    return Promise.reject(err)
  },
)

export const errMsg = (e) => e?.response?.data?.detail || e?.message || '操作失败'

// 通用确认删除流程：第一次 DELETE 返回 409（带影响说明）时弹确认再删
export async function confirmDelete(url, hint) {
  try {
    await api.delete(url)
    return true
  } catch (e) {
    if (e?.response?.status === 409) {
      const msg = e.response.data.detail || hint
      await ElMessageBoxConfirm(msg)
      await api.delete(url, { params: { confirm: true } })
      return true
    }
    throw e
  }
}

import { ElMessageBox } from 'element-plus'

export function ElMessageBoxConfirm(message) {
  return ElMessageBox.confirm(message, '确认删除', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
}

// ---------- 智能助手 ----------
export const aiApi = {
  providers: () => api.get('/ai/providers'),
  bots: () => api.get('/ai/bots'),
  createBot: (data) => api.post('/ai/bots', data),
  updateBot: (id, data) => api.patch(`/ai/bots/${id}`, data),
  deleteBot: (id) => api.delete(`/ai/bots/${id}`),
  testBot: (data) => api.post('/ai/bots/test', data),
  conversations: (botId) => api.get(`/ai/bots/${botId}/conversations`),
  createConversation: (botId) => api.post(`/ai/bots/${botId}/conversations`),
  convMessages: (convId) => api.get(`/ai/conversations/${convId}/messages`),
  renameConversation: (convId, title) => api.patch(`/ai/conversations/${convId}`, { title }),
  deleteConversation: (convId) => api.delete(`/ai/conversations/${convId}`),
  messages: (botId) => api.get(`/ai/bots/${botId}/messages`),
  clearMessages: (botId) => api.delete(`/ai/bots/${botId}/messages`),
  setScoreComment: (scoreId, content) => api.patch(`/scores/${scoreId}/ai-comment`, { content }),
  setExamComment: (examId, content) => api.patch(`/exams/${examId}/ai-comment`, { content }),
}

// 流式对话：POST /ai/chat，逐段回调 assistant 增量文本；ai_error 事件抛错
export async function aiChatStream(body, onDelta) {
  const res = await fetch('/api/ai/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(localStorage.getItem('sa_token') ? { 'X-Auth-Token': localStorage.getItem('sa_token') } : {}),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail || detail
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  let doneReading = false
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    if (doneReading) continue // [DONE] 后只排空流，等后端保存完毕
    buf += dec.decode(value, { stream: true })
    let idx
    while ((idx = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, idx).trim()
      buf = buf.slice(idx + 1)
      if (!line.startsWith('data:')) continue
      const data = line.slice(5).trim()
      if (data === '[DONE]') {
        // 不立即返回：继续读到流真正关闭，确保后端已把消息/会话标题保存完
        doneReading = true
        break
      }
      try {
        const obj = JSON.parse(data)
        if (obj.ai_error) throw new Error(obj.ai_error)
        const delta = obj.choices?.[0]?.delta?.content
        if (delta) onDelta(delta)
      } catch (e) {
        if (e instanceof SyntaxError) continue // 半截 JSON，忽略
        throw e
      }
    }
  }
}
