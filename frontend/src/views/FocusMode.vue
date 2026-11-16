<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { store, notify } from '../store'
import { confirmAction } from '../confirm'
import AppSelect from '../components/AppSelect.vue'

const router = useRouter()
const route = useRoute()
const queryHint = ref('')
const loading = ref(true)
const busy = ref(false)
const tasks = ref([])
const violations = ref([])
const history = ref([])
const summary = ref(null)
const session = ref(null)
const selectedTaskId = ref('')
const plannedMinutes = ref(25)
const taskOptions = computed(() => [
  { value: '', label: '自由学习（不绑定任务）' },
  ...tasks.value.map((task) => ({
    value: String(task.id),
    label: `${task.title} · ${task.duration_min} 分钟`
  }))
])
const cameraOn = ref(false)
const cameraError = ref('')
const presenceNote = ref('')
const remaining = ref(0)
const leaves = ref(0)
const videoRef = ref(null)
const noise = ref('none')
const noiseOptions = [
  { key: 'none', label: '静音' },
  { key: 'rain', label: '雨声' },
  { key: 'cafe', label: '咖啡厅' },
  { key: 'tone', label: '纯音 432Hz' }
]

let stream = null
let tickTimer = null
let snapshotTimer = null
let startedAt = 0
let audioCtx = null
let noiseSource = null

const goal = computed(() => store.goals.find((item) => item.id === store.currentGoalId) || null)
const isActive = computed(() => session.value?.status === 'active')
const pendingCount = computed(() => tasks.value.length)
const progress = computed(() => {
  if (!session.value) return 0
  const total = Math.max(session.value.planned_minutes * 60, 1)
  return Math.min(100, Math.round(((total - remaining.value) / total) * 100))
})
const timeText = computed(() => {
  const minutes = Math.floor(remaining.value / 60)
  const seconds = remaining.value % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
})
const todayViolations = computed(() => violations.value.filter((item) => item.day === todayISO()))
const forceMode = computed(() => Boolean(goal.value?.force_mode))
const typeLabel = { study: '学习', review: '复习', practice: '练习', remedial: '补救' }

function todayISO() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}


function applyTaskFromQuery() {
  const raw = route.query.task
  queryHint.value = ''
  if (raw == null || raw === '') return false
  const id = String(Array.isArray(raw) ? raw[0] : raw)
  const found = tasks.value.find((task) => String(task.id) === id)
  if (found) {
    selectedTaskId.value = id
    plannedMinutes.value = Math.min(Math.max(found.duration_min || 25, 5), 120)
    queryHint.value = `已选中「${found.title}」，确认时长后开始即可。`
    return true
  }
  queryHint.value = '这条任务不在今日待办里，可能已经完成，请重新选一条。'
  return false
}

async function load() {
  if (!store.currentGoalId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const [all, violationList, historyList, stat] = await Promise.all([
      api.tasks(store.currentGoalId),
      api.violations(store.currentGoalId),
      api.focusHistory(store.currentGoalId),
      api.focusSummary(store.currentGoalId).catch(() => null)
    ])
    tasks.value = all.filter((task) => task.day === todayISO() && task.status === 'pending')
    violations.value = violationList
    history.value = historyList
    summary.value = stat
    if (!applyTaskFromQuery() && !selectedTaskId.value && tasks.value.length) {
      selectedTaskId.value = String(tasks.value[0].id)
      plannedMinutes.value = Math.min(Math.max(tasks.value[0].duration_min, 5), 120)
    }
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function restoreActive() {
  try {
    const active = await api.activeFocus(store.currentGoalId)
    if (!active) return
    session.value = active
    remaining.value = active.remaining_seconds
    leaves.value = active.leaves
    startedAt = Date.now() - (active.planned_minutes * 60 - active.remaining_seconds) * 1000
    if (active.camera_enabled) {
      cameraOn.value = true
      await nextTick()
      await openCamera()
    }
  } catch (e) {
    /* ignore */
  }
}

async function start() {
  busy.value = true
  try {
    if (goal.value?.camera_required && !cameraOn.value) {
      const ok = await openCamera()
      if (!ok) {
        notify('该目标要求摄像头监督，请允许摄像头后再开始', true)
        return
      }
    }
    const data = await api.startFocus({
      goal_id: store.currentGoalId,
      task_id: selectedTaskId.value ? Number(selectedTaskId.value) : null,
      planned_minutes: Number(plannedMinutes.value),
      camera_enabled: cameraOn.value
    })
    session.value = data
    remaining.value = data.remaining_seconds
    startedAt = Date.now()
    leaves.value = 0
    if (cameraOn.value) {
      await nextTick()
      await openCamera()
    }
    notify('强制学习已开始，离开页面会被记录')
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    busy.value = false
  }
}

function bindVideo() {
  if (videoRef.value && stream) {
    videoRef.value.srcObject = stream
    const playPromise = videoRef.value.play?.()
    if (playPromise && playPromise.catch) playPromise.catch(() => {})
  }
}

async function openCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    cameraError.value = '当前浏览器不支持摄像头，或页面不在安全上下文中'
    cameraOn.value = false
    notify(cameraError.value, true)
    return false
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 } },
      audio: false
    })
    cameraOn.value = true
    cameraError.value = ''
    await nextTick()
    bindVideo()
    startSnapshotLoop()
    return true
  } catch (e) {
    cameraError.value = '摄像头开启失败：' + (e.message || '请检查浏览器权限')
    cameraOn.value = false
    notify(cameraError.value, true)
    return false
  }
}

