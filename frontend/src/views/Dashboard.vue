<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { store, notify } from '../store'
import DetailModal from '../components/DetailModal.vue'
import TaskPracticeModal from '../components/TaskPracticeModal.vue'
import CoachStream from '../components/CoachStream.vue'

const router = useRouter()
const loading = ref(true)
const data = ref(null)
const loadError = ref('')
const detail = ref(null)
const practiceTask = ref(null)
const openReason = ref(null)
const whyMap = ref({})
const whyLoading = ref(null)
const fatigue = ref(null)
const filtering = ref('todo')

// C3 实施意图微承诺
const commitments = ref({ items: [], active_count: 0, max_active: 5 })
const cSuggestions = ref([])
const cStats = ref(null)
const commitmentBusy = ref(false)

const ENERGY_LABELS = ['很差', '偏低', '一般', '不错', '充沛']
const PACE_OPTIONS = [
  { key: 'lighter', label: '明天轻一点' },
  { key: 'same', label: '保持节奏' },
  { key: 'heavier', label: '明天加一点' }
]
const MASTERY_LEVELS = [
  { key: 'unseen', label: '未学', color: '#d7d0c3', match: (v) => (v || 0) <= 0 },
  { key: 'begin', label: '初学', color: '#e8c9a0', match: (v) => v > 0 && v < 0.25 },
  { key: 'practice', label: '练习中', color: '#d4b15a', match: (v) => v >= 0.25 && v < 0.5 },
  { key: 'familiar', label: '较熟', color: '#7ea37a', match: (v) => v >= 0.5 && v < 0.75 },
  { key: 'mastered', label: '掌握', color: '#3f6f55', match: (v) => v >= 0.75 }
]

const review = ref(null)
const reviewBusy = ref(false)
const reviewForm = ref({
  energy: 3,
  hard_note: '',
  extra_learned: '',
  next_pace: 'same'
})


const TYPE_LABELS = {
  study: '学习',
  practice: '练习',
  review: '复习',
  remedial: '补救',
  mock: '模考'
}

const tasks = computed(() => data.value?.today_tasks || [])
const visibleTasks = computed(() => {
  if (filtering.value === 'done') return tasks.value.filter((t) => t.status === 'done')
  if (filtering.value === 'todo') return tasks.value.filter((t) => t.status !== 'done')
  return tasks.value
})
const doneCount = computed(() => tasks.value.filter((t) => t.status === 'done').length)
const completion = computed(() =>
  tasks.value.length ? Math.round((doneCount.value / tasks.value.length) * 100) : 0
)
const masteryAvg = computed(() => {
  const goal = data.value?.goal
  if (!goal) return 0
  return Math.round((goal.avg_mastery || 0) * 100)
})
const weakPoints = computed(() => (data.value?.weak_points || []).slice(0, 5))
const rhythm = computed(() => data.value?.rhythm)
const changes = computed(() => (data.value?.latest_changes || []).slice(0, 3))

const budgetMinutes = computed(() => data.value?.goal?.daily_minutes || data.value?.today_minutes || 0)
const timeAlloc = computed(() => {
  const groups = []
  const index = new Map()
  for (const task of tasks.value) {
    const key = task.type || 'study'
    if (!index.has(key)) {
      const row = { type: key, label: TYPE_LABELS[key] || key, planned: 0, done: 0 }
      index.set(key, row)
      groups.push(row)
    }
    const row = index.get(key)
    row.planned += task.duration_min || 0
    if (task.status === 'done') row.done += task.duration_min || 0
  }
  return groups
})
const typeGroups = computed(() => {
  const order = ['study', 'practice', 'review', 'remedial', 'mock']
  const map = new Map()
  for (const task of visibleTasks.value) {
    const key = task.type || 'study'
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(task)
  }
  const keys = [
    ...order.filter((key) => map.has(key)),
    ...[...map.keys()].filter((key) => !order.includes(key))
  ]
  return keys.map((key) => ({
    type: key,
    label: TYPE_LABELS[key] || key,
    minutes: map.get(key).reduce((sum, task) => sum + (task.duration_min || 0), 0),
    items: map.get(key)
  }))
})
const masteryLevels = computed(() => {
  const items = data.value?.mastery || []
  const total = items.length || 1
  return MASTERY_LEVELS.map((level) => {
    const count = items.filter((item) => level.match(item.value || 0)).length
    return { ...level, count, percent: Math.round((count / total) * 100) }
  })
})
const emptyPlanText = computed(() => {
  if (!tasks.value.length) {
    return '这里还没有任务。点击「补充 7 天计划」，系统会按优先级排入可用时间。'
  }
  if (filtering.value === 'todo') {
    return '今天的任务都完成了。花一分钟写下日复盘，明天会按你的节奏来排。'
  }
  if (filtering.value === 'done') {
    return '还没有已完成的任务。从第一条开始计时，或者勾选完成。'
  }
  return '这里还没有任务。'
})


