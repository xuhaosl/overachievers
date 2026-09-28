<template>
  <el-container class="layout" v-if="ready">
    <!-- 移动端顶栏 -->
    <el-header v-if="isMobile" class="mobile-header">
      <el-button :icon="Menu" text @click="drawer = true" />
      <span class="app-title">学生成绩助手</span>
      <span />
    </el-header>
    <el-drawer v-model="drawer" direction="ltr" size="200px" :with-header="false">
      <SideMenu @select="drawer = false" />
    </el-drawer>

    <!-- 桌面侧栏 -->
    <el-aside v-if="!isMobile" width="200px">
      <div class="logo">学生成绩助手</div>
      <SideMenu />
    </el-aside>

    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Menu } from '@element-plus/icons-vue'
import { api } from './api'
import SideMenu from './SideMenu.vue'

const ready = ref(false)
const isMobile = ref(window.innerWidth < 768)
const drawer = ref(false)
const router = useRouter()

const onResize = () => (isMobile.value = window.innerWidth < 768)
onMounted(async () => {
  window.addEventListener('resize', onResize)
  try {
    const { data } = await api.get('/meta')
    if (data.auth_required && !localStorage.getItem('sa_token')) {
      router.replace('/login')
      ready.value = true
      return
    }
  } catch {
    /* 后端未启动时也放行，页面会显示错误 */
  }
  ready.value = true
})
onUnmounted(() => window.removeEventListener('resize', onResize))
</script>

<style>
html,
body,
#app {
  height: 100%;
  margin: 0;
}
.layout {
  height: 100%;
}
.logo {
  font-weight: bold;
  font-size: 16px;
  padding: 16px;
  text-align: center;
}
.mobile-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--el-border-color-light);
}
.app-title {
  font-weight: bold;
}
.el-aside {
  border-right: 1px solid var(--el-border-color-light);
}
</style>
