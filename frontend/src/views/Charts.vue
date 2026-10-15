<template>
  <div>
    <!-- 筛选栏 -->
    <div class="page-head">
      <h3>{{ pageTitle }}</h3>
    </div>

    <el-form inline class="filter">
      <el-form-item label="孩子">
        <el-select v-model="childId" style="width: 120px" @change="onChildChange">
          <el-option v-for="c in store.children" :key="c.id" :value="c.id" :label="c.name" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="chartType !== 'term'" label="时间">
        <el-radio-group v-model="rangeType" @change="loadData">
          <el-radio-button value="term">本学期</el-radio-button>
          <el-radio-button value="year">本学年</el-radio-button>
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="custom">自定义</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="chartType !== 'term' && rangeType === 'custom'" label="">
        <el-date-picker
          v-model="customRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          start-placeholder="开始"
          end-placeholder="结束"
          @change="loadData"
          style="width: 240px"
        />
      </el-form-item>
      <el-form-item v-if="chartType === 'term'" label="学期">
        <el-select v-model="rankTerm" style="width: 140px" @change="renderTermRank">
          <el-option v-for="t in termOptions" :key="t.value" :value="t.value" :label="t.label" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button @click="exportView">导出数据</el-button>
      </el-form-item>
    </el-form>

    <el-empty v-if="!childId" description="请先选择孩子" />
    <!-- 学期排名子页：只显示学期排名柱状图 -->
    <template v-else-if="chartType === 'term'">
      <div class="chart-head" style="margin-bottom: 8px">
        <!-- 学科点选控件：与其它曲线一致，点击切换显示/隐藏 -->
        <div class="legend-line">
          <span
            v-for="it in termLegend"
            :key="it.name"
            class="lg"
            :class="{ off: termHide.has(it.name) }"
            @click="toggleTerm(it.name)"
          >
            <i :style="{ background: it.color }"></i>{{ it.name }}
          </span>
        </div>
      </div>
      <el-card shadow="never">
        <el-empty v-if="termRankEmpty" description="该学期暂无成绩记录" :image-size="60" />
        <div v-show="!termRankEmpty" ref="termRankChartEl" class="chart"></div>
      </el-card>
    </template>
    <template v-else>
      <el-empty v-if="empty" :description="emptyText" />
      <template v-else>
      <div class="chart-head">
        <h3>得分曲线</h3>
        <!-- 曲线点选控件：标题右侧，点击切换显示/隐藏 -->
        <div class="legend-line">
          <span
            v-for="it in scoreLegend"
            :key="it.name"
            class="lg"
            :class="{ off: scoreHide.has(it.name) }"
            @click="toggleScore(it.name)"
          >
            <i :style="{ background: it.color }"></i>{{ it.name }}
          </span>
        </div>
      </div>
      <el-card shadow="never">
        <div ref="scoreChartEl" class="chart"></div>
      </el-card>
      <div class="chart-head rank-title">
        <h3>排名曲线</h3>
        <div class="legend-line">
          <span
            v-for="it in rankLegend"
            :key="it.name"
            class="lg"
            :class="{ off: rankHide.has(it.name) }"
            @click="toggleRank(it.name)"
          >
            <i :style="{ background: it.color }"></i>{{ it.name }}
          </span>
        </div>
      </div>
      <el-card shadow="never">
        <div ref="rankChartEl" class="chart"></div>
      </el-card>
      </template>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api'
import { store, setChild } from '../store'
import { gradeLabel, inferTerm, ratePercent, rankNum, rankText } from '../utils'

const route = useRoute()
const childId = ref(store.childId)
const rangeType = ref('all')
const customRange = ref(null)
const chartType = ref(route.query.type || 'single')
// 曲线排名只用班级排名（年级排名按学年统计，逻辑待定）
const rankMode = ref('class')
const subjects = ref([])
const allScores = ref([])
const allExams = ref([])

const scoreChartEl = ref(null)
const rankChartEl = ref(null)
let scoreChart = null
let rankChart = null
const empty = ref(false)

