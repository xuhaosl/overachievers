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
      <el-form-item label="时间">
        <el-radio-group v-model="rangeType" @change="loadData">
          <el-radio-button value="term">本学期</el-radio-button>
          <el-radio-button value="year">本学年</el-radio-button>
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="custom">自定义</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="rangeType === 'custom'" label="">
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
    </el-form>

    <el-empty v-if="!childId" description="请先选择孩子" />
    <el-empty v-else-if="empty" :description="emptyText" />
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
    const [s, e] = await Promise.all([
      api.get('/scores', { params: { child_id: childId.value } }),
      api.get('/exams', { params: { child_id: childId.value } }),
    ])
    allScores.value = s.data.filter((x) => inDateRange(x.date))
    allExams.value = e.data.filter((x) => inDateRange(x.date)).reverse() // 时间正序
    render()
  } catch (err) {
    ElMessage.error(errMsg(err))
  }
}

// 菜单切换「单元测验/期中期末」子项时组件被复用，跟随 query 更新并重绘
watch(
  () => route.query.type,
  (v) => {
    chartType.value = v || 'single'
    render()
  },
)

// 页头标题
const pageTitle = computed(
  () =>
    ({
      single: '单元测验',
      total: '期中期末',
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

  // 简写标签：期中期末视图里，单科成绩与场次同口径（"N上末"），同学期归入同一类目；
  // 单元测验视图为"N上N"（短学期名+单元序号），无单元时显示"？"
  const isTotalView = typeFilters.includes('期中考试') || typeFilters.includes('期末考试')
  const unitLabel = (row) => {
    if (isTotalView) return `${row.term_short || ''}末`
    const nos = [...(row.unit_names || '').matchAll(/第(\d+)单元/g)].map((m) => m[1])
    return `${row.term_short || ''}${nos.join('') || '?'}`
  }
  const examLabel = (e) => `${e.term_short || ''}末`

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

function onResize() {
  scoreChart?.resize()
  rankChart?.resize()
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
