import { createRouter, createWebHashHistory } from 'vue-router'
import { store } from './store'
import { LEGACY_ROUTES, SECTIONS, sectionByKey } from './sections'
import SectionView from './components/SectionView.vue'
import Login from './views/Login.vue'
import Recover from './views/Recover.vue'

const routes = [
  {
    path: '/login',
    component: Login,
    meta: { public: true, title: '登录' }
  },
  {
    path: '/recover',
    component: Recover,
    meta: { public: true, title: '找回密码' }
  },
  ...SECTIONS.map((section) => ({
    path: section.path,
    component: SectionView,
    meta: { title: section.title, sub: section.sub, section: section.key }
  })),
  ...Object.entries(LEGACY_ROUTES).map(([path, [sectionKey, tabKey]]) => {
    const section = sectionByKey(sectionKey)
    const isDefault = section && tabKey === section.tabs[0].key
    return {
      path,
      redirect: isDefault ? { path: section.path } : { path: section.path, query: { tab: tabKey } }
    }
  }),
  { path: '/:pathMatch(.*)*', redirect: '/today' }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

router.beforeEach((to) => {
  if (!to.meta.public && !store.token) return { path: '/login' }
  if (to.meta.public && store.token) return { path: '/today' }
  return true
})

export default router
