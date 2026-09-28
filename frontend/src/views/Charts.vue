<template>
  <div>
    <!-- 筛选栏 -->
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
      <el-form-item v-if="chartType === 'rate' || chartType === 'rank'">
        <el-select v-model="subjectIds" multiple collapse-tags placeholder="选择学科（可多选对比）" style="width: 260px" @change="render">
          <el-option v-for="s in subjects" :key="s.id" :value="s.id" :label="s.name" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="chartType === 'rank' || chartType === 'examrank'">
        <el-radio-group v-model="rankMode" @change="render">
          <el-radio-button value="grade">年级排名</el-radio-button>
          <el-radio-button value="class">班级排名</el-radio-button>
        </el-radio-group>
      </el-form-item>
    </el-form>

    <el-tabs v-model="chartType" @tab-change="onTabChange">
      <el-tab-pane label="得分率曲线" name="rate" />
      <el-tab-pane label="总分曲线" name="exam" />
      <el-tab-pane label="单科排名曲线" name="rank" />
      <el-tab-pane label="总分排名曲线" name="examrank" />
    </el-tabs>

    <el-empty v-if="!childId" description="请先选择孩子" />
    <el-empty v-else-if="empty" :description="emptyText" />
    <div v-show="childId && !empty" ref="chartEl" class="chart"></div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, nextTick } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api'
import { store, setChild } from '../store'
import { gradeLabel, inferTerm, ratePercent } from '../utils'

const childId = ref(store.childId)
const rangeType = ref('all')
const customRange = ref(null)
const chartType = ref('rate')
const rankMode = ref('grade')
const subjectIds = ref([])
const subjects = ref([])
const allScores = ref([])
const allExams = ref([])

const chartEl = ref(null)
let chart = null
const empty = ref(false)

const emptyText = computed(() => {
  if (rangeType.value === 'term') return '本学期暂无数据，试试切换时间范围'
  if (rangeType.value === 'year') return '本学年暂无数据，试试切换时间范围'
  return '暂无成绩数据，先去「录成绩」录入一些成绩吧'
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
// 学期匹配（1月属于上一学年下学期，所以直接比日期区间更可靠）
function termRangeOf(term) {
  // "2026-2027 上学期" -> 2026-08-01 ~ 2027-01-31；下学期 -> 2027-02-01 ~ 2027-07-31
  const [a, b] = term.split(' ')[0].split('-').map(Number)
  if (term.includes('上')) return [`${a}-08-01`, `${b}-01-31`]
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

function onTabChange() {
  // 切到排名/得分率时默认全选学科
  if ((chartType.value === 'rate' || chartType.value === 'rank') && !subjectIds.value.length) {
    subjectIds.value = subjects.value.map((s) => s.id)
  }
  render()
}

// ---------- 绘图 ----------
function showChart() {
  empty.value = false
  // 同步初始化，保证紧随其后的 chart.setOption() 不会拿到 null；
  // 首帧可能还在隐藏态，尺寸交给 nextTick 的 resize 修正
  if (!chart) chart = echarts.init(chartEl.value)
  nextTick(() => chart?.resize())
}
function setEmpty() {
  empty.value = true
  if (chart) chart.clear()
}

function render() {
  if (!childId.value) return setEmpty()
  if (chartType.value === 'rate') return renderRate()
  if (chartType.value === 'exam') return renderExam()
  if (chartType.value === 'rank') return renderRank()
  return renderExamRank()
}

// 得分率曲线：多科各一条线，纵轴 0~100%
function renderRate() {
  const picked = subjects.value.filter((s) => subjectIds.value.includes(s.id))
  const series = picked
    .map((s) => {
      const pts = allScores.value
        .filter((x) => x.subject_id === s.id)
        .sort((a, b) => (a.date > b.date ? 1 : -1))
        .map((x) => [x.date, Math.round(x.rate * 1000) / 10])
      return {
        name: s.name,
        type: 'line',
        data: pts,
        connectNulls: false,
        color: s.color,
        label: { show: pts.length <= 12, position: 'top', formatter: (p) => `${p.value[1]}%`, fontSize: 10 },
      }
    })
    .filter((se) => se.data.length)
  if (!series.length) return setEmpty()
  showChart()
  chart.setOption(
    {
      tooltip: {
        trigger: 'item',
        formatter: (p) => {
          const s = allScores.value.find(
            (x) => x.subject_id === picked.find((ps) => ps.name === p.seriesName)?.id && x.date === p.value[0],
          )
          return s
            ? `${p.seriesName}<br/>${p.value[0]}<br/>得分 <b>${s.regular_score}${s.bonus_score != null ? `（${s.bonus_score}）` : ''}</b> / ${s.total}<br/>得分率 <b>${ratePercent(s.rate)}</b>`
            : `${p.seriesName}<br/>${p.value[0]}<br/>${p.value[1]}%`
        },
      },
      legend: { top: 0 },
      grid: { left: 50, right: 30, top: 40, bottom: 60 },
      xAxis: { type: 'time' },
      yAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } },
      series,
    },
    true,
  )
}

// 总分曲线：按场次聚合，纵轴得分率统一量纲
function renderExam() {
  const pts = allExams.value
    .filter((x) => x.total_sum > 0)
    .map((x) => [x.date, Math.round(x.rate * 1000) / 10])
  if (!pts.length) return setEmpty()
  showChart()
  chart.setOption(
    {
      tooltip: {
        trigger: 'item',
        formatter: (p) => {
          const e = allExams.value.find((x) => x.date === p.value[0])
          return e
            ? `${e.name}<br/>${e.date}（${e.type}）<br/>总分 <b>${e.earned_sum}</b> / ${e.total_sum}（${e.score_count} 科）<br/>得分率 <b>${ratePercent(e.rate)}</b>`
            : `${p.value[0]}<br/>${p.value[1]}%`
        },
      },
      grid: { left: 50, right: 30, top: 30, bottom: 60 },
      xAxis: { type: 'time' },
      yAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } },
      series: [
        {
          name: '总分得分率',
          type: 'line',
          data: pts,
          label: { show: pts.length <= 12, position: 'top', formatter: (p) => `${p.value[1]}%`, fontSize: 10 },
        },
      ],
    },
    true,
  )
}

