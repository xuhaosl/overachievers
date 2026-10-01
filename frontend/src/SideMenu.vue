<template>
  <el-menu
    router
    :default-active="$route.fullPath"
    :default-openeds="['/list', '/charts']"
    class="side-menu"
  >
    <!-- 一级菜单：无 group 的路由（成绩列表单独作为子菜单处理） -->
    <template v-for="r in topRoutes" :key="r.path">
      <el-sub-menu v-if="r.path === '/list'" index="/list">
        <template #title>
          <el-icon><component :is="icons[r.meta.icon]" /></el-icon>
          <span>{{ r.meta.title }}</span>
        </template>
        <el-menu-item index="/list?tab=single">
          <el-icon><component :is="icons.EditPen" /></el-icon>
          <span>单科成绩</span>
        </el-menu-item>
        <el-menu-item index="/list?tab=exam">
          <el-icon><component :is="icons.Tickets" /></el-icon>
          <span>考试场次</span>
        </el-menu-item>
      </el-sub-menu>
      <el-sub-menu v-else-if="r.path === '/charts'" index="/charts">
        <template #title>
          <el-icon><component :is="icons[r.meta.icon]" /></el-icon>
          <span>{{ r.meta.title }}</span>
        </template>
        <el-menu-item index="/charts?type=single">
          <el-icon><component :is="icons.TrendCharts" /></el-icon>
          <span>单元测验</span>
        </el-menu-item>
        <el-menu-item index="/charts?type=total">
          <el-icon><component :is="icons.TrendCharts" /></el-icon>
          <span>期中期末</span>
        </el-menu-item>
      </el-sub-menu>
      <el-menu-item v-else :index="r.path">
        <el-icon><component :is="icons[r.meta.icon]" /></el-icon>
        <span>{{ r.meta.title }}</span>
      </el-menu-item>
    </template>
    <!-- 二级菜单：设置 -->
    <el-sub-menu index="settings">
      <template #title>
        <el-icon><component :is="icons.Setting" /></el-icon>
        <span>设置</span>
      </template>
      <el-menu-item v-for="r in settingRoutes" :key="r.path" :index="r.path">
        <el-icon><component :is="icons[r.meta.icon]" /></el-icon>
        <span>{{ r.meta.title }}</span>
      </el-menu-item>
    </el-sub-menu>
  </el-menu>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  HomeFilled,
  EditPen,
  List,
  Tickets,
  TrendCharts,
  User,
  Reading,
  Setting,
  OfficeBuilding,
  Download,
} from '@element-plus/icons-vue'

const icons = { HomeFilled, EditPen, List, Tickets, TrendCharts, User, Reading, Setting, OfficeBuilding, Download }
const route = useRoute()
const router = useRouter()
const routes = computed(() =>
  router.getRoutes().filter((r) => r.meta?.title && !r.meta?.hidden),
)
const topRoutes = computed(() => routes.value.filter((r) => !r.meta?.group))
const settingRoutes = computed(() => routes.value.filter((r) => r.meta?.group === '设置'))
</script>
