/**
 * 错题整理「AI 识别」逐题编辑的导航与表单映射。
 * 抽成纯函数，便于对题号下拉切换做单元测试。
 */

/** 题号归一化：第2题、(3)、2. 都转成 2，用于查重和补识别。 */
export function normalizeNo(text) {
  return String(text || '').replace(/[第题()（）\s.、]/g, '')
}

/** 题号下拉项的文字：优先显示识别到的原小题号，没有题号时用序号。 */
export function questionOptionLabel(q, index) {
  const item = q || {}
  const label = item.no ? `第 ${item.no} 题` : `第 ${index + 1} 道`
  return item.done ? `${label}（已处理）` : label
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