function typeLabel(task) {
  return TYPE_LABELS[task.type] || task.type
}

async function toggleReason(task) {
  if (openReason.value === task.id) {
    openReason.value = null
    return
  }
  openReason.value = task.id
  if (whyMap.value[task.id] || !store.currentGoalId) return
  whyLoading.value = task.id
  try {
    const detail = await api.taskWhy(store.currentGoalId, task.id)
    whyMap.value = { ...whyMap.value, [task.id]: detail }
  } catch (e) {
    whyMap.value = { ...whyMap.value, [task.id]: { reason: task.reason, error: e.message } }
  } finally {
    whyLoading.value = null
  }
}

async function loadFatigue(goalId) {
  if (!goalId) {
    fatigue.value = null
    return
  }
  try {
    fatigue.value = await api.fatigueInfo(goalId)
  } catch {
    fatigue.value = null
  }
}

function openPoint(point) {
  detail.value = {
    title: point.kp_name,
    subtitle: '薄弱知识点',
    rows: [
      { label: '当前掌握度', value: `${Math.round((point.value || 0) * 100)}%` },
      { label: '下次复习', value: point.next_review_at || '尚未安排' },
      { label: '建议', value: '先做一次针对性自测，再到知识漏洞地图确认是否需要修复任务。' }
    ],
    linkTo: '/knowledge?tab=map',
    linkText: '打开知识漏洞地图'
  }
}

function openChange(change) {
  detail.value = {
    title: '计划调整说明',
    subtitle: '自动重排记录',
    rows: [
      { label: '调整内容', value: change.detail },
      { label: '调整依据', value: '剩余时间、逾期任务、错题增长与掌握度变化共同决定。' }
    ],
    linkTo: '/plan',
    linkText: '查看完整计划'
  }
}

async function load(goalId) {
  loading.value = true
  loadError.value = ''
  try {
    data.value = await api.dashboard(goalId || undefined)
    whyMap.value = {}
    openReason.value = null
    applyReview(data.value?.daily_review)
  } catch (e) {
    // 刷新失败时不静默保留旧数据：记下原因，页面顶部明确提示「可能不是最新」
    loadError.value = e.message
    if (!data.value) notify(e.message, true)
  } finally {
    loading.value = false
  }
}


function allocWidth(minutes) {
  const cap = Math.max(budgetMinutes.value || 1, data.value?.today_minutes || 1)
  return `${Math.min(100, Math.round((minutes / cap) * 100))}%`
}

function startFocusFor(task) {
  router.push({ path: '/today', query: { tab: 'focus', task: String(task.id) } })
}

function applyReview(row) {
  if (!row) {
    review.value = null
    return
  }
  review.value = row
  reviewForm.value = {
    energy: row.energy || 3,
    hard_note: row.hard_note || '',
    extra_learned: row.extra_learned || '',
    next_pace: row.next_pace || 'same'
  }
}

async function saveReview() {
  if (!store.currentGoalId || reviewBusy.value) return
  reviewBusy.value = true
  try {
    const row = await api.saveDailyReview(store.currentGoalId, { ...reviewForm.value })
    applyReview(row)
    notify('今日复盘已保存')
  } catch (e) {
    notify(e.message, true)
  } finally {
    reviewBusy.value = false
  }
}

async function changeTask(task, status) {
  try {
    await api.updateTask(store.currentGoalId, task.id, status)
    await load(store.currentGoalId)
  } catch (e) {
    notify(e.message, true)
  }
}

async function quickPlan() {
  if (!store.currentGoalId) return router.push('/plan?tab=goal')
  try {
    const result = await api.generatePlan(store.currentGoalId, { days: 7, regenerate: false })
    notify(result.summary)
    await load(store.currentGoalId)
  } catch (e) {
    notify(e.message, true)
  }
}

