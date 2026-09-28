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