function stopCamera() {
  if (stream) {
    stream.getTracks().forEach((track) => track.stop())
    stream = null
  }
  if (snapshotTimer) {
    clearInterval(snapshotTimer)
    snapshotTimer = null
  }
  cameraOn.value = false
}

async function toggleCamera() {
  if (cameraOn.value) {
    stopCamera()
  } else {
    await openCamera()
  }
}

function startSnapshotLoop() {
  if (snapshotTimer) clearInterval(snapshotTimer)
  snapshotTimer = setInterval(captureSnapshot, 60000)
}

let lastLuma = null

function captureSnapshot() {
  if (!isActive.value || !videoRef.value?.videoWidth) return
  const video = videoRef.value
  const width = 160
  const height = 120
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.drawImage(video, 0, 0, width, height)
  let data
  try {
    data = ctx.getImageData(0, 0, width, height).data
  } catch (e) {
    return
  }
  const pixels = data.length / 4
  let sum = 0
  let diff = 0
  for (let i = 0; i < data.length; i += 4) {
    const luma = (data[i] + data[i + 1] + data[i + 2]) / 3
    sum += luma
    if (lastLuma) diff += Math.abs(luma - lastLuma[i / 4])
  }
  const avg = sum / pixels
  const avgDiff = lastLuma ? diff / pixels : 0
  lastLuma = new Float32Array(pixels)
  for (let i = 0; i < data.length; i += 4) {
    lastLuma[i / 4] = (data[i] + data[i + 1] + data[i + 2]) / 3
  }
  const absent = avg < 12 || (lastLuma && avgDiff < 0.6)
  const note = absent
    ? `端侧判断：可能离开（亮度 ${avg.toFixed(0)}，变化 ${avgDiff.toFixed(1)}）`
    : `端侧判断：在场（亮度 ${avg.toFixed(0)}，变化 ${avgDiff.toFixed(1)}）`
  presenceNote.value = note
  if (absent) leaves.value += 1
  // 文档 E1：只把端侧判断的结果上报，原图不出浏览器
  if (session.value?.id) {
    api
      .focusPresence(session.value.id, {
        present: !absent,
        luma: Number(avg.toFixed(1)),
        diff: Number(avgDiff.toFixed(1)),
        note
      })
      .then((data) => {
        if (typeof data.leaves === 'number') leaves.value = data.leaves
        if (data.aborted) notify('端侧连续判断离开，专注已自动中止', true)
      })
      .catch(() => {
        /* 网络波动不打断专注；本地状态仍然保留 */
      })
  }
}

function tick() {
  if (!isActive.value) return
  if (remaining.value > 0) remaining.value -= 1
  if (remaining.value <= 0) finish(true)
}

async function finish(auto = false) {
  if (!session.value || !isActive.value || busy.value) return
  busy.value = true
  try {
    const actual = auto
      ? session.value.planned_minutes
      : Math.max(1, Math.round((Date.now() - startedAt) / 60000))
    const data = await api.finishFocus(session.value.id, {
      actual_minutes: actual,
      note: auto ? '倒计时完成' : '手动结束'
    })
    session.value = data
    stopCamera()
    if (data.status === 'completed') {
      notify(data.unlocked ? '今日任务已全部完成，强制学习解锁' : '专注完成，任务已打卡')
    } else {
      notify('专注时长不足，已记录一次违约', true)
    }
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    busy.value = false
  }
}