// 排名曲线公共 option
function rankOption(name, pts) {
  showChart()
  chart.setOption(
    {
      tooltip: { trigger: 'item', formatter: (p) => `${name}<br/>${p.value[0]}<br/>${rankMode.value === 'grade' ? '年级' : '班级'}第 <b>${p.value[1]}</b> 名` },
      grid: { left: 50, right: 30, top: 30, bottom: 60 },
      xAxis: { type: 'time' },
      yAxis: { type: 'value', inverse: true, minInterval: 1, name: '名次（越小越高）' },
      series: [{ name, type: 'line', data: pts, label: { show: pts.length <= 15, position: 'top', fontSize: 10 } }],
    },
    true,
  )
}

// 单科排名曲线
function renderRank() {
  const picked = subjects.value.filter((s) => subjectIds.value.includes(s.id))
  const series = picked
    .map((s) => {
      const key = rankMode.value === 'grade' ? 'grade_rank' : 'class_rank'
      const pts = allScores.value
        .filter((x) => x.subject_id === s.id && x[key] != null)
        .sort((a, b) => (a.date > b.date ? 1 : -1))
        .map((x) => [x.date, x[key]])
      return { name: s.name, type: 'line', data: pts, connectNulls: false, color: s.color }
    })
    .filter((se) => se.data.length)
  if (!series.length) return setEmpty()
  showChart()
  chart.setOption(
    {
      tooltip: {
        trigger: 'item',
        formatter: (p) => `${p.seriesName}<br/>${p.value[0]}<br/>${rankMode.value === 'grade' ? '年级' : '班级'}第 <b>${p.value[1]}</b> 名`,
      },
      legend: { top: 0 },
      grid: { left: 50, right: 30, top: 40, bottom: 60 },
      xAxis: { type: 'time' },
      yAxis: { type: 'value', inverse: true, minInterval: 1, name: '名次（越小越高）' },
      series,
    },
    true,
  )
}

// 总分排名曲线：按场次的总排名
function renderExamRank() {
  const key = rankMode.value === 'grade' ? 'grade_rank' : 'class_rank'
  const pts = allExams.value
    .filter((x) => x[key] != null)
    .map((x) => [x.date, x[key]])
  if (!pts.length) return setEmpty()
  rankOption('总分排名', pts)
}

function onResize() {
  chart?.resize()
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
    // 默认标签是得分率/单科排名，需要先全选学科，否则会误显示"暂无数据"
    if (!subjectIds.value.length) subjectIds.value = subjects.value.map((s) => s.id)
  } finally {
    loadData()
  }
})
onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
})
</script>

<style scoped>
.filter :deep(.el-form-item) {
  margin-bottom: 8px;
}
.chart {
  width: 100%;
  height: 420px;
}
</style>