// ---- 微承诺：加载 / 采纳 / 打卡 / 取消 ----
async function loadCommitments(goalId) {
  if (!goalId) return
  try {
    const [today, sug] = await Promise.all([
      api.commitmentsToday(goalId),
      api.commitmentSuggestions(goalId)
    ])
    commitments.value = today
    cSuggestions.value = sug.suggestions || []
    // 履行率与相关性是沉淀指标，失败不阻断
    api
      .commitmentStats(goalId)
      .then((s) => (cStats.value = s))
      .catch(() => {})
  } catch (e) {
    // 微承诺加载失败不打断今日页主流程
  }
}

async function adopt(s) {
  if (commitmentBusy.value) return
  commitmentBusy.value = true
  try {
    await api.createCommitment({
      goal_id: store.currentGoalId,
      task_id: s.task_id,
      if_condition: s.if_condition,
      then_action: s.then_action,
      source: 'coach'
    })
    notify('承诺已生效，今天做到它')
    await loadCommitments(store.currentGoalId)
  } catch (e) {
    notify(e.message, true)
  } finally {
    commitmentBusy.value = false
  }
}

async function fulfillC(item) {
  if (commitmentBusy.value) return
  commitmentBusy.value = true
  try {
    await api.fulfillCommitment(item.id)
    notify('已记录：说到做到')
    await loadCommitments(store.currentGoalId)
  } catch (e) {
    notify(e.message, true)
  } finally {
    commitmentBusy.value = false
  }
}

async function cancelC(item) {
  if (commitmentBusy.value) return
  commitmentBusy.value = true
  try {
    await api.cancelCommitment(item.id)
    await loadCommitments(store.currentGoalId)
  } catch (e) {
    notify(e.message, true)
  } finally {
    commitmentBusy.value = false
  }
}

const COMMITMENT_STATES = { fulfilled: '已履行 ✓', missed: '未履行', cancelled: '已取消' }


const dueCards = ref(0)
const cloudHealth = ref(null)

async function loadDueCards(goalId) {
  if (!goalId) {
    dueCards.value = 0
    return
  }
  try {
    const deck = await api.flashcards(goalId, 50)
    const cards = deck.cards || []
    const today = new Date().toISOString().slice(0, 10)
    dueCards.value = cards.filter((card) => {
      if (card.due === true) return true
      if (card.due === false) return false
      const next = String(card.next_review_at || '').slice(0, 10)
      return !next || next <= today
    }).length
  } catch {
    dueCards.value = 0
  }
}


async function loadHealth() {
  try {
    cloudHealth.value = await api.health()
  } catch {
    cloudHealth.value = null
  }
}

const todayFocus = computed(() => {
  const name = weakPoints.value[0]?.kp_name
  const mistakes = data.value?.mistake_count_7d || 0
  if (name && mistakes) {
    return `今天优先补「${name}」等薄弱点；近 7 天有 ${mistakes} 道错题，会进入复盘并影响后面的安排。`
  }
  if (name) return `今天优先补「${name}」等薄弱点，看课和练习都会对着它来。`
  if (mistakes) {
    return `近 7 天有 ${mistakes} 道错题。先走完今日闭环，再在复盘里对错因下手。`
  }
  return '先走完看课、随堂测、口语跟读和复盘，学迹会根据结果调整后面的安排。'
})


watch(
  () => store.currentGoalId,
  (id) => {
    loadHealth()
    if (id) {
      load(id)
      loadCommitments(id)
      loadFatigue(id)
      loadDueCards(id)
    } else if (!store.goals.length) load()
  },
  { immediate: true }
)
</script>