async function abort() {
  if (!session.value || !isActive.value) return
  const ok = await confirmAction({
    title: '中止本次专注',
    message: '中止会记录一次违约，确定要中止吗？',
    detail: '违约记录会进入本周的执行力评估，并可能触发计划重排。',
    confirmText: '仍然中止',
    danger: true
  })
  if (!ok) return
  busy.value = true
  try {
    const data = await api.abortFocus(session.value.id, '主动中止专注')
    session.value = data
    stopCamera()
    notify('已中止并记录违约', true)
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    busy.value = false
  }
}

function onVisibilityChange() {
  if (!document.hidden || !isActive.value) return
  leaves.value += 1
  api
    .heartbeatFocus(session.value.id, leaves.value)
    .then(async (data) => {
      session.value = data
      if (data.status !== 'active') {
        stopCamera()
        notify('离开专注页面次数过多，已自动中止并记录违约', true)
        await load()
      } else {
        notify(`检测到离开页面 ${data.leaves} 次，再离开将自动中止`, true)
      }
    })
    .catch(() => {})
}

function stopNoise() {
  if (noiseSource) {
    try {
      noiseSource.stop()
    } catch (e) {
      /* ignore */
    }
    noiseSource = null
  }
  if (audioCtx) {
    try {
      audioCtx.close()
    } catch (e) {
      /* ignore */
    }
    audioCtx = null
  }
}

function startNoise(type) {
  const Ctor =
    typeof window !== 'undefined' && (window.AudioContext || window.webkitAudioContext)
  if (!Ctor) {
    notify('当前浏览器不支持背景音', true)
    return
  }
  const ctx = new Ctor()
  const gain = ctx.createGain()
  gain.gain.value = type === 'tone' ? 0.035 : type === 'rain' ? 0.08 : 0.1
  if (type === 'tone') {
    const osc = ctx.createOscillator()
    osc.type = 'sine'
    osc.frequency.value = 432
    osc.connect(gain).connect(ctx.destination)
    osc.start()
    noiseSource = { stop: () => osc.stop() }
  } else {
    const length = ctx.sampleRate * 2
    const buffer = ctx.createBuffer(1, length, ctx.sampleRate)
    const data = buffer.getChannelData(0)
    let last = 0
    for (let index = 0; index < length; index += 1) {
      const white = Math.random() * 2 - 1
      if (type === 'cafe') {
        last = (last + 0.02 * white) / 1.02
        data[index] = last * 3.2
      } else {
        data[index] = white * 0.6
      }
    }
    const source = ctx.createBufferSource()
    source.buffer = buffer
    source.loop = true
    const filter = ctx.createBiquadFilter()
    filter.type = type === 'rain' ? 'highpass' : 'lowpass'
    filter.frequency.value = type === 'rain' ? 1200 : 700
    source.connect(filter).connect(gain).connect(ctx.destination)
    source.start()
    noiseSource = source
  }
  audioCtx = ctx
}

function setNoise(type) {
  stopNoise()
  noise.value = type
  if (type !== 'none') startNoise(type)
}

function cleanup() {
  if (tickTimer) clearInterval(tickTimer)
  stopCamera()
  stopNoise()
  document.removeEventListener('visibilitychange', onVisibilityChange)
}

onMounted(async () => {
  await load()
  await restoreActive()
  applyTaskFromQuery()
  tickTimer = setInterval(tick, 1000)
  document.addEventListener('visibilitychange', onVisibilityChange)
})

watch(() => route.query.task, () => applyTaskFromQuery())

onBeforeUnmount(cleanup)

const focusStats = computed(() => {
  const done = tasks.value.filter((task) => task.status === 'done').length
  const s = summary.value
  if (s) {
    return {
      sessions: s.sessions ?? 0,
      totalMinutes: s.total_minutes ?? 0,
      todayMinutes: s.today_minutes ?? 0,
      violations: s.violations ?? 0,
      done,
      tasks: tasks.value.length,
      complete: true
    }
  }
  // 接口不可用时退回历史列表（只覆盖最近若干次，界面上会标注）
  const sessions = history.value.length
  const totalMinutes = history.value.reduce(
    (sum, item) => sum + (item.minutes || item.duration_min || 0),
    0
  )
  return {
    sessions,
    totalMinutes,
    todayMinutes: 0,
    violations: violations.value.length,
    done,
    tasks: tasks.value.length,
    complete: false
  }
})
</script>

