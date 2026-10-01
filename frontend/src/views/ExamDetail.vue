<template>
  <div v-loading="loading">
    <template v-if="exam">
      <div class="page-head">
        <el-page-header @back="$router.push({ path: '/list', query: { tab: 'exam' } })">
          <template #content>
            <b>{{ exam.name }}</b>
            <span v-if="exam.starred" class="head-star">☆</span>
            <el-tag size="small" type="info" style="margin-left: 8px">{{ exam.type }}</el-tag>
          </template>
          <template #extra>
            <el-button :disabled="!prevId" @click="go(prevId)">上一个</el-button>
            <el-button :disabled="!nextId" @click="go(nextId)">下一个</el-button>
            <el-button type="primary" @click="showEdit = true">编辑</el-button>
          </template>
        </el-page-header>
      </div>

      <el-card shadow="never" class="detail-card">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="孩子">{{ exam.child_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="日期">{{ exam.date }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ exam.type }}</el-descriptions-item>
          <el-descriptions-item label="年级">
            {{ [exam.stage, exam.grade ? `${exam.grade}年级` : ''].filter(Boolean).join('') || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="学期">{{ exam.term }}</el-descriptions-item>
          <el-descriptions-item label="全科总分">
            {{ examSum ? `${examSum.earned} / ${examSum.total}` : '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="班级排名">
            {{ rankText(exam.class_rank) }}
          </el-descriptions-item>
          <el-descriptions-item label="年级排名（学年）">
            {{ rankText(exam.year_rank) }}
          </el-descriptions-item>
          <el-descriptions-item label="得分率">
            {{ examSum ? ratePercent(examSum.rate) : '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="班级最高分">
            {{ exam.high_score != null ? exam.high_score : '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="最高得分者" :span="2">
            {{ exam.high_scorer || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="标签">{{ exam.tags || '—' }}</el-descriptions-item>
          <el-descriptions-item label="备注" :span="2">{{ exam.note || '—' }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 已录成绩 -->
      <el-card shadow="never" class="scores-card" style="margin-top: 8px">
        <template #header>
          <div class="scores-head">
            <span>场内各科成绩</span>
            <el-select
              v-model="pullId"
              filterable
              clearable
              placeholder="从已录成绩拉取（选后自动加入）"
              style="width: 340px"
              @change="attachScore"
            >
              <el-option
                v-for="row in pullScores"
                :key="row.id"
                :value="row.id"
                :label="`${row.subject_name} ${row.date} ${earnedLabel(row)}`"
              />
            </el-select>
          </div>
        </template>
        <el-alert
          :title="`全科合计：${
            examSum
              ? `${examSum.earned} / ${examSum.total}（得分率 ${ratePercent(examSum.rate)}）`
              : '暂无成绩，从右上角拉取'
          }`"
          type="success"
          :closable="false"
          style="margin-bottom: 12px"
        />
        <el-empty v-if="!exam.scores.length" description="还没有成绩，从右上角拉取「录一条」里的成绩" :image-size="80" />
        <el-table v-else :data="exam.scores" size="small">
          <el-table-column label="日期" width="105">
            <template #default="{ row }">{{ row.date }}</template>
          </el-table-column>
          <el-table-column label="学科" width="85">
            <template #default="{ row }">
              <span class="color-dot" :style="{ background: row.subject_color }" />{{ row.subject_name }}
            </template>
          </el-table-column>
          <el-table-column label="成绩" min-width="100">
            <template #default="{ row }">
              {{ displayScore(row) }} / {{ displayTotal(row) }}
            </template>
          </el-table-column>
          <el-table-column label="得分率" width="90">
            <template #default="{ row }">{{ ratePercent(row.rate) }}</template>
          </el-table-column>
          <el-table-column label="年级名次" width="90">
            <template #default="{ row }">{{ rankText(row.grade_rank) }}</template>
          </el-table-column>
          <el-table-column label="班级名次" width="90">
            <template #default="{ row }">{{ rankText(row.class_rank) }}</template>
          </el-table-column>
          <el-table-column label="备注" min-width="120">
            <template #default="{ row }">{{ row.note || '—' }}</template>
          </el-table-column>
          <el-table-column width="130" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" text @click="$router.push(`/score/${row.id}`)">详情</el-button>
              <el-button size="small" type="danger" text @click="detachScore(row)">移出</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>

    <!-- 编辑场次 -->
    <ExamEditDialog v-model="showEdit" :exam="exam" @saved="loadExam" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api'
import { earnedLabel, ratePercent, rankText } from '../utils'
import ExamEditDialog from '../components/ExamEditDialog.vue'

const route = useRoute()
const router = useRouter()
const exam = ref(null)
const loading = ref(true)
const pullId = ref(null)
const pullScores = ref([])
const showEdit = ref(false)

const examSum = computed(() => {
  const list = exam.value?.scores || []
  if (!list.length) return null
  const earned = list.reduce((a, s) => a + s.earned, 0)
  const total = list.reduce((a, s) => a + s.total, 0)
  return { earned, total, rate: total > 0 ? earned / total : 0 }
})

// "100（5）"：常规得分＋括号内附加得分
function displayScore(row) {
  return `${row.regular_score}${row.bonus_score != null ? `（${row.bonus_score}）` : ''}`
}

// "100（5）"：常规总分＋括号内附加总分
function displayTotal(row) {
  return `${row.regular_total}${row.bonus_total != null ? `（${row.bonus_total}）` : ''}`
}

async function loadExam() {
  loading.value = true
  try {
    const { data } = await api.get(`/exams/${route.params.id}`)
    exam.value = data
    // 同孩子全部场次（按列表顺序：日期倒序），用于上一个/下一个导航
    const { data: list } = await api.get('/exams', { params: { child_id: data.child_id } })
    listIds.value = list.map((x) => x.id)
    await loadPullScores()
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    loading.value = false
  }
}

// 上一个/下一个：列表中当前场次的前一条/后一条
const listIds = ref([])
const idx = computed(() => listIds.value.indexOf(exam.value?.id))
const prevId = computed(() => (idx.value > 0 ? listIds.value[idx.value - 1] : null))
const nextId = computed(() =>
  idx.value >= 0 && idx.value < listIds.value.length - 1 ? listIds.value[idx.value + 1] : null,
)
function go(id) {
  if (id) router.push(`/exam/${id}`)
}
// 同组件路由切换（点上一个/下一个）时重新加载
watch(
  () => route.params.id,
  (v, o) => {
    if (v && v !== o) loadExam()
  },
)

async function loadPullScores() {
  const { data } = await api.get('/scores', { params: { child_id: exam.value.child_id } })
  // 可拉取的成绩与考试类型相关：期末考试场次只能拉期末考试的单科成绩，以此类推
  pullScores.value = data.filter((s) => !s.exam_id && s.type === exam.value.type)
}

async function attachScore(scoreId) {
  if (!scoreId) return
  try {
    await api.post(`/scores/${scoreId}/attach`, { exam_id: exam.value.id })
    ElMessage.success('已拉进场次')
    pullId.value = null
    loadExam()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function detachScore(row) {
  try {
    await api.post(`/scores/${row.id}/detach`)
    ElMessage.success('已移出场次，成绩退回独立状态')
    loadExam()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

onMounted(loadExam)
</script>

<style scoped>
.page-head {
  margin-bottom: 16px;
}
/* 卡片内边距收紧 */
.detail-card :deep(.el-card__body),
.scores-card :deep(.el-card__body) {
  padding: 12px;
}
/* 详情行间距调小2px（单元格上下内边距 8px → 6px） */
.detail-card :deep(.el-descriptions__body) {
  --el-descriptions-item-bordered-padding: 6px 11px;
}
/* "场内各科成绩"标题行上下 8px，标题与拉取控件左右分布 */
.scores-card :deep(.el-card__header) {
  padding: 8px 12px;
}
.scores-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.star {
  color: #f7ba2a;
  font-weight: 600;
}
.head-star {
  color: #f7ba2a;
  font-size: 20px;
  margin-left: 6px;
  vertical-align: -2px;
}
.color-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  margin-right: 5px;
}
.hint {
  color: #909399;
  font-size: 12px;
}
</style>