<template>
  <div v-if="loading" class="skeleton-page" aria-busy="true" aria-label="正在读取今日学习状态">
    <div class="skeleton skeleton-hero"></div>
    <div class="skeleton-grid">
      <div class="skeleton skeleton-card"></div>
      <div class="skeleton skeleton-card"></div>
      <div class="skeleton skeleton-card"></div>
    </div>
  </div>

  <div v-else-if="!data?.goal" class="blank-state">
    <div class="blank-kicker">为什么用学迹</div>
    <h2>先设定一个考试目标，今天就开始对症学习</h2>
    <p>刷视频难以及时检验，单独刷题又对不上正在看的课。告诉学迹你考什么、何时考、每天能学多久，它会把看课、出题、跟读和错题复盘连成每天一条路径。</p>
    <div class="blank-actions">
      <router-link class="btn btn-solid" to="/plan?tab=goal">创建第一个目标</router-link>
      <router-link class="btn" to="/plan?tab=market">直接选学科包</router-link>
    </div>
    <ul class="blank-reasons">
      <li><strong>对上弱项</strong>课和题按你的知识点和错因来匹配</li>
      <li><strong>一条线走完</strong>看完就练，练完开口，不用切三个应用</li>
      <li><strong>记住你的错</strong>错题会改明天的安排，落后只是顺延</li>
    </ul>
    <ol class="blank-steps">
      <li><span>01</span>设定考试与每天能投入的时间</li>
      <li><span>02</span>导入资料或选学科包，抽出知识点</li>
      <li><span>03</span>按闭环学习：看课 → 出题 → 跟读 → 复盘</li>
    </ol>
  </div>

  <div v-else class="home">
    <div v-if="loadError" class="stale-banner" role="alert">
      <span>这页数据可能不是最新：{{ loadError }}</span>
      <button class="link-quiet" type="button" @click="load(store.currentGoalId)">重试</button>
    </div>
    <section class="lead">
      <div class="lead-copy">
        <div class="lead-eyebrow">{{ data.goal.exam_name }} · 还剩 {{ data.goal.days_left }} 天 · 已连续 {{ data.streak || 0 }} 天</div>
        <h2 class="lead-title">
          {{ data.user.nickname }}，还有 <em>{{ data.goal.days_left }}</em> 天
        </h2>
        <p class="lead-quote">{{ data.coach_message }}</p>
        <p class="lead-why">{{ todayFocus }}</p>
        <div class="lead-actions">
          <router-link class="btn btn-solid" to="/plan?tab=exam">开始今日课程</router-link>
          <button class="btn" @click="router.push('/today?tab=focus')">
            {{ data.goal.force_mode ? '进入强制学习' : '开始专注' }}
          </button>
          <button class="link-quiet" type="button" @click="quickPlan">补充 7 天计划</button>
          <router-link class="link-quiet" to="/plan">编辑计划</router-link>
        </div>
      </div>
      <dl class="lead-metrics">
        <div>
          <dt>今日完成</dt>
          <dd>{{ doneCount }}<span>/{{ tasks.length }}</span></dd>
          <small>{{ completion }}% 完成率</small>
        </div>
        <div>
          <dt>投入分钟</dt>
          <dd>{{ data.today_minutes }}<span>/{{ data.goal.daily_minutes }}</span></dd>
          <small>每日预算</small>
        </div>
        <div>
          <dt>平均掌握度</dt>
          <dd>{{ masteryAvg }}<span>%</span></dd>
          <small>{{ data.goal.knowledge_count }} 个知识点</small>
        </div>
        <div>
          <dt>近 7 天错题</dt>
          <dd>{{ data.mistake_count_7d }}</dd>
          <small>错因触发补救</small>
        </div>
      </dl>
    </section>

    <section class="demo-loop" aria-label="今日学习闭环">
      <header class="demo-loop-head">
        <div>
          <h3>今天就走完这一条</h3>
          <p>学迹要解决的是「看了、刷了，却对不上弱项」。下面四步连在一起，错的会回到明天的安排。</p>
        </div>
        <div class="demo-cloud">
          <router-link v-if="dueCards > 0" class="demo-cloud-chip ok" to="/today?tab=flashcards">
            今日待复习 {{ dueCards }} 张闪卡
          </router-link>
        </div>
      </header>
      <ol class="demo-steps">
        <li>
          <router-link to="/plan?tab=exam">
            <span class="demo-idx">01</span>
            <span class="demo-copy">
              <strong>看课</strong>
              <em>备考方案里课内播放本节视频</em>
            </span>
          </router-link>
        </li>
        <li>
          <router-link to="/plan?tab=exam">
            <span class="demo-idx">02</span>
            <span class="demo-copy">
              <strong>随堂测</strong>
              <em>看完立刻出 4 题，错的进入错题本</em>
            </span>
          </router-link>
        </li>
        <li>
          <router-link to="/today?tab=voice&mode=shadow">
            <span class="demo-idx">03</span>
            <span class="demo-copy">
              <strong>口语跟读</strong>
              <em>听标准音并跟读，当场看到发音反馈</em>
            </span>
          </router-link>
        </li>
        <li>
          <router-link to="/practice?tab=mistakes">
            <span class="demo-idx">04</span>
            <span class="demo-copy">
              <strong>复盘</strong>
              <em>查看错因与掌握度变化</em>
            </span>
          </router-link>
        </li>
      </ol>
    </section>

    <section
      v-if="fatigue?.fatigue && fatigue.fatigue.index >= 35"
      class="fatigue-banner"
      :class="{ urgent: fatigue.fatigue.index >= 60 }"
      role="status"
    >
      <div>
        <strong>疲劳指数 {{ fatigue.fatigue.index }}（{{ fatigue.fatigue.level }}）</strong>
        <p>{{ fatigue.fatigue.suggestion }}</p>
      </div>
      <router-link class="btn" :class="fatigue.fatigue.index >= 60 ? 'btn-solid' : ''" to="/collab?tab=rest">
        去恢复站
      </router-link>
    </section>

    <CoachStream :goal-id="store.currentGoalId" />

    <section class="home-grid">
      <div class="panel">
        <header class="panel-head">
          <div>
            <h3>今日计划</h3>
            <p>按类型分组。点「开始计时」会带着这条任务进入专注，结束后自动打卡。</p>
          </div>
          <div class="segmented">
            <button :class="{ on: filtering === 'todo' }" @click="filtering = 'todo'">待完成</button>
            <button :class="{ on: filtering === 'done' }" @click="filtering = 'done'">已完成</button>
            <button :class="{ on: filtering === 'all' }" @click="filtering = 'all'">全部</button>
          </div>
        </header>

        <div v-if="!visibleTasks.length" class="empty">{{ emptyPlanText }}</div>
        <div v-else class="today-board">
          <section v-for="group in typeGroups" :key="group.type" class="task-group">
            <header class="task-group-head">
              <h4>{{ group.label }}</h4>
              <span>{{ group.items.length }} 项 · {{ group.minutes }} 分钟</span>
            </header>
            <ol class="task-list">
              <li v-for="(task, index) in group.items" :key="task.id" class="task" :class="{ done: task.status === 'done' }">
            <div class="task-index">{{ String(index + 1).padStart(2, '0') }}</div>
            <div class="task-main">
              <div class="task-line">
                <span class="task-type">{{ typeLabel(task) }}</span>
                <span class="task-title">{{ task.title }}</span>
                <span class="task-min">{{ task.duration_min }}′</span>
              </div>
              <div class="task-meta">
                <button class="link-quiet" @click="toggleReason(task)">
                  {{ openReason === task.id ? '收起依据' : '为什么是它' }}
                </button>
                <button class="link-quiet" @click="practiceTask = task">练习一下</button>
              </div>
              <div v-if="openReason === task.id" class="task-why">
                <p class="task-reason">{{ (whyMap[task.id] && whyMap[task.id].reason) || task.reason }}</p>
                <p v-if="whyLoading === task.id" class="mini-note">正在用规则复算依据…</p>
                <template v-else-if="whyMap[task.id] && whyMap[task.id].why">
                  <dl class="why-facts">
                    <div>
                      <dt>期望增益</dt>
                      <dd>+{{ whyMap[task.id].why.expected_gain }} 分</dd>
                    </div>
                    <div>
                      <dt>收益密度</dt>
                      <dd>{{ whyMap[task.id].why.density }}</dd>
                    </div>
                    <div>
                      <dt>掌握度 ± 不确定性</dt>
                      <dd>
                        {{ Math.round((whyMap[task.id].why.mastery || 0) * 100) }}%
                        ±{{ Math.round((whyMap[task.id].why.uncertainty || 0) * 1000) / 10 }}
                      </dd>
                    </div>
                    <div>
                      <dt>当前保持率</dt>
                      <dd>{{ Math.round((whyMap[task.id].retention_now || whyMap[task.id].why.retention || 0) * 100) }}%</dd>
                    </div>
                  </dl>
                  <p v-if="whyMap[task.id].why.if_skipped" class="why-counter">{{ whyMap[task.id].why.if_skipped.summary }}</p>
                  <p v-if="whyMap[task.id].why.if_delayed_1d" class="why-counter">{{ whyMap[task.id].why.if_delayed_1d.summary }}</p>
                  <p class="mini-note">{{ whyMap[task.id].why.formula }}</p>
                </template>
                <p v-else-if="whyMap[task.id] && whyMap[task.id].error" class="mini-note">{{ whyMap[task.id].error }}</p>
              </div>
            </div>
            <div class="task-actions">
              <button
                v-if="task.status !== 'done'"
                class="btn btn-sm btn-solid"
                type="button"
                title="开始专注计时"
                @click="startFocusFor(task)"
              >开始计时</button>
              <button
                v-if="task.status !== 'done'"
                class="icon-btn"
                title="标记完成"
                @click="changeTask(task, 'done')"
              >✓</button>
              <button
                v-else
                class="icon-btn undo"
                title="撤销完成"
                @click="changeTask(task, 'pending')"
              >↺</button>
              <button
                v-if="task.status !== 'skipped'"
                class="icon-btn quiet"
                title="跳过"
                @click="changeTask(task, 'skipped')"
              >—</button>
            </div>
          </li>
        </ol>
          </section>
        </div>
      </div>

      <aside class="home-side">
        <section class="panel">
          <header class="panel-head slim">
            <h3>今日时间分配</h3>
            <span class="mini-note">{{ data.today_minutes }} / {{ data.goal.daily_minutes }} 分钟</span>
          </header>
          <div v-if="!timeAlloc.length" class="empty">还没有可分配的任务。</div>
          <ul v-else class="alloc-list">
            <li v-for="row in timeAlloc" :key="row.type">
              <div class="alloc-line">
                <span>{{ row.label }}</span>
                <strong>{{ row.done }}/{{ row.planned }}′</strong>
              </div>
              <div class="alloc-track">
                <i class="alloc-planned" :style="{ width: allocWidth(row.planned) }"></i>
                <i class="alloc-done" :style="{ width: allocWidth(row.done) }"></i>
              </div>
            </li>
          </ul>
        </section>

        <section class="panel">
          <header class="panel-head slim">
            <h3>今日复盘</h3>
            <span v-if="review" class="mini-note">已保存</span>
          </header>
          <p class="mini-note">花一分钟记下今天的状态，明天排任务时会参考。</p>
          <div class="energy-pills">
            <button
              v-for="n in 5"
              :key="n"
              type="button"
              :class="{ on: reviewForm.energy === n }"
              @click="reviewForm.energy = n"
            >{{ ENERGY_LABELS[n - 1] }}</button>
          </div>
          <label class="review-field">
            今天最吃力的地方
            <textarea v-model="reviewForm.hard_note" maxlength="500" rows="2" placeholder="比如哪一类题、哪一章卡住了"></textarea>
          </label>
          <label class="review-field">
            额外学会了什么
            <textarea v-model="reviewForm.extra_learned" maxlength="500" rows="2" placeholder="计划外的收获，可留空"></textarea>
          </label>
          <div class="segmented pace-seg">
            <button
              v-for="opt in PACE_OPTIONS"
              :key="opt.key"
              type="button"
              :class="{ on: reviewForm.next_pace === opt.key }"
              @click="reviewForm.next_pace = opt.key"
            >{{ opt.label }}</button>
          </div>
          <button class="btn btn-solid btn-block" type="button" :disabled="reviewBusy" @click="saveReview">
            {{ review ? '更新复盘' : '保存复盘' }}
          </button>
          <p v-if="review && review.suggestion" class="review-tip">{{ review.suggestion }}</p>
        </section>

        <section class="panel">
          <header class="panel-head slim">
            <h3>今日微承诺</h3>
            <span v-if="cStats && cStats.fulfillment_rate != null" class="mini-note">
              28 天履行率 {{ Math.round(cStats.fulfillment_rate * 100) }}%
            </span>
          </header>
          <ul v-if="commitments.items.length" class="commit-list">
            <li v-for="c in commitments.items" :key="c.id" class="commit-item" :class="'is-' + c.status">
              <p class="commit-text">
                <b>如果</b> {{ c.if_condition }}，<b>那么</b> {{ c.then_action }}
              </p>
              <div v-if="c.status === 'pending'" class="commit-actions">
                <button class="btn btn-sm btn-solid" :disabled="commitmentBusy" @click="fulfillC(c)">做到了</button>
                <button class="btn btn-sm btn-ghost" :disabled="commitmentBusy" @click="cancelC(c)">取消</button>
              </div>
              <span v-else class="commit-state">{{ COMMITMENT_STATES[c.status] }}</span>
            </li>
          </ul>
          <div v-else class="empty">今天还没有承诺。挑一条教练建议，把「我要学」变成「如果—那么」。</div>
          <div
            v-if="cSuggestions.length && commitments.active_count < commitments.max_active"
            class="commit-suggest"
          >
            <div class="mini-note">教练建议 · 挑一条就够</div>
            <div v-for="(s, i) in cSuggestions" :key="i" class="commit-suggest-item">
              <p>{{ s.if_condition }}，{{ s.then_action }}</p>
              <button class="btn btn-sm" :disabled="commitmentBusy" @click="adopt(s)">采纳</button>
            </div>
          </div>
          <p v-else-if="commitments.active_count >= commitments.max_active" class="mini-note">
            已有 {{ commitments.active_count }} 条待履行承诺——微承诺贵精不贵多，先完成一条。
          </p>
        </section>

        <section class="panel">
          <header class="panel-head slim">
            <h3>掌握进度</h3>
            <router-link class="link-quiet" to="/knowledge?tab=map">知识地图 →</router-link>
          </header>
          <div v-if="(data.mastery || []).length" class="level-stack">
            <div class="level-bar">
              <i
                v-for="level in masteryLevels"
                :key="level.key"
                :style="{ width: level.percent + '%', background: level.color }"
                :title="level.label + ' ' + level.count"
              ></i>
            </div>
            <ul class="level-legend">
              <li v-for="level in masteryLevels" :key="level.key">
                <i :style="{ background: level.color }"></i>{{ level.label }} {{ level.count }}
              </li>
            </ul>
          </div>
          <div v-if="!weakPoints.length" class="empty">暂无掌握度数据。</div>
          <ul v-else class="rank-list">
            <li v-for="point in weakPoints" :key="point.kp_id" @click="openPoint(point)">
              <div class="rank-line">
                <span>{{ point.kp_name }}</span>
                <strong>{{ Math.round((point.value || 0) * 100) }}%</strong>
              </div>
              <div class="hairline-bar"><i :style="{ width: Math.round((point.value || 0) * 100) + '%' }"></i></div>
            </li>
          </ul>
        </section>

        <section class="panel">
          <header class="panel-head slim">
            <h3>学习节奏</h3>
            <span class="mini-note">{{ data.streak }} 天连续</span>
          </header>
          <dl class="fact-list" v-if="rhythm">
            <div><dt>常学时段</dt><dd>{{ (rhythm.peak_hours || []).join('、') || '尚未形成' }}</dd></div>
            <div><dt>平均拖延</dt><dd>{{ rhythm.avg_delay_days }} 天</dd></div>
            <div><dt>近 28 天完成率</dt><dd>{{ Math.round((rhythm.completion_rate || 0) * 100) }}%</dd></div>
          </dl>
          <div v-else class="empty">再积累几天数据就能看出节奏。</div>
        </section>

        <section class="panel">
          <header class="panel-head slim">
            <h3>最近调整</h3>
            <router-link class="link-quiet" to="/plan">记录 →</router-link>
          </header>
          <div v-if="!changes.length" class="empty">暂未发生重排。</div>
          <ul v-else class="note-list">
            <li v-for="change in changes" :key="change.id || change.detail" @click="openChange(change)">
              {{ change.detail }}
            </li>
          </ul>
        </section>
      </aside>
    </section>

  </div>

  <DetailModal
    v-if="detail"
    :open="Boolean(detail)"
    :title="detail.title"
    :subtitle="detail.subtitle"
    :rows="detail.rows"
    :link-to="detail.linkTo"
    :link-text="detail.linkText"
    @close="detail = null"
  />
  <TaskPracticeModal
    v-if="practiceTask"
    :task="practiceTask"
    :goal-id="store.currentGoalId"
    @close="practiceTask = null"
    @done="load(store.currentGoalId)"
  />