const emptyText = computed(() => {
  if (rangeType.value === 'term') return '本学期暂无数据，试试切换时间范围'
  if (rangeType.value === 'year') return '本学年暂无数据，试试切换时间范围'
  return '暂无成绩数据，先去「成绩列表 → 新建成绩」录入一些成绩吧'
})

// ---------- 时间过滤 ----------
function currentTerm() {
  return inferTerm(new Date().toISOString().slice(0, 10))
}
function inDateRange(dateStr) {
  if (rangeType.value === 'all') return true
  if (rangeType.value === 'term') return dateStr.slice(0, 4) === '' ? true : sameTerm(dateStr)
  if (rangeType.value === 'year') return sameSchoolYear(dateStr)
  if (rangeType.value === 'custom') {
    if (!customRange.value) return true
    return dateStr >= customRange.value[0] && dateStr <= customRange.value[1]
  }
  return true
}
// 学期匹配（1月属于上一学年第二学期，所以直接比日期区间更可靠）
function termRangeOf(term) {
  // "2026-2027 第1学期" -> 2026-08-01 ~ 2027-01-31；第2学期 -> 2027-02-01 ~ 2027-07-31（兼容旧的"第一/第二学期"）
  const [a, b] = term.split(' ')[0].split('-').map(Number)
  if (/第(一|1)学期/.test(term)) return [`${a}-08-01`, `${b}-01-31`]
  return [`${b}-02-01`, `${b}-07-31`]
}
function sameTerm(dateStr) {
  const t = currentTerm()
  const [from, to] = termRangeOf(t)
  return dateStr >= from && dateStr <= to
}
function sameSchoolYear(dateStr) {
  const t = currentTerm()
  const [a, b] = t.split(' ')[0].split('-').map(Number)
  return dateStr >= `${a}-08-01` && dateStr <= `${b}-07-31`
}

// ---------- 数据加载 ----------
async function loadData() {
  if (!childId.value) return
  try {
    const [s, e, cls] = await Promise.all([
      api.get('/scores', { params: { child_id: childId.value } }),
      api.get('/exams', { params: { child_id: childId.value } }),
      api.get('/classes'),
    ])
    rawScores.value = s.data
    childClasses.value = cls.data.filter((c) => c.child_id === childId.value)
    allScores.value = s.data.filter((x) => inDateRange(x.date))
    allExams.value = e.data.filter((x) => inDateRange(x.date)).reverse() // 时间正序
    // 当前学期失效（切换孩子）时重置为最近学期
    const opts = termOptions.value
    if (!opts.some((t) => t.value === rankTerm.value)) {
      rankTerm.value = opts.length ? opts[opts.length - 1].value : ''
    }
    render()
  } catch (err) {
    ElMessage.error(errMsg(err))
  }
}

// 菜单切换「单元测验/期中期末/学期排名」子项时组件被复用，跟随 query 更新并重绘
watch(
  () => route.query.type,
  (v) => {
    chartType.value = v || 'single'
    // 切到/切出学期排名视图会重建图表 DOM，等 DOM 更新后再绘制
    nextTick(() => render())
  },
)

// 页头标题
const pageTitle = computed(
  () =>
    ({
      single: '单元测验',
      total: '期中期末',
      term: '学期排名',
    })[chartType.value] || '成长曲线',
)

// ---------- 绘图 ----------
function showChart() {
  empty.value = false
  // v-else 切换后 DOM 会重建，实例指向旧节点时需重建；首帧隐藏态尺寸交给 nextTick 修正
  if (!scoreChart || scoreChart.getDom() !== scoreChartEl.value) {
    scoreChart?.dispose()
    scoreChart = echarts.init(scoreChartEl.value)
  }
  if (!rankChart || rankChart.getDom() !== rankChartEl.value) {
    rankChart?.dispose()
    rankChart = echarts.init(rankChartEl.value)
  }
  nextTick(() => {
    scoreChart?.resize()
    rankChart?.resize()
  })
}
function setEmpty() {
  empty.value = true
  scoreChart?.clear()
  rankChart?.clear()
}