<template>
  <div v-if="!store.currentGoalId" class="empty">
    还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建目标并开启强制模式。
  </div>

  <div v-else class="stack">
    <div class="hero">
      <h1>强制学习 · 摄像头监督你的专注</h1>
      <p>
        {{ forceMode ? '当前目标已开启强制模式：任务不能跳过，离开页面会记违约，专注时长不足会中断打卡。' : '当前目标未开启强制模式。可在「目标与资料」中开启，任务将不可跳过。' }}
        系统会按剩余 {{ goal?.days_left }} 天自动调整今日任务，不需要你手动点重排。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ goal?.days_left }}</strong>
          <span>距考试天数</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ pendingCount }}</strong>
          <span>今日待完成</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ todayViolations.length }}</strong>
          <span>今日违约</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ forceMode ? '已开启' : '未开启' }}</strong>
          <span>强制模式</span>
        </div>
      </div>
    </div>

    <div v-if="loading" class="empty">正在加载今日任务与专注记录...</div>

    <div v-else class="focus-grid">
      <div class="card focus-panel">
        <template v-if="isActive">
          <div class="card-head">
            <div>
              <div class="card-title">专注进行中</div>
              <div class="card-sub">{{ session.task_title || '自由学习' }} · 计划 {{ session.planned_minutes }} 分钟</div>
            </div>
            <span class="tag tag-review">摄像头{{ session.camera_enabled ? '已开启' : '未开启' }}</span>
          </div>

          <div class="focus-timer">{{ timeText }}</div>
          <div class="bar" style="margin-bottom: 18px">
            <i :style="{ width: progress + '%' }"></i>
          </div>

          <div class="camera-box" v-show="session.camera_enabled || cameraOn">
            <video ref="videoRef" class="camera-video" autoplay muted playsinline></video>
            <div class="camera-caption">端侧在场判断 · 不上传原图 · 每 60 秒本地检测一次</div>
            <div v-if="presenceNote" class="small muted" style="margin-top: 6px">{{ presenceNote }}</div>
          </div>

          <div class="focus-stats">
            <div><b>{{ session.snapshots }}</b><span>学习见证</span></div>
            <div><b>{{ leaves }}</b><span>离开页面</span></div>
            <div><b>{{ session.actual_minutes }}</b><span>已记录分钟</span></div>
          </div>

          <div class="row" style="margin-top: 12px">
            <span class="small muted">背景音</span>
            <button
              v-for="item in noiseOptions"
              :key="item.key"
              class="chip"
              :class="{ active: noise === item.key }"
              @click="setNoise(item.key)"
            >
              {{ item.label }}
            </button>
          </div>

          <div class="row" style="margin-top: 16px">
            <button class="btn btn-teal" :disabled="busy" @click="finish(false)">完成专注并打卡</button>
            <button class="btn btn-danger" :disabled="busy" @click="abort">中止（记违约）</button>
          </div>
          <div class="small muted" style="margin-top: 10px">
            离开页面超过 3 次会自动中止；专注不足计划时长的 60% 会记为一次违约。
          </div>
        </template>

        <template v-else>
      <div v-if="session && session.status === 'completed'" class="task-reason" style="margin-bottom: 12px">
        本轮专注已结束，任务已打卡。
        <button class="link-quiet" type="button" @click="router.push('/today')">返回今日</button>
      </div>
      <div v-if="queryHint" class="task-reason" style="margin-bottom: 12px">{{ queryHint }}</div>
          <div class="card-head">
            <div>
              <div class="card-title">开始一次强制学习</div>
              <div class="card-sub">选择任务，打开摄像头，倒计时结束才算完成</div>
            </div>
            <span class="tag" :class="forceMode ? 'tag-review' : 'tag-pending'">{{ forceMode ? '强制模式' : '普通模式' }}</span>
          </div>

          <div class="field">
            <label>选择今日任务</label>
            <AppSelect v-model="selectedTaskId" :options="taskOptions" placeholder="自由学习（不绑定任务）" @change="plannedMinutes = 25" />
          </div>

          <div class="grid grid-2" style="gap: 12px">
            <div class="field">
              <label>计划专注分钟</label>
              <input v-model.number="plannedMinutes" class="input" type="number" min="5" max="180" step="5" />
            </div>
            <div class="field">
              <label>摄像头监督</label>
              <button class="btn btn-block" :class="cameraOn ? 'btn-teal' : 'btn-ghost'" type="button" @click="toggleCamera">
                {{ cameraOn ? '摄像头已开启' : '开启摄像头' }}
              </button>
            </div>
          </div>

          <div v-if="cameraError" class="task-reason" style="margin-bottom: 12px">{{ cameraError }}</div>

          <div class="camera-box" v-show="cameraOn">
            <video ref="videoRef" class="camera-video" autoplay muted playsinline></video>
            <div class="camera-caption">摄像头只用于学习见证，不上传人脸识别结果</div>
          </div>

          <div class="row" style="margin-top: 12px">
            <span class="small muted">背景音</span>
            <button
              v-for="item in noiseOptions"
              :key="item.key"
              class="chip"
              :class="{ active: noise === item.key }"
              @click="setNoise(item.key)"
            >
              {{ item.label }}
            </button>
          </div>

          <button class="btn btn-block" :disabled="busy" style="margin-top: 14px" @click="start">
            {{ busy ? '正在开始...' : '开始强制学习' }}
          </button>

          <div class="task-reason" style="margin-top: 14px">
            完成后自动打卡；中途离开页面会计数，超过 3 次自动中止并记录违约；专注不足 60% 也会记违约。
            今日任务全部完成后，强制学习状态解锁。
          </div>
        </template>
      </div>

      <div class="stack">
        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">今日待完成任务</div>
              <div class="card-sub">强制模式下不可跳过，只能完成或中止</div>
            </div>
            <router-link class="btn btn-ghost btn-sm" to="/plan">查看计划</router-link>
          </div>
          <div v-if="!tasks.length" class="empty">今天没有待完成任务，可能已经全部完成。</div>
          <div v-else class="stack">
            <button
              v-for="task in tasks"
              :key="task.id"
              class="focus-task"
              :class="{ active: String(task.id) === selectedTaskId }"
              @click="selectedTaskId = String(task.id); plannedMinutes = task.duration_min"
            >
              <span class="tag" :class="`tag-${task.type}`">{{ typeLabel[task.type] || task.type }}</span>
              <span class="focus-task-main">
                <b>{{ task.title }}</b>
                <small>{{ task.duration_min }} 分钟 · {{ task.kp_name || '未关联知识点' }}</small>
              </span>
              <span class="focus-task-arrow">→</span>
            </button>
          </div>
        </div>

        <div class="card">
          <div class="card-title">违约记录</div>
          <div v-if="!violations.length" class="empty" style="margin-top: 12px">还没有违约记录，保持住。</div>
          <div v-else class="stack" style="margin-top: 12px">
            <div v-for="item in violations.slice(0, 5)" :key="item.id" class="violation-row">
              <span class="tag tag-skipped">{{ item.kind }}</span>
              <span>{{ item.detail }}</span>
              <small>{{ item.day }}</small>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-title">最近专注</div>
          <div v-if="!history.length" class="empty" style="margin-top: 12px">还没有专注记录。</div>
          <div v-else class="stack" style="margin-top: 12px">
            <div v-for="item in history.slice(0, 4)" :key="item.id" class="kv">
              <span>{{ item.task_title || '自由学习' }} · {{ item.actual_minutes }}/{{ item.planned_minutes }} 分钟</span>
              <strong :style="{ color: item.status === 'completed' ? '#0d9488' : '#dc2626' }">
                {{ item.status === 'completed' ? '完成' : '中止' }}
              </strong>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">专注与违约概览</div>
          <div class="card-sub">专注记录、完成任务与违约次数</div>
        </div>
      </div>
      <div class="grid grid-4" style="margin-top: 10px">
        <div class="stat">
          <div class="stat-label">专注次数</div>
          <div class="stat-value">{{ focusStats.sessions }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">累计专注</div>
          <div class="stat-value">{{ focusStats.totalMinutes }}<span style="font-size: 13px"> 分钟</span></div>
        </div>
        <div class="stat">
          <div class="stat-label">完成任务</div>
          <div class="stat-value">{{ focusStats.done }} / {{ focusStats.tasks }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">违约次数</div>
          <div class="stat-value">{{ focusStats.violations }}</div>
        </div>
      </div>
      <div v-if="focusStats.complete" class="small muted" style="margin-top: 8px">
        以上为全量统计 · 今日已专注 {{ focusStats.todayMinutes }} 分钟
      </div>
    </div>
  </div>
</template>
