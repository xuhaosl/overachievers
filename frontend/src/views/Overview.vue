<template>
  <div v-if="!store.children.length">
    <el-empty description="欢迎使用！先添加孩子和学科，再录入成绩">
      <el-button type="primary" @click="$router.push('/children')">去添加孩子</el-button>
      <el-button @click="$router.push('/subjects')">去添加学科</el-button>
    </el-empty>
  </div>

  <div v-else>
    <div class="toolbar">
      <el-select v-model="childId" style="width: 140px" @change="load">
        <el-option v-for="c in store.children" :key="c.id" :value="c.id" :label="c.name" />
      </el-select>
      <el-button @click="$router.push('/list')">成绩</el-button>
      <el-button @click="$router.push('/charts')">成长</el-button>
    </div>

    <h3>得分率成长曲线</h3>
    <el-card shadow="never">
      <div class="chart-filter">
        <el-radio-group v-model="rangeType" size="small" @change="renderChart">
          <el-radio-button value="term">本学期</el-radio-button>
          <el-radio-button value="year">本学年</el-radio-button>
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="custom">自定义</el-radio-button>
        </el-radio-group>
        <el-date-picker
          v-if="rangeType === 'custom'"
          v-model="customRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          start-placeholder="开始"
          end-placeholder="结束"
          @change="renderChart"
          style="width: 240px"
        />
        <!-- 图例（学科、考试场次）：与筛选栏齐平，可点选 -->
        <div class="legend-btns">
          <span
            v-for="g in legendItems"
            :key="g.name"
            class="legend-item"
            :class="{ off: offNames.has(g.name) }"
            @click="toggleSeries(g.name)"
          >
            <i class="dot" :style="{ background: offNames.has(g.name) ? '#c0c4cc' : g.color }" />{{ g.name }}
          </span>
        </div>
      </div>
      <el-empty v-if="!chartCount" description="当前时间范围内暂无成绩数据" :image-size="60" />
      <div v-show="chartCount" ref="chartEl" style="height: 155px"></div>
    </el-card>

    <h3>最近考试</h3>
    <el-empty v-if="!ov.recent_exams.length" description="还没有考试场次，去「成绩列表 → 考试场次」新建" :image-size="80" />
    <el-row :gutter="12" v-else>
      <el-col v-for="e in ov.recent_exams" :key="e.id" :xs="24" :sm="12" :lg="8">
        <el-card shadow="hover" class="exam-card clickable" @click="$router.push(`/exam/${e.id}`)">
          <div class="exam-title">
            <b>{{ e.name }}</b>
            <span v-if="e.starred" class="head-star">☆</span>
            <el-tag size="small" type="info">{{ e.type }}</el-tag>
          </div>
          <div class="exam-meta">
            {{ e.date }} · {{ gradeLabel(e.grade) }} · {{ e.term }}
          </div>
          <div class="exam-line" v-if="e.subject_names && e.subject_names.length">
            {{ e.subject_names.join('、') }}
          </div>
          <div class="exam-line">
            总分 <b>{{ e.earned_sum }}</b> / {{ e.total_sum }} · 得分率
            <b>{{ ratePercent(e.rate) }}</b>
          </div>
          <div class="exam-line" v-if="e.year_rank != null || e.class_rank != null">
            {{ [rankText(e.year_rank, '-'), rankText(e.class_rank, '-')].join(' · ') }}
          </div>
          <div class="exam-line" v-if="e.tags">标签：{{ e.tags }}</div>
          <div class="exam-line" v-if="e.note">{{ e.note }}</div>
        </el-card>
      </el-col>
    </el-row>

    <h3 style="margin-top: 3px">各科最新成绩</h3>
    <el-empty v-if="!ov.subject_latest.length" description="还没有成绩记录" :image-size="80" />
    <el-row :gutter="12" v-else>
      <el-col v-for="s in ov.subject_latest" :key="s.subject_id" :xs="12" :sm="8" :lg="6">
        <el-card
          shadow="hover"
          class="subject-card clickable"
          @click="$router.push({ path: '/list', query: { subject_id: s.subject_id, child_id: childId } })"
        >
          <span class="color-dot" :style="{ background: s.subject_color }" />
          <b>{{ s.title || s.subject_name }}</b>
          <span v-if="s.starred" class="head-star">☆</span>
          <div class="subject-line">{{ s.latest_display }}</div>
          <div class="subject-line">得分率 <b>{{ ratePercent(s.latest_rate) }}</b></div>
          <div class="subject-line muted">{{ [s.meta, s.latest_date].filter(Boolean).join(' · ') }}</div>
          <div class="subject-line" v-if="s.grade_rank != null || s.class_rank != null">
            {{ [rankText(s.grade_rank, '-'), rankText(s.class_rank, '-')].join(' · ') }}
          </div>
          <div class="subject-line" v-if="s.tags">标签：{{ s.tags }}</div>
          <div class="subject-line" v-if="s.note">{{ s.note }}</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api'
