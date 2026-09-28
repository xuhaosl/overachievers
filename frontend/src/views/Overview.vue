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
      <el-button type="primary" plain @click="$router.push('/entry')">录成绩</el-button>
      <el-button plain @click="$router.push('/charts')">看曲线</el-button>
    </div>

    <h3>最近考试</h3>
    <el-empty v-if="!ov.recent_exams.length" description="还没有考试场次，去「录成绩」创建一场考试" :image-size="80" />
    <el-row :gutter="12" v-else>
      <el-col v-for="e in ov.recent_exams" :key="e.id" :xs="24" :sm="12" :lg="8">
        <el-card shadow="hover" class="exam-card">
          <div class="exam-title">
            <b>{{ e.name }}</b>
            <el-tag size="small" type="info">{{ e.type }}</el-tag>
          </div>
          <div class="exam-meta">
            {{ e.date }} · {{ gradeLabel(e.grade) }} · {{ e.term }} · 共 {{ e.score_count }} 科
          </div>
          <div class="exam-line">
            总分 <b>{{ e.earned_sum }}</b> / {{ e.total_sum }} · 得分率
            <b>{{ ratePercent(e.rate) }}</b>
          </div>
          <div class="exam-line" v-if="e.grade_rank != null || e.class_rank != null">
            年级第 {{ e.grade_rank ?? '-' }} 名 · 班级第 {{ e.class_rank ?? '-' }} 名
          </div>
        </el-card>
      </el-col>
    </el-row>

    <h3>各科最新成绩</h3>
    <el-empty v-if="!ov.subject_latest.length" description="还没有成绩记录" :image-size="80" />
    <el-row :gutter="12" v-else>
      <el-col v-for="s in ov.subject_latest" :key="s.subject_id" :xs="12" :sm="8" :lg="6">
        <el-card shadow="hover" class="subject-card">
          <span class="color-dot" :style="{ background: s.subject_color }" />
          <b>{{ s.subject_name }}</b>
          <div class="subject-line">{{ s.latest_display }}</div>
          <div class="subject-line">
            得分率 <b>{{ ratePercent(s.latest_rate) }}</b>
            <span class="muted">（{{ s.latest_date }}）</span>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api, errMsg } from '../api'
import { store, setChild } from '../store'
import { gradeLabel, ratePercent } from '../utils'

const childId = ref(store.childId)
const ov = ref({ recent_exams: [], subject_latest: [] })

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
}

onMounted(async () => {
  try {
    const { data } = await api.get('/children')
    store.children = data
  } finally {
    load()
  }
})
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 8px;
}
h3 {
  margin: 18px 0 10px;
}
.exam-card {
  margin-bottom: 12px;
}
.exam-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.exam-meta,
.exam-line {
  font-size: 13px;
  color: var(--el-text-color-regular);
  margin-top: 4px;
}
.subject-card {
  margin-bottom: 12px;
}
.subject-line {
  font-size: 13px;
  margin-top: 6px;
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
</style>
