<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'
import AppSelect from '../components/AppSelect.vue'
import DetailModal from '../components/DetailModal.vue'

const loading = ref(true)
const generating = ref(false)
const kind = ref('probe')
const pending = ref([])
const history = ref([])
const detail = ref(null)
const tutorPoints = ref([])
const tutorPointOptions = computed(() => tutorPoints.value.map((point) => ({ value: point.id, label: point.name })))
const modeOptions = [
  { value: 'hint', label: '提示模式' },
  { value: 'explain', label: '讲解模式' },
  { value: 'exam', label: '考试模式' }
]
const levelOptions = [
  { value: 'direction', label: '方向提示' },
  { value: 'concept', label: '概念提示' },
  { value: 'step', label: '步骤提示' },
  { value: 'full', label: '完整讲解' }
]
const resourceOptions = [
  { value: 'flashcard', label: '闪卡' },
  { value: 'variant', label: '变式题' },
  { value: 'outline', label: '微课提纲' }
]

const tutorKpId = ref('')
const tutorMode = ref('hint')
const tutorLevel = ref('concept')
const tutorMessage = ref('')
const tutorReply = ref(null)
const tutorLoading = ref(false)
const recallText = ref('')
const recallResult = ref(null)
const resourceType = ref('flashcard')
const resourceResult = ref(null)
const resourceLoading = ref(false)

const kindLabelMap = {
  probe: '主动探针',
  transfer: '迁移压力测试',
  challenge: '反脆弱挑战',
  boundary: '概念边界辨析',
  speed: '限时快答',
  reverse: '逆向追问',
  trap: '陷阱排除',
  mixed: '混合挑战'
}

function kindLabel(key) {
  return kindLabelMap[key] || key || '主动探针'
}

function openHistory(item) {
  detail.value = {
    title: item.question,
    subtitle: item.correct ? '作答正确' : '作答错误',
    rows: [
      { label: '结果', value: item.correct ? '正确' : '错误' },
      { label: '题型', value: kindLabel(item.kind) },
      { label: '记录时间', value: item.created_at ? item.created_at.slice(0, 16).replace('T', ' ') : '—' },
      { label: '说明', value: '该记录来自真实作答，会参与掌握度与错因统计。' }
    ]
  }
}
const selected = ref({})
const result = ref(null)

const kinds = [
  { key: 'probe', label: '主动探针', desc: 'AI 主动寻找隐藏知识盲区，不用你挑知识点' },
  { key: 'transfer', label: '迁移压力测试', desc: '换情境、换问法，判断是否真正理解并能应用' },
  { key: 'challenge', label: '反脆弱挑战', desc: '故意加入陌生条件，答错不扣掌握度，训练应对能力' },
  { key: 'boundary', label: '概念边界辨析', desc: '四个高度相似的表述，只有一处细微差别决定对错' },
  { key: 'speed', label: '限时快答', desc: '题干短一眼可读，考条件反射式熟练度，答错不惩罚' },
  { key: 'reverse', label: '逆向追问', desc: '从结论反推原因与条件，考因果链是否真正理清' },
  { key: 'trap', label: '陷阱排除', desc: '选项埋入常见思维陷阱，考能否识破套路' },
  { key: 'mixed', label: '混合挑战', desc: '一道题融合两个知识点交叉运用，考综合能力' }
]

const activeKind = computed(() => kinds.find((item) => item.key === kind.value) || kinds[0])

