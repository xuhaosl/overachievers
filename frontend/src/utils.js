export const gradeLabel = (n) => (n ? `${n}年级` : '')

// 成绩显示："85（10）/110"，无附加分时 "85/100"
export function scoreDisplay(score) {
  const base = `${score.regular_score}${
    score.bonus_score != null ? `（${score.bonus_score}）` : ''
  }`
  return `${base}/${score.total}`
}

export const ratePercent = (rate) =>
  rate != null ? `${Math.round(rate * 1000) / 10}%` : '-'

export const examTypes = ['单元测试', '期中测试', '模拟测验', '期末考试', '其它测试']

// 学期推断：8月起归入新学年上学期，1~7月归上一学年下学期（与后端规则一致）
export function inferTerm(dateStr) {
  if (!dateStr) return ''
  const y = Number(dateStr.slice(0, 4))
  const m = Number(dateStr.slice(5, 7))
  return m >= 8 ? `${y}-${y + 1} 上学期` : `${y - 1}-${y} 下学期`
}

// 成绩的显示标签："85（10）" 或 "85"
export function earnedLabel(s) {
  return s.bonus_score != null ? `${s.regular_score}（${s.bonus_score}）` : `${s.regular_score}`
}
