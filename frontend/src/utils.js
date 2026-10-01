export const gradeLabel = (n) => (n ? `${n}年级` : '')

// 按记录日期推算当时读的年级（8月起算新学年）；无入学年份返回 null
export function gradeAtDate(enrollYear, dateStr) {
  if (!enrollYear || !dateStr) return null
  const y = Number(dateStr.slice(0, 4))
  const start = Number(dateStr.slice(5, 7)) >= 8 ? y : y - 1
  return Math.min(9, Math.max(1, start - Number(enrollYear) + 1))
}

// ---------- 班级（就读经历）推算 ----------
export const STAGE_YEARS = { 小学: 6, 初中: 3, 高中: 3 }

// 毕业年份 = 该阶段入学年份 + 学制
export function classGraduateYear(stage, enrollYear) {
  if (!enrollYear) return null
  return Number(enrollYear) + (STAGE_YEARS[stage] || 6)
}

export function todayStr() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// 班级记录在 dateStr 时推算的年级；无效（未入学/已毕业/无入学年份）返回 null
export function classGradeAt(rec, dateStr) {
  const g = gradeAtDate(rec.enroll_year, dateStr)
  if (g == null) return null
  return g >= 1 && g <= (STAGE_YEARS[rec.stage] || 6) ? g : null
}

// 在孩子的班级记录中找 dateStr 时在读的班级（优先入学年份大的）
export function pickClassAt(classes, childId, dateStr) {
  const recs = (classes || [])
    .filter((c) => c.child_id === childId && c.enroll_year)
    .sort((a, b) => (b.enroll_year || 0) - (a.enroll_year || 0))
  for (const r of recs) {
    const g = classGradeAt(r, dateStr)
    if (g != null) return { rec: r, grade: g }
  }
  return null
}

// 孩子的"当前班级"：今天在读的；全部已毕业时取最新一条做历史展示
export function currentClassRec(classes, childId) {
  const recs = (classes || [])
    .filter((c) => c.child_id === childId)
    .sort((a, b) => (b.enroll_year || 0) - (a.enroll_year || 0))
  return recs.find((r) => classGradeAt(r, todayStr()) != null) || recs[0] || null
}

// 成绩显示："得分（附加分）/总分"，无附加分时 "得分/总分"
export function scoreDisplay(score) {
  const base = `${score.regular_score}${
    score.bonus_score != null ? `（${score.bonus_score}）` : ''
  }`
  return `${base}/${score.total}`
}

export const ratePercent = (rate) =>
  rate != null ? `${Math.round(rate * 1000) / 10}%` : '-'

// 名次值取数字：3 → 3，"前5" → 5，无数字返回 null（曲线画点用）
export function rankNum(v) {
  if (v == null || v === '') return null
  if (typeof v === 'number') return v
  const m = String(v).match(/\d+(?:\.\d+)?/)
  return m ? Number(m[0]) : null
}

// 名次显示：数字 → "第 x 名"，文字（如"前5"）→ 原样，空 → 占位符
export function rankText(v, placeholder = '—') {
  if (v == null || v === '') return placeholder
  return /^\d+(\.\d+)?$/.test(String(v)) ? `第 ${v} 名` : String(v)
}

export const examTypes = ['单元测试', '期中考试', '期末考试']

// 学期推断：第一学期=8月~次年1月，第二学期=2月~7月（与后端规则一致）
export function inferTerm(dateStr) {
  if (!dateStr) return ''
  const y = Number(dateStr.slice(0, 4))
  const m = Number(dateStr.slice(5, 7))
  if (m >= 8) return `${y}-${y + 1} 第1学期`
  if (m <= 1) return `${y - 1}-${y} 第1学期`
  return `${y - 1}-${y} 第2学期`
}

// 成绩的显示标签："得分（附加分）" 或 "得分"
export function earnedLabel(s) {
  return s.bonus_score != null ? `${s.regular_score}（${s.bonus_score}）` : `${s.regular_score}`
}

// "98（5）/100（10）"：括号里有附加分时才显示
export function fullScore(regular, bonus, total, bonusTotal) {
  const left = bonus ? `${regular}（${bonus}）` : `${regular}`
  const right = bonusTotal ? `${total}（${bonusTotal}）` : `${total}`
  return `${left} / ${right}`
}

// "2026-2027 第1学期" → "第1学期"（兼容旧数据"上学期/第一学期"）
export function shortTerm(term) {
  if (!term) return ''
  const t = term.replace('上学期', '第1学期').replace('下学期', '第2学期').replace('第一学期', '第1学期').replace('第二学期', '第2学期')
  return t.split(/\s+/).pop()
}
