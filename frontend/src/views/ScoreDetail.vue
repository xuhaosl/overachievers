<template>
  <div v-loading="loading" class="detail-page">
    <template v-if="s">
      <div class="page-head">
        <el-page-header @back="$router.back()">
          <template #content>
            <span class="color-dot" :style="{ background: s.subject_color }" />
            <b>{{ pageTitle }}</b>
            <span v-if="s.starred" class="head-star">☆</span>
            <el-tag size="small" type="info" style="margin-left: 8px">{{ s.type }}</el-tag>
          </template>
          <template #extra>
            <el-button :disabled="!prevId" @click="go(prevId)">上一个</el-button>
            <el-button :disabled="!nextId" @click="go(nextId)">下一个</el-button>
            <el-button type="primary" @click="showEdit = true">编辑</el-button>
          </template>
        </el-page-header>
      </div>

      <el-card shadow="never">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="孩子">{{ s.child_name }}</el-descriptions-item>
          <el-descriptions-item label="日期">{{ s.date }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ s.type }}</el-descriptions-item>
          <el-descriptions-item label="学科">{{ s.subject_name }}</el-descriptions-item>
          <el-descriptions-item label="单元">
            <template v-if="s.unit_names">
              <el-link type="primary" @click="goSubject">{{ s.unit_names }}</el-link>
            </template>
            <template v-else>—</template>
          </el-descriptions-item>
          <el-descriptions-item label="年级">
            {{ [s.stage, s.grade ? `${s.grade}年级` : '', shortTerm(s.term)].filter(Boolean).join('') || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="学期">{{ s.term }}</el-descriptions-item>
          <el-descriptions-item label="成绩">
            <b>{{ displayScore(s) }}</b>
            <span class="muted"> / {{ displayTotal(s) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="得分率">
            <b>{{ ratePercent(s.rate) }}</b>
            <span class="muted" style="margin-left: 4px">（自动计算）</span>
          </el-descriptions-item>
          <el-descriptions-item label="年级排名">{{ rankText(s.grade_rank) }}</el-descriptions-item>
          <el-descriptions-item label="班级排名">
            <!-- 数字名次显示"第 x 名（共 n 人）"，文字名次（如"前5"）原样显示 -->
            {{ s.class_rank != null && s.class_rank !== ''
              ? (/^\d+(\.\d+)?$/.test(String(s.class_rank))
                ? `第 ${s.class_rank} 名${s.class_size ? `（共 ${s.class_size} 人）` : ''}`
                : String(s.class_rank))
              : '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="所属场次">
            <template v-if="s.exam_id">
              <el-link type="primary" @click="$router.push(`/exam/${s.exam_id}`)">{{ s.exam_name }}</el-link>
            </template>
            <template v-else>—（独立成绩）</template>
          </el-descriptions-item>
          <el-descriptions-item label="班级最高分">
            {{ s.high_score != null ? s.high_score : '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="最高得分者" :span="2">
            {{ s.high_scorer || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="标签">{{ s.tags || '—' }}</el-descriptions-item>
          <el-descriptions-item label="备注" :span="2">{{ s.note || '—' }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card shadow="never" style="margin-top: 16px">
        <template #header>
          <div class="card-head">
            <span>试卷图片（为将来的试卷分析、错题整理预留）</span>
            <el-upload
              :show-file-list="false"
              :auto-upload="true"
              :http-request="doUpload"
              accept=".jpg,.jpeg,.png,.gif,.webp"
              multiple
            >
              <el-button type="primary" :loading="uploading">上传图片</el-button>
            </el-upload>
          </div>
        </template>

        <el-empty v-if="!images.length" description="还没有图片，点右上角上传" :image-size="80" />
        <div v-else class="img-grid">
          <div v-for="img in images" :key="img.id" class="img-item">
            <el-image
              :src="img.url"
              :preview-src-list="images.map((i) => i.url)"
              :initial-index="images.findIndex((i) => i.id === img.id)"
              fit="cover"
              class="img-thumb"
            />
            <div class="img-op">
              <span class="img-name">{{ img.original_name || '图片' }}</span>
              <el-button size="small" type="danger" text @click="delImage(img)">删除</el-button>
            </div>
          </div>
        </div>
      </el-card>
    </template>

    <!-- 编辑成绩 -->
    <ScoreEditDialog v-model="showEdit" :score="s" @saved="load" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, errMsg } from '../api'
import { gradeLabel, ratePercent, rankText, shortTerm } from '../utils'
import ScoreEditDialog from '../components/ScoreEditDialog.vue'

const route = useRoute()
const router = useRouter()
const s = ref(null)
const images = ref([])
const loading = ref(true)
const uploading = ref(false)
const showEdit = ref(false)

// 标题：阶段年级学期学科单元，如"某年级第N学期某学科第N单元"
const pageTitle = computed(() => {
  const v = s.value
  if (!v) return ''
  const units = v.unit_names
    ? v.unit_names.split('、').map((x) => x.split('（')[0]).join('、')
    : ''
  const termPart = v.term ? v.term.split(' ').pop() : ''
  return [v.stage, v.grade ? `${v.grade}年级` : '', termPart, v.subject_name, units]
    .filter(Boolean)
    .join('')
})

function displayScore(row) {
  const base = `${row.regular_score}${row.bonus_score != null ? `（${row.bonus_score}）` : ''}`
  return base
}

// 总分同样带附加分："100（5）"
function displayTotal(row) {
  return `${row.regular_total}${row.bonus_total != null ? `（${row.bonus_total}）` : ''}`
}

function earned(row) {
  return (row.regular_score || 0) + (row.bonus_score || 0)
}

function totalSum(row) {
  return (row.regular_total || 0) + (row.bonus_total || 0)
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get(`/scores/${route.params.id}`)
    s.value = data
    images.value = (await api.get(`/scores/${route.params.id}/images`)).data
    // 同孩子全部成绩（按列表顺序：日期倒序），用于上一个/下一个导航
    const { data: list } = await api.get('/scores', { params: { child_id: data.child_id } })
    listIds.value = list.map((x) => x.id)
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    loading.value = false
  }
}

// 上一个/下一个：列表中当前成绩的前一条/后一条
const listIds = ref([])
const idx = computed(() => listIds.value.indexOf(s.value?.id))
const prevId = computed(() => (idx.value > 0 ? listIds.value[idx.value - 1] : null))
const nextId = computed(() =>
  idx.value >= 0 && idx.value < listIds.value.length - 1 ? listIds.value[idx.value + 1] : null,
)
function go(id) {
  if (id) router.push(`/score/${id}`)
}

// 点单元跳到学科详情页对应学期TAB，用于修改单元内容
function goSubject() {
  const q = s.value?.term_short ? { term: s.value.term_short } : {}
  router.push({ path: `/subject/${s.value.subject_id}`, query: q })
}
// 同组件路由切换（点上一个/下一个）时重新加载
watch(
  () => route.params.id,
  (v, o) => {
    if (v && v !== o) load()
  },
)

async function doUpload({ file }) {
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    await api.post(`/scores/${route.params.id}/images`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    ElMessage.success('已上传')
    images.value = (await api.get(`/scores/${route.params.id}/images`)).data
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    uploading.value = false
  }
}

async function delImage(img) {
  try {
    await api.delete(`/scores/images/${img.id}`)
    images.value = images.value.filter((i) => i.id !== img.id)
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

onMounted(load)
</script>

<style scoped>
.page-head {
  margin-bottom: 16px;
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
  width: 12px;
  height: 12px;
  border-radius: 3px;
  margin-right: 6px;
  vertical-align: middle;
}
.muted {
  color: #909399;
  font-size: 13px;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.img-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
}
.img-item {
  width: 150px;
}
.img-thumb {
  width: 150px;
  height: 110px;
  border-radius: 6px;
  border: 1px solid #ebeef5;
}
.img-op {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 4px;
}
.img-name {
  font-size: 12px;
  color: #909399;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
