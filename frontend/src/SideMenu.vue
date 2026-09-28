<template>
  <el-menu router :default-active="$route.path" class="side-menu">
    <el-menu-item v-for="r in routes" :key="r.path" :index="r.path">
      <el-icon><component :is="icons[r.meta.icon]" /></el-icon>
      <span>{{ r.meta.title }}</span>
    </el-menu-item>
  </el-menu>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  HomeFilled,
  EditPen,
  List,
  TrendCharts,
  User,
  Reading,
} from '@element-plus/icons-vue'

const icons = { HomeFilled, EditPen, List, TrendCharts, User, Reading }
const route = useRoute()
const router = useRouter()
const routes = computed(() =>
  router.getRoutes().filter((r) => r.meta?.title && !r.meta?.hidden),
)
</script>
