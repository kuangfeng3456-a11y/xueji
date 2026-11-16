<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'
import { confirmAction } from '../confirm'
import AppSelect from '../components/AppSelect.vue'
import TaskCard from '../components/TaskCard.vue'
import DetailModal from '../components/DetailModal.vue'
import TaskPracticeModal from '../components/TaskPracticeModal.vue'

const tasks = ref([])
const loading = ref(true)
const showAllDays = ref(false)
const busy = ref(false)
const days = ref(7)
const dayOptions = [
  { value: 7, label: '7 天' },
  { value: 14, label: '14 天' },
  { value: 21, label: '21 天' }
]
const filter = ref('all')
const changes = ref([])
const lastSummary = ref('')
const detail = ref(null)
const practiceTask = ref(null)
const preview = ref(null)

const filtered = computed(() => {
  if (filter.value === 'pending') return tasks.value.filter((t) => t.status === 'pending')
  if (filter.value === 'done') return tasks.value.filter((t) => t.status === 'done')
  return tasks.value
})

const groups = computed(() => {
  const map = new Map()
  for (const task of filtered.value) {
    if (!map.has(task.day)) map.set(task.day, [])
    map.get(task.day).push(task)
  }
  return [...map.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1))
})

const unfinished = computed(() => tasks.value.filter((t) => t.status === 'pending').length)

const todayStr = new Date().toISOString().slice(0, 10)
const todayCount = computed(() => tasks.value.filter((t) => t.day === todayStr).length)
const completionRate = computed(() => {
  if (!tasks.value.length) return 0
  return Math.round(tasks.value.filter((t) => t.status === 'done').length / tasks.value.length * 100)
})
const totalMinutes = computed(() => tasks.value.reduce((sum, t) => sum + t.duration_min, 0))

const typeStats = computed(() => {
  const map = {}
  for (const t of tasks.value) map[t.type] = (map[t.type] || 0) + 1
  return Object.entries(map).map(([type, count]) => ({ type, count }))
})

const statusStats = computed(() => {
  const map = {}
  for (const t of tasks.value) map[t.status] = (map[t.status] || 0) + 1
  return Object.entries(map).map(([status, count]) => ({ status, count }))
})

const avgDuration = computed(() => {
  if (!tasks.value.length) return 0
  return Math.round(totalMinutes.value / tasks.value.length)
})

const typeLabelMap = { study: '学习', review: '复习', practice: '练习', remedial: '补救' }
const statusLabelMap = { pending: '待完成', done: '已完成', skipped: '已跳过' }

function formatDay(day) {
  const [y, m, d] = day.split('-').map(Number)
  const target = new Date(y, m - 1, d)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const diff = Math.round((target - today) / 86400000)
  const week = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][target.getDay()]
  const prefix = diff === 0 ? '今天 · ' : diff === 1 ? '明天 · ' : diff === -1 ? '昨天 · ' : ''
  return `${prefix}${m} 月 ${d} 日 ${week}`
}

function dayStats(items) {
  const done = items.filter((t) => t.status === 'done').length
  const minutes = items.reduce((sum, t) => sum + t.duration_min, 0)
  return `${done}/${items.length} 完成 · ${minutes} 分钟`
}