import { store, setChild } from '../store'
import { gradeLabel, inferTerm, ratePercent, rankText } from '../utils'

const childId = ref(store.childId)
const ov = ref({ recent_exams: [], subject_latest: [] })

// ---------- 得分率成长曲线 ----------
const rangeType = ref('all')
const customRange = ref(null)
const chartEl = ref(null)
let chart = null
const allScores = ref([])
const allExams = ref([])

function currentTerm() {
  return inferTerm(new Date().toISOString().slice(0, 10))
}
// 学期/学年的日期区间（与成长曲线页一致）
function termRangeOf(term) {
  const [a, b] = term.split(' ')[0].split('-').map(Number)
  if (/第(一|1)学期/.test(term)) return [`${a}-08-01`, `${b}-01-31`]
  return [`${b}-02-01`, `${b}-07-31`]
}
function inRange(dateStr) {
  if (rangeType.value === 'all') return true
  if (rangeType.value === 'term') {
    const [from, to] = termRangeOf(currentTerm())
    return dateStr >= from && dateStr <= to
  }
  if (rangeType.value === 'year') {
    const [a, b] = currentTerm().split(' ')[0].split('-').map(Number)
    return dateStr >= `${a}-08-01` && dateStr <= `${b}-07-31`
  }
  if (rangeType.value === 'custom') {
    if (!customRange.value) return false
    return dateStr >= customRange.value[0] && dateStr <= customRange.value[1]
  }
  return true
}

// 过滤后参与绘图的数据条数（决定显示图表还是空提示）
const chartCount = computed(() => {
  return (
    allScores.value.filter((x) => inRange(x.date)).length +
    allExams.value.filter((x) => inRange(x.date)).length
  )
})

async function loadChartData() {
  if (!childId.value) return
  try {
    const [s, e] = await Promise.all([
      api.get('/scores', { params: { child_id: childId.value } }),
      api.get('/exams', { params: { child_id: childId.value } }),
    ])
    allScores.value = s.data
    allExams.value = e.data
    renderChart()
  } catch (err) {
    ElMessage.error(errMsg(err))
  }
}

