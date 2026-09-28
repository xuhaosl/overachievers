import { reactive } from 'vue'

export const store = reactive({
  childId: Number(localStorage.getItem('sa_child')) || null,
  children: [],
})

export function setChild(id) {
  store.childId = id
  if (id) localStorage.setItem('sa_child', String(id))
  else localStorage.removeItem('sa_child')
}
