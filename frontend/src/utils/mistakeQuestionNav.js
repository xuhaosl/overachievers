/**
 * 错题整理「AI 识别」逐题编辑的导航与表单映射。
 * 抽成纯函数，便于对题号下拉切换做单元测试。
 */

/** 题号归一化：第2题、(3)、2. 都转成 2，用于查重和补识别。 */
export function normalizeNo(text) {
  return String(text || '').replace(/[第题()（）\s.、]/g, '')
}

/** 题号的排序值：数字题号按数值排，非数字或无题号排到最后。 */
export function questionNoValue(no) {
  const n = normalizeNo(no)
  const match = n.match(/\d+/)
  return match ? Number(match[0]) : Number.POSITIVE_INFINITY
}

/** 按题号升序排列待处理题目，题号相同的保持原顺序。 */
export function sortQuestionsByNo(items = []) {
  return items
    .map((q, i) => ({ q, i }))
    .sort((a, b) => {
      const av = questionNoValue(a.q?.no)
      const bv = questionNoValue(b.q?.no)
      if (av === bv) return a.i - b.i
      return av - bv
    })
    .map((x) => x.q)
}

/** 题号下拉项的文字：优先显示识别到的原小题号，没有题号时用序号。 */
export function questionOptionLabel(q, index) {
  const item = q || {}
  const label = item.no ? `第 ${item.no} 题` : `第 ${index + 1} 道`
  return item.done ? `${label}（已处理）` : label
}

/** 找出与当前小题属于同一大题的所有待处理小题：group_no 或 group_stem 任一相同即归组。 */
export function groupSiblings(items = [], index = 0) {
  const cur = items[index]
  if (!cur) return []
  const parent = items.map((_, i) => i)
  function find(i) {
    return parent[i] === i ? i : (parent[i] = find(parent[i]))
  }
  function union(a, b) {
    parent[find(a)] = find(b)
  }
  const byNo = new Map()
  const byStem = new Map()
  items.forEach((q, i) => {
    const no = normalizeNo(q?.group_no)
    const stem = normalizeNo(q?.group_stem)
    if (no && byNo.has(no)) union(i, byNo.get(no))
    else if (no) byNo.set(no, i)
    if (stem && byStem.has(stem)) union(i, byStem.get(stem))
    else if (stem) byStem.set(stem, i)
  })
  const root = find(index)
  return items.filter((_, i) => find(i) === root)
}

/** 手动补题时，把没有分组信息的题目并入最接近的已有大题。 */
export function attachToNearestGroup(q, items = []) {
  if (!q) return q
  if (q.group_no || q.group_stem) {
    const linked = groupSiblings([...items, q], items.length).length > 1
    if (linked) return q
  }
  const groups = []
  const used = new Set()
  items.forEach((it, i) => {
    if (used.has(i)) return
    if (!normalizeNo(it.group_no) && !normalizeNo(it.group_stem)) return
    const siblings = groupSiblings(items, i)
    siblings.forEach((s) => {
      const idx = items.indexOf(s)
      if (idx >= 0) used.add(idx)
    })
    groups.push(siblings)
  })
  if (!groups.length) return q
  let target = groups[0]
  if (groups.length > 1) {
    const qv = questionNoValue(q.no)
    let best = Number.POSITIVE_INFINITY
    if (Number.isFinite(qv)) {
      for (const group of groups) {
        const values = group
          .map((m) => questionNoValue(m.no))
          .filter((v) => Number.isFinite(v))
        if (!values.length) continue
        const distance = Math.min(...values.map((v) => Math.abs(v - qv)))
        if (distance < best) {
          best = distance
          target = group
        }
      }
    }
  }
  const rep = target.find((m) => m.group_no) || target[0] || {}
  q.group_no = rep.group_no || ''
  q.group_stem = rep.group_stem || ''
  q.group_title = rep.group_title || ''
  return q
}

function memberLabel(q, index) {
  const no = String(q?.no || '').trim().replace(/[（）()]/g, '')
  return `（${no || index + 1}）`
}

/**
 * 把同一大题下的多个错题合并成一条保存内容。
 * 独立题（无 group_no 且只有自己）返回 null，沿用单题保存。
 */
export function buildGroupAggregate(items = [], index = 0) {
  const cur = items[index]
  if (!cur) return null
  const members = groupSiblings(items, index)
  const groupNo = String(
    cur.group_no || members.map((q) => q.group_no).find(Boolean) || '',
  ).trim()
  if (!groupNo && members.length <= 1) return null
  const groupStem = members.map((q) => String(q.group_stem || '').trim()).find(Boolean) || ''
  const groupTitle =
    members.map((q) => String(q.group_title || '').trim()).find(Boolean) ||
    String(cur.title || '').trim()
  const lines = (field) =>
    members
      .map((q, i) => {
        const value = String(q[field] || '').trim()
        return value ? `${memberLabel(q, i)}${value}` : ''
      })
      .filter(Boolean)
      .join('\n')
  const stem = [
    groupStem,
    ...members.map((q, i) => `${memberLabel(q, i)}${String(q.stem || '').trim()}`),
  ]
    .filter(Boolean)
    .join('\n\n')
  const knowledge = []
  for (const q of members) {
    for (const tag of q.knowledge || []) {
      if (tag && !knowledge.includes(tag)) knowledge.push(tag)
    }
  }
  return {
    question_no: (groupNo || members.map((q) => String(q.no || '').trim()).filter(Boolean).join('、')).slice(0, 20),
    title: groupTitle.slice(0, 120),
    stem,
    my_answer: lines('my_answer'),
    correct_answer: lines('correct_answer'),
    explanation: lines('explanation'),
    reason: lines('reason'),
    knowledge,
    figure_filename: members.map((q) => q.figure_filename).find(Boolean) || null,
  }
}

/** 生成题号下拉选项，value 为 items 中的下标。 */
export function buildQuestionOptions(items = []) {
  return items.map((q, index) => ({
    value: index,
    label: questionOptionLabel(q, index),
  }))
}

/** 把识别结果中的某一道题映射成编辑表单；setIds 为默认错题集。 */
export function buildQuestionForm(q = {}, setIds = []) {
  const item = q || {}
  return {
    no: item.no || '',
    title: item.title || '',
    stem: item.stem || '',
    my_answer: item.my_answer || '',
    correct_answer: item.correct_answer || '',
    explanation: item.explanation || '',
    reason: item.reason || '',
    knowledge_tags: (item.knowledge || []).join('、'),
    unit_ids: item.unit_ids || [],
    set_ids: (setIds || []).slice(),
  }
}

/**
 * 有批改痕迹时只保留判错的小题。
 * 返回 null 表示模型没有逐题标注对错，需要用户手动勾选。
 */
export function selectWrongQuestions(items = [], hasMarks = false) {
  if (!hasMarks) return items
  const flagged = items.some((q) => typeof q?.is_wrong === 'boolean')
  if (!flagged) return null
  return items.filter((q) => q.is_wrong === true)
}