async function load() {
  if (!store.currentGoalId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const [pendingList, all] = await Promise.all([
      api.probes(store.currentGoalId, { kind: kind.value, status: 'pending' }),
      api.probes(store.currentGoalId, { kind: kind.value })
    ])
    pending.value = pendingList
    history.value = all.filter((item) => item.status === 'answered').slice(0, 6)
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function generate() {
  generating.value = true
  result.value = null
  try {
    await api.generateProbes(store.currentGoalId, { kind: kind.value, count: 1 })
    notify(`AI 已生成一道${activeKind.value.label}题`)
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    generating.value = false
  }
}

async function submit(probe) {
  if (selected.value[probe.id] === undefined) {
    notify('请先选择一个答案', true)
    return
  }
  try {
    const data = await api.submitProbe(probe.id, selected.value[probe.id])
    result.value = { ...data, probe }
    await load()
  } catch (e) {
    notify(e.message, true)
  }
}

async function loadTutorPoints() {
  if (!store.currentGoalId) return
  try {
    tutorPoints.value = await api.knowledgePoints(store.currentGoalId)
    if (!tutorKpId.value && tutorPoints.value.length) tutorKpId.value = tutorPoints.value[0].id
  } catch (e) {
    /* ignore */
  }
}

async function askSocratic() {
  if (!tutorKpId.value) {
    notify('请先选择知识点', true)
    return
  }
  tutorLoading.value = true
  tutorReply.value = null
  try {
    tutorReply.value = await api.socratic(store.currentGoalId, {
      kp_id: Number(tutorKpId.value),
      message: tutorMessage.value,
      mode: tutorMode.value,
      level: tutorLevel.value
    })
  } catch (e) {
    notify(e.message, true)
  } finally {
    tutorLoading.value = false
  }
}

async function checkRecall() {
  if (!tutorKpId.value) {
    notify('请先选择知识点', true)
    return
  }
  if (!recallText.value.trim()) {
    notify('请输入你的复述', true)
    return
  }
  try {
    recallResult.value = await api.socraticRecall(store.currentGoalId, {
      kp_id: Number(tutorKpId.value),
      recall: recallText.value
    })
  } catch (e) {
    notify(e.message, true)
  }
}

async function genResources() {
  if (!tutorKpId.value) {
    notify('请先选择知识点', true)
    return
  }
  resourceLoading.value = true
  resourceResult.value = null
  try {
    resourceResult.value = await api.generateResources(store.currentGoalId, {
      kp_id: Number(tutorKpId.value),
      resource_type: resourceType.value,
      count: 3
    })
  } catch (e) {
    notify(e.message, true)
  } finally {
    resourceLoading.value = false
  }
}

watch(
  () => [store.currentGoalId, kind.value],
  () => {
    load()
    loadTutorPoints()
  },
  { immediate: true }
)
onMounted(() => {})

const probeStats = computed(() => {
  const answered = history.value.length
  const correct = history.value.filter((item) => item.correct).length
  return {
    answered,
    correct,
    rate: answered ? Math.round((correct / answered) * 100) : 0,
    pending: pending.value.length,
    types: kinds.length
  }
})
</script>

<template>
  <div v-if="!store.currentGoalId" class="empty">
    还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建目标。
  </div>

  <div v-else class="stack">
    <div class="hero">
      <h1>AI 探针与挑战</h1>
      <p>
        不是等你去问 AI，而是 AI 主动来找你的盲区。主动探针寻找隐藏漏洞，迁移压力测试判断是否真正理解，
        反脆弱挑战用陌生条件训练应对能力。三类题目都会写入学习证据链。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ pending.length }}</strong>
          <span>待作答</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ history.length }}</strong>
          <span>近期作答</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ activeKind.label }}</strong>
          <span>当前模式</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ kinds.length }}</strong>
          <span>挑战类型</span>
        </div>
      </div>
    </div>

    <div class="chip-list">
      <button
        v-for="item in kinds"
        :key="item.key"
        class="chip"
        :class="{ active: kind === item.key }"
        @click="kind = item.key"
      >
        {{ item.label }}
      </button>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">{{ activeKind.label }}</div>
          <div class="card-sub">{{ activeKind.desc }}</div>
        </div>
        <button class="btn" :disabled="generating" @click="generate">
          {{ generating ? 'AI 出题中...' : '让 AI 主动出题' }}
        </button>
      </div>

      <div v-if="loading" class="empty">正在读取题目...</div>
      <div v-else-if="!pending.length" class="empty">
        当前没有待答题。点击右上角「让 AI 主动出题」，系统会结合掌握度与错题自动选题。
      </div>
      <div v-else class="stack">
        <div v-for="probe in pending" :key="probe.id" class="probe-card">
          <div class="row-between">
            <span class="tag tag-study">{{ activeKind.label }}</span>
            <span class="small muted">{{ probe.kp_name || '未关联知识点' }}</span>
          </div>
          <div class="probe-question">{{ probe.question }}</div>
          <div class="quiz-options">
            <button
              v-for="(option, index) in probe.options"
              :key="index"
              class="quiz-option"
              :class="{ active: selected[probe.id] === index }"
              @click="selected = { ...selected, [probe.id]: index }"
            >
              <span class="quiz-option-key">{{ String.fromCharCode(65 + index) }}</span>
              <span>{{ option }}</span>
            </button>
          </div>
          <button class="btn btn-sm" style="margin-top: 10px" @click="submit(probe)">提交答案</button>
        </div>
      </div>
    </div>

    <div v-if="result" class="card">
      <div class="card-head">
        <div>
          <div class="card-title">{{ result.correct ? '回答正确' : '发现一个盲区' }}</div>
          <div class="card-sub">{{ result.probe.kp_name || '未关联知识点' }}</div>
        </div>
        <span class="tag" :class="result.correct ? 'tag-review' : 'tag-skipped'">{{ result.correct ? '通过' : '待补' }}</span>
      </div>
      <div class="task-reason">{{ result.explanation || '暂无解析' }}</div>
      <div class="row" style="margin-top: 10px">
        <span v-if="result.mastery !== null" class="small muted">掌握度更新为 {{ Math.round(result.mastery * 100) }}%</span>
        <span class="small muted">韧性值 {{ result.resilience }}</span>
        <span class="small muted">{{ result.evidence }}</span>
      </div>
    </div>

    <div class="card">
      <div class="card-title">近期作答</div>
      <div v-if="!history.length" class="empty" style="margin-top: 10px">还没有作答记录。</div>
      <div v-else class="stack" style="margin-top: 10px">
        <div v-for="item in history" :key="item.id" class="kv click-line" style="padding: 8px; border-radius: 10px" role="button" tabindex="0" @click="openHistory(item)" @keydown.enter.prevent="openHistory(item)" @keydown.space.prevent="openHistory(item)">
          <span>{{ item.question.slice(0, 42) }}{{ item.question.length > 42 ? '…' : '' }}</span>
          <strong :style="{ color: item.correct ? '#0d9488' : '#dc2626' }">
            {{ item.correct ? '正确' : '错误' }}
          </strong>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">AI 苏格拉底导师</div>
          <div class="card-sub">分级提示、复述检查与资源工厂，不会直接替你写答案</div>
        </div>
      </div>
      <div class="grid grid-3" style="gap: 10px; margin-top: 12px">
        <div class="field">
          <label>知识点</label>
          <AppSelect v-model="tutorKpId" :options="tutorPointOptions" placeholder="选择知识点" />
        </div>
        <div class="field">
          <label>模式</label>
          <AppSelect v-model="tutorMode" :options="modeOptions" />
        </div>
        <div class="field">
          <label>提示级别</label>
          <AppSelect v-model="tutorLevel" :options="levelOptions" />
        </div>
      </div>
      <div class="row" style="gap: 8px; margin-top: 8px">
        <input v-model="tutorMessage" class="input" placeholder="说说你卡在哪一步..." style="flex: 1" @keyup.enter="askSocratic" />
        <button class="btn" :disabled="tutorLoading" @click="askSocratic">
          {{ tutorLoading ? '思考中...' : '请教导师' }}
        </button>
      </div>
      <div v-if="tutorReply" class="task-reason" style="margin-top: 10px">
        <b>{{ tutorReply.level_label }} · {{ tutorReply.mode_label }}</b>
        <div style="margin-top: 6px">{{ tutorReply.reply }}</div>
        <div v-if="tutorReply.next_question" class="small muted" style="margin-top: 6px">下一步：{{ tutorReply.next_question }}</div>
        <div class="small muted" style="margin-top: 4px">引擎：{{ tutorReply.engine === 'llm' ? '智能讲解' : '备用讲解' }}</div>
      </div>
      <div class="row" style="gap: 8px; margin-top: 10px">
        <input v-model="recallText" class="input" placeholder="用你自己的话复述这个知识点..." style="flex: 1" />
        <button class="btn btn-ghost" @click="checkRecall">复述检查</button>
      </div>
      <div v-if="recallResult" class="small" style="margin-top: 8px">
        <span class="tag" :class="recallResult.passed ? 'tag-review' : 'tag-time'">覆盖 {{ recallResult.coverage }}%</span>
        {{ recallResult.feedback }}
      </div>
      <div class="row" style="gap: 8px; margin-top: 12px">
        <AppSelect v-model="resourceType" :options="resourceOptions" style="width: 140px" />
        <button class="btn" :disabled="resourceLoading" @click="genResources">
          {{ resourceLoading ? '生成中...' : '生成学习资源' }}
        </button>
      </div>
      <div v-if="resourceResult" class="stack" style="margin-top: 10px">
        <div class="small muted">
          {{ resourceResult.resource_label }} · {{ resourceResult.engine === 'llm' ? '智能讲解' : '备用讲解' }}
          · {{ resourceResult.review_status }}
        </div>
        <div v-for="(item, index) in resourceResult.items" :key="index" class="gap-row">
          <div class="small">{{ item.front || item.question || item.title }}</div>
          <span class="tag tag-study">#{{ index + 1 }}</span>
        </div>
        <div class="small muted">{{ resourceResult.note }}</div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">探针与挑战概览</div>
          <div class="card-sub">真实作答记录、正确率与题型覆盖</div>
        </div>
      </div>
      <div class="grid grid-4" style="margin-top: 10px">
        <div class="stat">
          <div class="stat-label">已作答</div>
          <div class="stat-value">{{ probeStats.answered }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">正确</div>
          <div class="stat-value">{{ probeStats.correct }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">正确率</div>
          <div class="stat-value">{{ probeStats.rate }}%</div>
        </div>
        <div class="stat">
          <div class="stat-label">待作答 / 题型</div>
          <div class="stat-value" style="font-size: 18px">{{ probeStats.pending }} / {{ probeStats.types }}</div>
        </div>
      </div>
    </div>

    <DetailModal
      :open="Boolean(detail)"
      :title="detail?.title || ''"
      :subtitle="detail?.subtitle || ''"
      :rows="detail?.rows || []"
      :link-to="detail?.linkTo || ''"
      :link-text="detail?.linkText || '前往详情'"
      @close="detail = null"
    />
  </div>
</template>