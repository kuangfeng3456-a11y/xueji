<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from './api'
import { store, logout, syncGoalSelection, notify, currentGoal } from './store'
import { visibleSections, visibleTabs } from './sections'
import GoalSwitcher from './components/GoalSwitcher.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'

const route = useRoute()
const router = useRouter()
const sidebarOpen = ref(false)

const activeSection = computed(() => route.meta.section || 'today')
/** 侧栏只列商用可见的板块；内部工具区不进导航。 */
const railSections = computed(() => visibleSections())
const tabCount = (section) => visibleTabs(section).length

const activeMeta = computed(() => ({
  title: route.meta.title || '今日',
  sub: route.meta.sub || ''
}))
const online = computed(() => Boolean(store.meta?.llm_enabled || store.health?.llm))
const degraded = computed(
  () =>
    store.health?.status === 'degraded' ||
    store.health?.database_fallback ||
    store.health?.database === 'sqlite-fallback'
)
const runtimeLabel = computed(() => {
  if (online.value) return '智能教练在线'
  return '智能教练备用中'
})

let healthTimer = 0

async function refreshRuntime() {
  try {
    const [meta, health] = await Promise.all([api.meta(), api.health()])
    store.meta = meta
    store.health = health
  } catch {
    /* 运行状态刷新失败不影响主流程 */
  }
}

async function boot() {
  if (!store.token) return
  try {
    const [goals, meta, health] = await Promise.all([
      api.goals(),
      api.meta(),
      api.health().catch(() => null)
    ])
    store.goals = goals
    store.meta = meta
    if (health) store.health = health
    syncGoalSelection()
    // 刷新用户信息：本地缓存的会话可能是旧结构（例如还没有 is_superadmin），
    // 以服务端为准，避免超管身份在旧缓存里丢失。失败不影响主流程。
    api
      .me()
      .then((me) => {
        if (me) store.user = me
      })
      .catch(() => {})
  } catch (e) {
    if (store.token) notify(e.message, true)
  }
}

function doLogout() {
  // 先让服务端撤销当前会话，再清本地：只删 localStorage 的话，
  // 那枚 token 在有效期内仍能被复制出去使用。
  api.logout().catch(() => {}).finally(() => {
    logout()
    router.push('/login')
  })
}

watch(
  () => store.token,
  (token) => {
    if (token) boot()
  }
)

onMounted(() => {
  boot()
  refreshRuntime()
  healthTimer = window.setInterval(refreshRuntime, 60000)
})

onBeforeUnmount(() => {
  if (healthTimer) window.clearInterval(healthTimer)
})
</script>

<template>
  <div v-if="route.meta.public">
    <router-view />
  </div>

  <div v-else class="shell">
    <div v-if="sidebarOpen" class="rail-mask" @click="sidebarOpen = false"></div>

    <aside class="rail" :class="{ open: sidebarOpen }">
      <div class="rail-brand">
        <div class="brand-mark" aria-hidden="true">学</div>
        <div class="brand-lockup">
          <div class="brand-cn">学迹</div>
          <div class="brand-en">XUEJI · ADAPTIVE COACH</div>
        </div>
      </div>

      <nav class="rail-nav">
        <router-link
          v-for="section in railSections"
          :key="section.key"
          :to="section.path"
          class="rail-item"
          :class="{ active: activeSection === section.key }"
          @click="sidebarOpen = false"
        >
          <span class="rail-index">{{ section.index }}</span>
          <span class="rail-text">
            <b>{{ section.title }}</b>
            <i>{{ section.sub }}</i>
          </span>
          <span class="rail-count">{{ tabCount(section) }}</span>
        </router-link>
      </nav>

      <div class="rail-foot">
        <div class="rail-user">
          {{ store.user?.nickname || store.user?.username }}
          <span v-if="store.user?.is_superadmin" class="rail-admin-badge">管理员</span>
        </div>
        <div class="rail-school">{{ store.user?.school || '未填写学校' }}</div>
        <div v-if="currentGoal()" class="rail-goal">
          {{ currentGoal().exam_name }} · 剩 {{ currentGoal().days_left }} 天
        </div>
        <div class="rail-status">
          <span class="status-dot" :class="online ? (degraded ? 'warn' : 'on') : 'off'"></span>
          {{ runtimeLabel }}
        </div>
        <button class="link-quiet rail-exit" @click="doLogout">退出登录</button>
      </div>
    </aside>

    <div class="stage">
      <div class="stage-head">
        <header class="stage-bar">
          <button
            class="menu-toggle"
            type="button"
            :aria-expanded="sidebarOpen ? 'true' : 'false'"
            aria-label="打开或关闭导航"
            @click="sidebarOpen = !sidebarOpen"
          >
            <span></span><span></span><span></span>
          </button>
          <div class="stage-crumb">
            <span>{{ activeMeta.title }}</span>
            <i>/</i>
            <b>{{ activeMeta.sub }}</b>
          </div>
          <div class="stage-tools">
            <GoalSwitcher />
          </div>
        </header>

        <div v-if="degraded" class="sys-banner" role="status">
          <span class="status-dot warn"></span>
          <p>
            云端同步暂时不可用，学习记录已改为本地保存，功能可以继续使用，恢复后会自动同步。
          </p>
        </div>
      </div>

      <main class="stage-body">
        <router-view v-slot="{ Component }">
          <transition name="page-fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
  </div>

  <div v-if="store.toast" class="toast" :class="{ error: store.toast.error }" role="status">
    {{ store.toast.message }}
  </div>

  <ConfirmDialog />
</template>