</template>

<style scoped>
.fatigue-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin: 16px 0 0;
  padding: 14px 18px;
  border-radius: 14px;
  background: #f7f4ec;
  border: 1px solid #e6dfd0;
}
.fatigue-banner.urgent {
  background: #f8eee8;
  border-color: #e8cfc2;
}
.fatigue-banner p {
  margin: 4px 0 0;
  color: inherit;
  opacity: 0.85;
}
.task-why {
  margin-top: 8px;
}
.why-facts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 16px;
  margin: 8px 0;
}
.why-facts dt {
  font-size: 12px;
  opacity: 0.7;
}
.why-facts dd {
  margin: 0;
  font-weight: 600;
}
.why-counter {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.5;
}

.today-board {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.task-group-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin: 0 0 8px;
}
.task-group-head h4 {
  margin: 0;
  font-size: 13px;
  letter-spacing: 0.04em;
}
.task-group-head span {
  font-size: 12px;
  opacity: 0.65;
}
.task-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.alloc-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.alloc-line {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
}
.alloc-track {
  position: relative;
  height: 8px;
  margin-top: 6px;
  border-radius: 99px;
  background: #efe8db;
  overflow: hidden;
}
.alloc-track i {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  border-radius: 99px;
}
.alloc-planned {
  background: #d8c7a5;
}
.alloc-done {
  background: #3f6f55;
}
.energy-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 10px 0 12px;
}
.energy-pills button {
  border: 1px solid #e6dfd0;
  background: #fff;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
}
.energy-pills button.on {
  background: #2d3a31;
  color: #f7f4ec;
  border-color: #2d3a31;
}
.review-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0 0 10px;
  font-size: 12px;
  opacity: 0.9;
}
.review-field textarea {
  width: 100%;
  resize: vertical;
  min-height: 56px;
  border: 1px solid #e6dfd0;
  border-radius: 10px;
  padding: 8px 10px;
  font: inherit;
  background: #fffdf8;
}
.pace-seg {
  margin: 0 0 12px;
}
.review-tip {
  margin: 10px 0 0;
  font-size: 13px;
  line-height: 1.55;
}
.level-stack {
  margin: 0 0 12px;
}
.level-bar {
  display: flex;
  height: 10px;
  border-radius: 99px;
  overflow: hidden;
  background: #efe8db;
}
.level-bar i {
  display: block;
  height: 100%;
}
.level-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  font-size: 12px;
}
.level-legend i {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 99px;
  margin-right: 4px;
}

