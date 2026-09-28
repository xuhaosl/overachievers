import { createRouter, createWebHashHistory } from 'vue-router'
import Overview from './views/Overview.vue'
import ScoreEntry from './views/ScoreEntry.vue'
import ScoreList from './views/ScoreList.vue'
import Charts from './views/Charts.vue'
import Children from './views/Children.vue'
import Subjects from './views/Subjects.vue'
import Login from './views/Login.vue'

export default createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', component: Overview, meta: { title: '总览', icon: 'HomeFilled' } },
    { path: '/entry', component: ScoreEntry, meta: { title: '录成绩', icon: 'EditPen' } },
    { path: '/list', component: ScoreList, meta: { title: '成绩列表', icon: 'List' } },
    { path: '/charts', component: Charts, meta: { title: '曲线', icon: 'TrendCharts' } },
    { path: '/children', component: Children, meta: { title: '孩子管理', icon: 'User' } },
    { path: '/subjects', component: Subjects, meta: { title: '学科管理', icon: 'Reading' } },
    { path: '/login', component: Login, meta: { title: '登录', hidden: true } },
  ],
})
