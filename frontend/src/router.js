import { createRouter, createWebHashHistory } from 'vue-router'
import Overview from './views/Overview.vue'
import ScoreList from './views/ScoreList.vue'
import ScoreDetail from './views/ScoreDetail.vue'
import Charts from './views/Charts.vue'
import Children from './views/Children.vue'
import Subjects from './views/Subjects.vue'
import SubjectDetail from './views/SubjectDetail.vue'
import Classes from './views/Classes.vue'
import ClassDetail from './views/ClassDetail.vue'
import ChildDetail from './views/ChildDetail.vue'
import ExamDetail from './views/ExamDetail.vue'
import Backup from './views/Backup.vue'
import Login from './views/Login.vue'

export default createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', component: Overview, meta: { title: '总览', icon: 'HomeFilled' } },
    { path: '/exam/:id', component: ExamDetail, meta: { hidden: true } },
    { path: '/score/:id', component: ScoreDetail, meta: { hidden: true } },
    { path: '/list', component: ScoreList, meta: { title: '成绩列表', icon: 'List' } },
    { path: '/charts', component: Charts, meta: { title: '成长曲线', icon: 'TrendCharts' } },
    { path: '/children', component: Children, meta: { title: '孩子管理', icon: 'User', group: '设置' } },
    { path: '/subjects', component: Subjects, meta: { title: '学科管理', icon: 'Reading', group: '设置' } },
    { path: '/subject/:id', component: SubjectDetail, meta: { hidden: true } },
    { path: '/classes', component: Classes, meta: { title: '班级管理', icon: 'OfficeBuilding', group: '设置' } },
    { path: '/backup', component: Backup, meta: { title: '数据备份', icon: 'Download', group: '设置' } },
    { path: '/class/:id', component: ClassDetail, meta: { hidden: true } },
    { path: '/child/:id', component: ChildDetail, meta: { hidden: true } },
    { path: '/login', component: Login, meta: { title: '登录', hidden: true } },
  ],
})