.lead-why {
  margin: 8px 0 0;
  color: var(--ink-2, #4b5563);
  font-size: 14px;
  line-height: 1.7;
}
.demo-loop {
  margin-top: 18px;
  padding: 16px 18px 14px;
  border: 1px solid var(--line, #e6e1d8);
  border-radius: 16px;
  background: var(--surface, #fff);
}
.demo-loop-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 12px;
}
.demo-loop-head h3 {
  margin: 0;
  font-size: 16px;
}
.demo-loop-head p {
  margin: 4px 0 0;
  color: var(--muted, #6b7280);
  font-size: 13px;
}
.demo-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
}
.demo-cloud-chip {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #f3f4f6;
  color: #6b7280;
}
.demo-cloud-chip.ok {
  background: #ecfdf3;
  color: #067647;
}
.demo-steps {
  list-style: none;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
  padding: 0;
}
.demo-steps a {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 10px;
  border: 1px solid var(--line, #e6e1d8);
  border-radius: 12px;
  text-decoration: none;
  color: inherit;
  min-height: 88px;
  background: var(--surface-2, #fafaf7);
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}
.demo-steps a:hover {
  border-color: var(--blue, #2563eb);
  box-shadow: 0 8px 18px -14px rgba(37, 99, 235, 0.6);
  transform: translateY(-1px);
}
.demo-idx {
  flex: none;
  font-size: 12px;
  font-weight: 700;
  color: var(--blue, #2563eb);
}
.demo-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.demo-copy strong {
  font-size: 14px;
}
.demo-copy em {
  font-style: normal;
  font-size: 12px;
  color: var(--muted, #6b7280);
  line-height: 1.45;
}
@media (max-width: 900px) {
  .demo-steps {
    grid-template-columns: 1fr 1fr;
  }
  .demo-loop-head {
    flex-direction: column;
  }
}
</style>