function render() {
  if (!childId.value) return setEmpty()
  // 学期排名视图：只绘制学期排名柱状图
  if (chartType.value === 'term') return renderTermRank()
  // 每个曲线视图对应一组成绩类型；期中期末页额外叠加场次总分/总排名线
  const typeMap = {
    single: ['单元测试'],
    total: ['期中考试', '期末考试'],
  }
  return renderSingle(typeMap[chartType.value] || [], chartType.value === 'total')
}

// 横坐标类目 → 日期映射：tooltip 按 label 反查原始数据
let scoreDateMap = {}

// 曲线点选控件（标题右侧）：图例列表与隐藏集合，点击切换后重绘
const scoreLegend = ref([])
const rankLegend = ref([])
const scoreHide = ref(new Set())
const rankHide = ref(new Set())
function toggleScore(name) {
  const next = new Set(scoreHide.value)
  next.has(name) ? next.delete(name) : next.add(name)
  scoreHide.value = next
  render()
}
function toggleRank(name) {
  const next = new Set(rankHide.value)
  next.has(name) ? next.delete(name) : next.add(name)
  rankHide.value = next
  render()
}

// 得分图骨架：横轴为单元/场次简写，纵轴 80 ~ 满分+5
function scoreOption(series, catLabels, maxTotal = 0) {
  return {
    tooltip: { trigger: 'item', formatter: scoreTooltip },
    grid: { left: 30, right: 15, top: 18, bottom: 26 },
    xAxis: { type: 'category', data: catLabels, axisLabel: { interval: 0, fontSize: 11 } },
    yAxis: { type: 'value', min: 80, max: (maxTotal || 100) + 5, name: '得分', nameLocation: 'start', nameGap: 16 },
    series,
  }
}

// 排名图骨架：横轴为单元/场次简写，纵轴固定 20~1（反转，越小越高）
function rankOption(series, catLabels) {
  return {
    tooltip: { trigger: 'item', formatter: rankTooltip },
    grid: { left: 30, right: 15, top: 18, bottom: 26 },
    xAxis: { type: 'category', data: catLabels, axisLabel: { interval: 0, fontSize: 11 } },
    yAxis: {
      type: 'value',
      inverse: true,
      min: 1,
      max: 20,
      minInterval: 1,
      name: rankMode.value === 'grade' ? '年级名次' : '班级名次',
    },
    series,
  }
}

// 得分图悬浮提示：含得分率与名次参考
function scoreTooltip(p) {
  if (p.seriesName === '总分') {
    const e = allExams.value.find((x) => x.date === scoreDateMap[p.value[0]])
    return `总分<br/>${p.value[0]}<br/>得分 <b>${p.value[1]}</b>${e && e.total_sum ? ` / ${e.total_sum}` : ''}`
  }
  const s = subjects.value.find((x) => x.name === p.seriesName)
  const date = scoreDateMap[p.value[0]]
  const row = allScores.value.find((x) => s && x.subject_id === s.id && x.date === date)
  if (!row) return `${p.seriesName}<br/>${p.value[0]}<br/>${p.value[1]}`
  const ranks =
    row.grade_rank != null || row.class_rank != null
      ? `<br/>${[rankText(row.grade_rank, ''), rankText(row.class_rank, '')].filter(Boolean).join(' · ')}`
      : ''
  return `${p.seriesName}<br/>${p.value[0]}（${row.type}）<br/>得分 <b>${row.regular_score}${row.bonus_score != null ? `（${row.bonus_score}）` : ''}</b> / ${row.total}<br/>得分率 <b>${ratePercent(row.rate)}</b>${ranks}`
}

// 排名图悬浮提示：系列名（学科/总分/班级排名/年级排名）+ 名次数字
function rankTooltip(p) {
  return `${p.seriesName}<br/>${p.value[0]}<br/>第 <b>${p.value[1]}</b> 名`
}

// 图表横轴类目短标签：期中期末视图"N上末"；单元测验视图"N上N"（短学期名+单元序号），无单元显示"？"
function catLabel(row, isTotal) {
  if (isTotal) return `${row.term_short || ''}末`
  const nos = [...(row.unit_names || '').matchAll(/第(\d+)单元/g)].map((m) => m[1])
  return `${row.term_short || ''}${nos.join('') || '?'}`
}