function renderChart() {
  nextTick(() => {
    if (!chartEl.value) return
    if (!chart) chart = echarts.init(chartEl.value)
    chart.resize()
    // 各单科：每个学科一条得分率折线
    const bySubject = new Map()
    for (const s of allScores.value.filter((x) => inRange(x.date))) {
      if (!bySubject.has(s.subject_id)) {
        bySubject.set(s.subject_id, { name: s.subject_name, color: s.subject_color, pts: [] })
      }
      bySubject.get(s.subject_id).pts.push([s.date, Math.round(s.rate * 1000) / 10])
    }
    const series = [...bySubject.values()].map((g) => ({
      name: g.name,
      type: 'line',
      symbolSize: 6,
      itemStyle: { color: g.color },
      lineStyle: { color: g.color },
      data: g.pts.sort((a, b) => a[0].localeCompare(b[0])),
    }))
    // 各场次：考试总分得分率折线
    const ex = allExams.value.filter((x) => inRange(x.date)).sort((a, b) => a.date.localeCompare(b.date))
    if (ex.length) {
      series.push({
        name: '考试场次',
        type: 'line',
        symbol: 'diamond',
        symbolSize: 8,
        itemStyle: { color: '#E6A23C' },
        lineStyle: { color: '#E6A23C', width: 2 },
        data: ex.map((x) => [x.date, Math.round(x.rate * 1000) / 10]),
      })
    }
    // 图例移到筛选栏（自定义 HTML 图例），图内 legend 仅保留点选状态
    chartSeries.value = series.map((x) => ({ name: x.name, color: x.itemStyle.color }))
    const selected = {}
    series.forEach((x) => {
      selected[x.name] = !offNames.value.has(x.name)
    })
    chart.setOption(
      {
        tooltip: { trigger: 'axis', valueFormatter: (v) => (v == null ? '-' : `${v}%`) },
        legend: { show: false, selected, data: series.map((x) => x.name) },
        grid: { left: 44, right: 16, top: 10, bottom: 18 },
        xAxis: { type: 'time' },
        yAxis: { type: 'value', min: 60, max: 100, axisLabel: { formatter: '{value}%' } },
        series,
      },
      true,
    )
  })
}

// 自定义图例：点选切换曲线显示/隐藏
const chartSeries = ref([])
const offNames = ref(new Set())
const legendItems = computed(() => chartSeries.value)
function toggleSeries(name) {
  const set = new Set(offNames.value)
  if (set.has(name)) set.delete(name)
  else set.add(name)
  offNames.value = set
  chart?.dispatchAction({ type: 'legendToggleSelect', name })
}

function resizeChart() {
  chart?.resize()
}

async function load() {
  setChild(childId.value)
  if (!childId.value && store.children.length) childId.value = store.children[0].id
  try {
    const { data } = await api.get('/stats/overview', {
      params: childId.value ? { child_id: childId.value } : {},
    })
    ov.value = data
  } catch (e) {
    console.error(errMsg(e))
  }
  loadChartData()
}

onMounted(async () => {
  window.addEventListener('resize', resizeChart)
  try {
    const { data } = await api.get('/children')
    store.children = data
  } finally {
    load()
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeChart)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 8px;
}
/* 两个按钮靠近一点 */
.toolbar :deep(.el-button + .el-button) {
  margin-left: 1px;
}
/* 三个板块（曲线/最近考试/各科最新成绩）上下间距 8px */
h3 {
  margin: 8px 0;
}
.chart-filter {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
/* 自定义图例：与筛选栏同一行，靠右 */
.legend-btns {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
  font-size: 12px;
}
.legend-item {
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--el-text-color-regular);
  user-select: none;
}
.legend-item.off {
  color: var(--el-text-color-secondary);
  text-decoration: line-through;
}
.legend-item .dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
}
.exam-card {
  margin-bottom: 8px;
}
/* 卡片高度缩小：内边距收紧 */
.exam-card :deep(.el-card__body),
.subject-card :deep(.el-card__body) {
  padding: 10px 14px;
}
.clickable {
  cursor: pointer;
}
.exam-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.exam-meta,
.exam-line {
  font-size: 13px;
  color: var(--el-text-color-regular);
  margin-top: 3px;
}
.subject-card {
  margin-bottom: 8px;
}
.subject-line {
  font-size: 13px;
  margin-top: 3px;
}
.color-dot {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 3px;
  margin-right: 6px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.head-star {
  color: #f7ba2a;
  font-size: 18px;
  margin: 0 6px;
  vertical-align: -2px;
}
</style>
