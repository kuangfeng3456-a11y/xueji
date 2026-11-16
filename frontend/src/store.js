import { reactive } from 'vue'

const rawSession = localStorage.getItem('xueji_session') || sessionStorage.getItem('xueji_session')
let session = {}
try {
  session = rawSession ? JSON.parse(rawSession) : {}
} catch (e) {
  session = {}
}

const storedGoal = Number(localStorage.getItem('xueji_goal') || 0)

export const store = reactive({
  token: session.token || '',
  user: session.user || null,
  goals: [],
  currentGoalId: storedGoal > 0 ? storedGoal : null,
  meta: null,
  health: null,
  toast: null
})

let toastTimer = null

export function setSession(token, user, remember = true) {
  store.token = token
  store.user = user
  const storage = remember ? localStorage : sessionStorage
  const otherStorage = remember ? sessionStorage : localStorage
  storage.setItem('xueji_session', JSON.stringify({ token, user }))
  otherStorage.removeItem('xueji_session')
}

export function logout() {
  store.token = ''
  store.user = null
  store.goals = []
  store.currentGoalId = null
  store.health = null
  localStorage.removeItem('xueji_session')
  sessionStorage.removeItem('xueji_session')
  localStorage.removeItem('xueji_goal')
  // 通知外层取消在途请求（由 main.js 监听），避免旧会话数据回写
  if (typeof window !== 'undefined') window.dispatchEvent(new Event('xueji:logout'))
}

/** 局部更新当前用户信息（改昵称/学校后同步界面与本地会话）。 */
export function patchUser(patch) {
  store.user = { ...(store.user || {}), ...patch }
  for (const storage of [localStorage, sessionStorage]) {
    const raw = storage.getItem('xueji_session')
    if (!raw) continue
    try {
      const session = JSON.parse(raw)
      session.user = store.user
      storage.setItem('xueji_session', JSON.stringify(session))
    } catch (e) {
      /* 会话损坏时交给下一次登录覆盖 */
    }
  }
}

export function setGoal(id) {
  store.currentGoalId = id ? Number(id) : null
  if (store.currentGoalId) localStorage.setItem('xueji_goal', String(store.currentGoalId))
  else localStorage.removeItem('xueji_goal')
}

export function currentGoal() {
  return store.goals.find((goal) => goal.id === store.currentGoalId) || null
}

/** 平台超级管理员（开发者账号）：可见研发内部工具与管理后台。 */
export function isSuperadmin() {
  return Boolean(store.user && store.user.is_superadmin)
}

export function syncGoalSelection() {
  if (!store.goals.length) {
    store.currentGoalId = null
    return
  }
  const exists = store.goals.some((goal) => goal.id === store.currentGoalId)
  if (!exists) setGoal(store.goals[0].id)
}

export function notify(message, error = false) {
  store.toast = { message, error }
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    store.toast = null
  }, 3600)
}