// 单科图：上图得分（实线）、下图排名（虚线）。
// 横坐标为简写类目：单科"N上N"（短学期名+单元序号）、场次"N下末"（短学期名+末），按时间排列；
// 各视图按类型过滤；期中期末页（withTotal）叠加场次总分/总排名线
function renderSingle(typeFilters, withTotal = false) {
  const picked = subjects.value
  const rankKey = rankMode.value === 'grade' ? 'grade_rank' : 'class_rank'

  // 得分图纵坐标量程：80 ~ 满分+5（单科 total / 场次 total_sum 的最大值），无数据时 80~105
  const inView = allScores.value.filter((x) => typeFilters.includes(x.type) && picked.some((s) => s.id === x.subject_id))
  let maxTotal = Math.max(0, ...inView.map((x) => x.total || 0))
  if (withTotal)
    maxTotal = Math.max(maxTotal, ...allExams.value.filter((x) => typeFilters.includes(x.type)).map((x) => x.total_sum || 0))

  // 简写标签：期中期末视图里，单科成绩与场次同口径（"N上末"），同学期归入同一类目
  const isTotalView = typeFilters.includes('期中考试') || typeFilters.includes('期末考试')
  const unitLabel = (row) => catLabel(row, isTotalView)
  const examLabel = (e) => catLabel(e, true)

  // 收集类目（label 去重，按日期排序）
  const cats = []
  const catDates = new Map()
  const addCat = (label, date) => {
    if (!catDates.has(label)) {
      catDates.set(label, date)
      cats.push({ label, date })
    }
  }

  const scoreSeries = []
  const rankSeries = []
  for (const s of picked) {
    const rows = allScores.value
      .filter((x) => x.subject_id === s.id && typeFilters.includes(x.type))
      .sort((a, b) => (a.date > b.date ? 1 : -1))
    const scorePts = rows.map((x) => {
      addCat(unitLabel(x), x.date)
      return [unitLabel(x), x.earned]
    })
    const rankPts = rows
      .filter((x) => rankNum(x[rankKey]) != null)
      .map((x) => {
        addCat(unitLabel(x), x.date)
        return [unitLabel(x), rankNum(x[rankKey])]
      })
    if (scorePts.length)
      scoreSeries.push({
        name: s.name,
        type: 'line',
        data: scorePts,
        connectNulls: false,
        color: s.color,
        label: { show: scorePts.length <= 12, position: 'top', fontSize: 10 },
      })
    if (rankPts.length)
      rankSeries.push({
        name: s.name,
        type: 'line',
        data: rankPts,
        connectNulls: false,
        color: s.color,
        lineStyle: { type: 'dashed' },
        label: { show: rankPts.length <= 15, position: 'bottom', fontSize: 10 },
      })
  }
  // 期中期末页：场次总分（上图实线）＋班级排名/年级排名（下图虚线）。
  // 年级排名按学年计算、上下学期相同，只取下学期（N下末）的场次
  if (withTotal) {
    const exams = allExams.value
      .filter((x) => typeFilters.includes(x.type))
      .sort((a, b) => (a.date > b.date ? 1 : -1))
    const scorePts = exams
      .filter((x) => x.total_sum > 0)
      .map((x) => {
        addCat(examLabel(x), x.date)
        return [examLabel(x), x.earned_sum]
      })
    const classPts = exams
      .filter((x) => rankNum(x.class_rank) != null)
      .map((x) => {
        addCat(examLabel(x), x.date)
        return [examLabel(x), rankNum(x.class_rank)]
      })
    const gradePts = exams
      .filter((x) => rankNum(x.year_rank) != null && (x.term_short || '').endsWith('下'))
      .map((x) => {
        addCat(examLabel(x), x.date)
        return [examLabel(x), rankNum(x.year_rank)]
      })
    if (scorePts.length)
      scoreSeries.push({
        name: '总分',
        type: 'line',
        data: scorePts,
        color: '#8B5CF6',
        label: { show: scorePts.length <= 12, position: 'top', fontSize: 10 },
      })
    if (classPts.length)
      rankSeries.push({
        name: '班级排名',
        type: 'line',
        data: classPts,
        color: '#8B5CF6',
        lineStyle: { type: 'dashed' },
        label: { show: classPts.length <= 15, position: 'bottom', fontSize: 10 },
      })
    if (gradePts.length)
      rankSeries.push({
        name: '年级排名',
        type: 'line',
        data: gradePts,
        color: '#E6A23C',
        lineStyle: { type: 'dashed' },
        label: { show: gradePts.length <= 15, position: 'bottom', fontSize: 10 },
      })
  }
  if (!scoreSeries.length && !rankSeries.length) return setEmpty()
  // 类目按时间排列
  cats.sort((a, b) => (a.date > b.date ? 1 : -1))
  const catLabels = cats.map((c) => c.label)
  scoreDateMap = Object.fromEntries(cats.map((c) => [c.label, c.date]))
  showChart()
  // 图例状态（点选控件在标题右侧）：隐藏的系列不渲染，点击图例重绘
  scoreLegend.value = scoreSeries.map((s) => ({ name: s.name, color: s.color }))
  rankLegend.value = rankSeries.map((s) => ({ name: s.name, color: s.color }))
  scoreChart.setOption(
    scoreOption(
      scoreSeries.filter((s) => !scoreHide.value.has(s.name)),
      catLabels,
      maxTotal,
    ),
    true,
  )
  rankChart.setOption(
    rankOption(
      rankSeries.filter((s) => !rankHide.value.has(s.name)),
      catLabels,
    ),
    true,
  )
}