async function load() {
  if (!store.currentGoalId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    tasks.value = await api.tasks(store.currentGoalId)
    await loadPreview()
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function generate(regenerate = false) {
  if (!store.currentGoalId) return
  if (regenerate) {
    const ok = await confirmAction({
      title: '重新生成计划',
      message: '重新生成会删除今天及以后尚未完成的计划任务。',
      detail: '已完成的任务与历史记录会保留，错题与掌握度不受影响。',
      confirmText: '重新生成',
      danger: true
    })
    if (!ok) return
  }
  busy.value = true
  try {
    const result = await api.generatePlan(store.currentGoalId, { days: days.value, regenerate })
    lastSummary.value = result.summary
    notify(result.summary)
    await load()
    await refreshGoals()
  } catch (e) {
    notify(e.message, true)
  } finally {
    busy.value = false
  }
}

async function doReplan() {
  if (!store.currentGoalId) return
  busy.value = true
  try {
    const result = await api.replan(store.currentGoalId, 'manual')
    changes.value = result.changes
    notify(result.changes[0]?.detail || '重排完成')
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    busy.value = false
  }
}

async function changeTask({ task, status }) {
  try {
    const extra = status === 'skipped' ? { skip_reason: '计划页临时跳过' } : {}
    await api.updateTask(store.currentGoalId, task.id, status, extra)
    await load()
  } catch (e) {
    notify(e.message, true)
  }
}

async function changeFeedback({ task, feedback }) {
  try {
    await api.updateTask(store.currentGoalId, task.id, 'done', { feedback })
    await load()
  } catch (e) {
    notify(e.message, true)
  }
}

async function changeTier({ task, minutes }) {
  try {
    await api.setTaskMinutes(store.currentGoalId, task.id, minutes)
    notify(`已降档为 ${minutes} 分钟，保持连续性`)
    await load()
  } catch (e) {
    notify(e.message, true)
  }
}

async function openTask(task) {
  const typeLabel = { study: '学习', review: '复习', practice: '练习', remedial: '补救' }
  const statusLabel = { pending: '待完成', done: '已完成', skipped: '已跳过' }
  const feedbackLabel = { easy: '简单', ok: '刚好', hard: '偏难' }
  const baseRows = [
    { label: '日期', value: task.day },
    { label: '类型', value: typeLabel[task.type] || task.type },
    { label: '时长', value: task.duration_min + ' 分钟' },
    { label: '状态', value: statusLabel[task.status] || task.status },
    { label: '知识点', value: task.kp_name || '未关联' },
    { label: '优先级', value: task.priority ? task.priority.toFixed(2) : '—' },
    { label: '来源', value: task.source || '—' },
    { label: '排程理由', value: task.reason || '—' },
    ...(task.skip_reason ? [{ label: '跳过原因', value: task.skip_reason }] : []),
    ...(task.feedback ? [{ label: '难度反馈', value: feedbackLabel[task.feedback] || task.feedback }] : [])
  ]
  detail.value = {
    title: task.title,
    subtitle: `${typeLabel[task.type] || task.type} · ${task.duration_min} 分钟 · ${statusLabel[task.status] || task.status}`,
    rows: baseRows
  }
  try {
    const data = await api.taskWhy(store.currentGoalId, task.id)
    const why = data.why || {}
    const tiers = data.tiers || {}
    detail.value = {
      ...detail.value,
      rows: [
        ...baseRows,
        { label: '任务三档', value: `标准 ${tiers.standard} · 精简 ${tiers.lite} · 最小 ${tiers.minimal} 分钟` },
        { label: '当前保持率', value: `${Math.round((data.retention_now || 0) * 100)}%（稳定度 ${data.stability_days} 天）` },
        { label: '期望增益', value: `+${why.expected_gain} 分` },
        { label: '收益密度', value: `${why.density}（价值 ${why.value} ÷ ${why.minutes} 分钟）` },
        { label: '如果今天跳过', value: (why.if_skipped && why.if_skipped.summary) || '—' },
        { label: '如果推迟 1 天', value: (why.if_delayed_1d && why.if_delayed_1d.summary) || '—' },
        { label: '如果改最小档', value: (why.if_min_tier && why.if_min_tier.summary) || '—' },
        { label: '为什么（可复算）', value: why.formula || '—' }
      ]
    }
  } catch (e) {
    notify(e.message, true)
  }
}

async function refreshGoals() {
  try {
    store.goals = await api.goals()
  } catch (e) {
    /* ignore */
  }
}

async function loadPreview() {
  if (!store.currentGoalId) return
  try {
    preview.value = await api.schedulePreview(store.currentGoalId, 8, 20)
  } catch (e) {
    preview.value = null
  }
}

watch(() => store.currentGoalId, load, { immediate: true })
</script>

<template>
  <div class="plan-root">
    <div v-if="!store.currentGoalId" class="empty">
      还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建一个。
    </div>

    <div v-else class="stack">
      <div class="card">
        <div class="row-between" style="flex-wrap: wrap">
          <div>
            <div class="card-title">排期</div>
            <div class="card-sub">{{ tasks.length }} 个任务 · {{ unfinished }} 个待完成</div>
          </div>
          <div class="row">
            <AppSelect v-model="days" :options="dayOptions" style="width: 110px" />
            <button class="btn" :disabled="busy" @click="generate(false)">
              {{ busy ? '处理中...' : '生成计划' }}
            </button>
            <button class="btn btn-ghost" :disabled="busy" @click="generate(true)">重新生成</button>
            <button class="btn btn-teal" :disabled="busy" @click="doReplan">智能重排</button>
          </div>
        </div>

        <div v-if="lastSummary" class="task-reason" style="margin-top: 12px">{{ lastSummary }}</div>
        <div v-if="changes.length" class="stack" style="margin-top: 10px">
          <div v-for="(change, index) in changes.slice(0, 3)" :key="index" class="small muted">· {{ change.detail }}</div>
        </div>
      </div>

      <div class="row" style="gap: 22px; flex-wrap: wrap">
        <span class="small">今日 <b>{{ todayCount }}</b></span>
        <span class="small">完成率 <b>{{ completionRate }}%</b></span>
        <span class="small">总时长 <b>{{ totalMinutes }}</b> 分钟</span>
        <span class="small">待完成 <b>{{ unfinished }}</b></span>
      </div>

      <div class="row" style="justify-content: space-between">
        <div class="chip-list">
          <button class="chip" :class="{ active: filter === 'all' }" @click="filter = 'all'">全部</button>
          <button class="chip" :class="{ active: filter === 'pending' }" @click="filter = 'pending'">待完成</button>
          <button class="chip" :class="{ active: filter === 'done' }" @click="filter = 'done'">已完成</button>
        </div>
        <span class="small muted">共 {{ filtered.length }} 个任务</span>
      </div>

      <div v-if="loading" class="empty">正在加载计划...</div>
      <div v-else-if="!groups.length" class="empty">
        还没有任务。选择天数后点击「生成计划」。
      </div>

      <div v-else class="stack">
        <div v-for="[day, items] in (showAllDays ? groups : groups.slice(0, 3))" :key="day" class="day-block">
          <div class="day-head">
            <span>{{ formatDay(day) }}</span>
            <span class="small muted">{{ dayStats(items) }}</span>
          </div>
          <div class="day-body">
            <TaskCard v-for="task in items" :key="task.id" :task="task" :show-tier="true" @change="changeTask" @feedback="changeFeedback" @detail="openTask" @tier="changeTier" />
          </div>
        </div>
      </div>

      <div v-if="groups.length > 3" class="row" style="justify-content: center">
        <button class="btn btn-ghost btn-sm" @click="showAllDays = !showAllDays">
          {{ showAllDays ? '收起，只看前 3 天' : `展开全部 ${groups.length} 天` }}
        </button>
      </div>

      <TaskPracticeModal
        v-if="practiceTask"
        :task="practiceTask"
        :goal-id="store.currentGoalId"
        @close="practiceTask = null"
        @done="load"
      />

      <DetailModal
        :open="Boolean(detail)"
        :title="detail?.title || ''"
        :subtitle="detail?.subtitle || ''"
        :rows="detail?.rows || []"
        @close="detail = null"
      />
    </div>
  </div>
</template>