// ---------- 学期排名：选定学期内各科「最高得分者」次数（孩子 vs 竞争对手） ----------
const rawScores = ref([]) // 该孩子全部成绩（不受顶部时间筛选影响）
const childClasses = ref([]) // 该孩子的班级（就读经历），用于推算对手名单
const rankTerm = ref('')
const termRankChartEl = ref(null)
let termRankChart = null
const termRankEmpty = ref(false)
// 学科点选控件（与其它曲线一致）：图例列表与隐藏集合，点击切换后重绘
const termLegend = ref([])
const termHide = ref(new Set())
function toggleTerm(name) {
  const next = new Set(termHide.value)
  next.has(name) ? next.delete(name) : next.add(name)
  termHide.value = next
  renderTermRank()
}
const STAGE_LEN = { 小学: 6, 初中: 3, 高中: 3 }

// 学期下拉选项：该孩子成绩中出现过的学期，按最早成绩日期排序，显示短名（四上）
const termOptions = computed(() => {
  const m = new Map() // term(长名) -> { min, short }
  for (const x of rawScores.value) {
    const cur = m.get(x.term)
    if (!cur) m.set(x.term, { min: x.date, short: x.term_short || '' })
    else {
      if (x.date < cur.min) cur.min = x.date
      if (!cur.short && x.term_short) cur.short = x.term_short
    }
  }
  return [...m.entries()]
    .sort((a, b) => (a[1].min > b[1].min ? 1 : -1))
    .map(([value, v]) => ({ value, label: v.short || value }))
})
// 当前学期失效（切换孩子）时重置为最近学期：loadData 里显式执行

// 竞争对手名单解析：JSON [{no, name}]，顿号/逗号分隔字符串兜底
function parseRivals(str) {
  if (!str) return []
  try {
    const arr = JSON.parse(str)
    if (Array.isArray(arr)) return arr.map((r) => r.name).filter(Boolean)
  } catch {
    /* 顿号分隔兜底 */
  }
  return str.split(/[、,，]/).map((s) => s.trim()).filter(Boolean)
}

// 按成绩日期推算当时就读的班级（与后端 resolve_stage_grade 同逻辑）
function classAtDate(dateStr) {
  const year = +dateStr.slice(0, 4)
  const startYear = +dateStr.slice(5, 7) >= 8 ? year : year - 1 // 8月起算新学年
  for (const c of childClasses.value) {
    const n = STAGE_LEN[c.stage]
    if (!n || !c.enroll_year) continue
    const g = startYear - c.enroll_year + 1
    if (g >= 1 && g <= n) return c
  }
  return null
}

// 悬浮提示：某人各科次数与合计
function termRankTooltip(params) {
  const arr = Array.isArray(params) ? params : [params]
  if (!arr.length) return ''
  const total = arr.reduce((s, p) => s + (p.value || 0), 0)
  const lines = arr.filter((p) => p.value > 0).map((p) => `${p.marker}${p.seriesName} <b>${p.value}</b> 次`)
  return `${arr[0].axisValue}：合计 <b>${total}</b> 次${lines.length ? '<br/>' + lines.join('<br/>') : ''}`
}

// 学期排名数据计算（绘图与导出共用）：该学期成绩 → 人员/各人各科次数/学科顺序与颜色
function termRankData() {
  const rows = rawScores.value.filter((x) => x.term === rankTerm.value)
  if (!rows.length) return null
  // 横轴人员：孩子 + 按成绩日期推算班级的全部竞争对手（含 0 次）
  const child = store.children.find((c) => c.id === childId.value)
  const people = child ? [child.name] : []
  const seen = new Set(people)
  const allRivals = [...new Set(childClasses.value.flatMap((c) => parseRivals(c.rivals)))] // 无班级命中时兜底
  for (const x of rows) {
    const cls = classAtDate(x.date)
    for (const n of cls ? parseRivals(cls.rivals) : allRivals) {
      if (!seen.has(n)) {
        seen.add(n)
        people.push(n)
      }
    }
  }
  // 计数：每条成绩的「最高得分者」（可能并列多人）按学科累加
  const counts = new Map(people.map((p) => [p, new Map()]))
  const subjColor = new Map()
  const subjOrder = []
  for (const x of rows) {
    if (!x.high_scorer) continue
    for (const name of x.high_scorer.split('、')) {
      if (!name || !counts.has(name)) continue
      const m = counts.get(name)
      m.set(x.subject_name, (m.get(x.subject_name) || 0) + 1)
      if (!subjColor.has(x.subject_name)) {
        subjColor.set(x.subject_name, x.subject_color)
        subjOrder.push(x.subject_name)
      }
    }
  }
  // 学科系列按学科管理列表顺序排列，不在列表的排后面
  const order = new Map(subjects.value.map((s, i) => [s.name, i]))
  subjOrder.sort((a, b) => (order.get(a) ?? 999) - (order.get(b) ?? 999))
  return { people, counts, subjColor, subjOrder }
}

function renderTermRank() {
  if (!termRankChartEl.value) return
  const rows = rawScores.value.filter((x) => x.term === rankTerm.value)
  if (!rows.length) {
    termRankEmpty.value = true
    termLegend.value = []
    termRankChart?.clear()
    return
  }
  termRankEmpty.value = false
  const { people, counts, subjColor, subjOrder } = termRankData()
  termLegend.value = subjOrder.map((name) => ({ name, color: subjColor.get(name) }))
  showTermRankChart()
  termRankChart.setOption(
    {
      tooltip: { trigger: 'axis', formatter: termRankTooltip },
      grid: { left: 30, right: 15, top: 18, bottom: 26 },
      xAxis: { type: 'category', data: people, axisLabel: { interval: 0, fontSize: 11 } },
      yAxis: { type: 'value', minInterval: 1, name: '次数', nameLocation: 'start', nameGap: 16 },
      // 同一人的各科柱子靠在一起（barGap 0），人与人之间留间隔
      series: subjOrder
        .filter((name) => !termHide.value.has(name))
        .map((name) => ({
          name,
          type: 'bar',
          barMaxWidth: 26,
          barGap: '0%',
          barCategoryGap: '40%',
          color: subjColor.get(name),
          label: { show: true, position: 'inside', fontSize: 10, formatter: (p) => (p.value > 0 ? p.value : '') },
          data: people.map((p) => counts.get(p).get(name) || 0),
        })),
    },
    true,
  )
}

// 空态切换后 DOM 会重建，实例指向旧节点时需重建
function showTermRankChart() {
  if (!termRankChart || termRankChart.getDom() !== termRankChartEl.value) {
    termRankChart?.dispose()
    termRankChart = echarts.init(termRankChartEl.value)
  }
  nextTick(() => termRankChart?.resize())
}

// ---------- 导出数据：当前板块图表数据导出为 Excel（xlsx 按需加载，不进主包） ----------
async function exportXlsx(filename, sheets) {
  const XLSX = await import('xlsx')
  const wb = XLSX.utils.book_new()
  for (const { title, rows } of sheets) {
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(rows), title)
  }
  XLSX.writeFile(wb, filename)
}

function exportView() {
  if (chartType.value === 'term') return exportTermRank()
  const typeMap = {
    single: ['单元测试'],
    total: ['期中考试', '期末考试'],
  }
  const types = typeMap[chartType.value] || []
  const pickedIds = new Set(subjects.value.map((s) => s.id))
  const isTotal = chartType.value === 'total'
  const scoreRows = allScores.value
    .filter((x) => types.includes(x.type) && pickedIds.has(x.subject_id))
    .map((x) => ({
      学科: x.subject_name,
      类目: catLabel(x, isTotal),
      日期: x.date,
      学期: x.term_short || x.term,
      得分: x.earned,
      满分: x.total,
      得分率: ratePercent(x.rate),
      班级名次: x.class_rank ?? '',
      年级名次: x.grade_rank ?? '',
      单元: x.unit_names || '',
    }))
  const sheets = []
  if (scoreRows.length) sheets.push({ title: '单科成绩', rows: scoreRows })
  if (isTotal) {
    const examRows = allExams.value
      .filter((x) => types.includes(x.type))
      .map((x) => ({
        场次: x.name,
        日期: x.date,
        学期: x.term_short || x.term,
        得分: x.earned_sum,
        满分: x.total_sum,
        得分率: ratePercent(x.rate),
        班级排名: x.class_rank ?? '',
        年级排名: x.year_rank ?? '',
        标签: x.tags || '',
      }))
    if (examRows.length) sheets.push({ title: '场次总分', rows: examRows })
  }
  if (!sheets.length) return ElMessage.info('当前板块暂无数据')
  exportXlsx(`导出_${pageTitle.value}.xlsx`, sheets)
}

function exportTermRank() {
  const d = termRankData()
  if (!d) return ElMessage.info('该学期暂无成绩记录')
  const label = termOptions.value.find((t) => t.value === rankTerm.value)?.label || rankTerm.value
  const rows = d.people.map((p) => {
    const obj = { 姓名: p }
    let total = 0
    for (const s of d.subjOrder) {
      const c = d.counts.get(p).get(s) || 0
      obj[s] = c
      total += c
    }
    obj.合计 = total
    return obj
  })
  exportXlsx(`导出_学期排名_${label}.xlsx`, [{ title: '学期排名', rows }])
}

function onResize() {
  scoreChart?.resize()
  rankChart?.resize()
  termRankChart?.resize()
}

function onChildChange(v) {
  setChild(v)
  loadData()
}

onMounted(async () => {
  window.addEventListener('resize', onResize)
  // 直接打开本页时 store 里可能还没有孩子列表，补拉一次；未选过孩子则自动选第一个
  try {
    if (!store.children.length) {
      const { data } = await api.get('/children')
      store.children = data
    }
  } catch {
    /* 下拉为空，用户可刷新重试 */
  }
  if (!childId.value && store.children.length) setChild(store.children[0].id)
  childId.value = store.childId
  try {
    const { data } = await api.get('/subjects')
    subjects.value = data
  } finally {
    loadData()
  }
})
onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  scoreChart?.dispose()
  rankChart?.dispose()
  termRankChart?.dispose()
})
</script>

<style scoped>
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.page-head h3 {
  margin: 0;
}
.filter :deep(.el-form-item) {
  margin-bottom: 8px;
}
.chart {
  width: 100%;
  height: 160px;
}
h3 {
  margin: 14px 0 8px;
}
.rank-title {
  margin-top: 14px;
}
/* 曲线标题行：标题居左、点选控件居右 */
.chart-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 12px;
}
.chart-head h3 {
  margin: 14px 0 8px;
}
.legend-line {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
}
.lg {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #606266;
  cursor: pointer;
  user-select: none;
}
.lg i {
  display: inline-block;
  width: 10px;
  height: 3px;
  border-radius: 2px;
}
.lg.off {
  color: #c0c4cc;
  text-decoration: line-through;
}
.lg.off i {
  background: #c0c4cc !important;
}
</style>
