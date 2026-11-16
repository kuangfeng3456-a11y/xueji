<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { store, notify } from '../store'
import AppSelect from '../components/AppSelect.vue'
import VocabLab from '../components/VocabLab.vue'
import QuizMaterial from '../components/QuizMaterial.vue'

const router = useRouter()
const points = ref([])
const kpId = ref('')
const count = ref(3)
const quiz = ref(null)
const answers = ref([])
const result = ref(null)
const generating = ref(false)
const submitting = ref(false)
const showHistory = ref(false)
const history = ref([])
const historySummary = ref({
  correct: 0,
  questions: 0,
  avg_score: 0,
  score_distribution: { excellent: 0, good: 0, warning: 0, fail: 0 }
})
const historyLoading = ref(false)
const bankCatalog = ref(null)
const bankLoading = ref(false)
const bankTesting = ref(false)
const bankTestResult = ref(null)
const showBankPoints = ref(false)
const vocabTarget = ref(null)

// 阅读/听力题会共享同一份材料，按 material.id 分组，材料只在组首渲染一次
const quizGroups = computed(() => {
  const list = quiz.value?.questions || []
  const groups = []
  const byMaterial = new Map()
  list.forEach((question) => {
    const material = question.material
    const key = material?.id
    if (key && byMaterial.has(key)) {
      byMaterial.get(key).questions.push(question)
      return
    }
    const group = { key: key || `solo-${question.index}`, material: material || null, questions: [question] }
    if (key) byMaterial.set(key, group)
    groups.push(group)
  })
  return groups
})

// 材料序号：同一套卷里出现多段听力材料时，标注「材料 1 / 材料 2」
const materialOrder = computed(() => {
  const order = new Map()
  let index = 0
  for (const group of quizGroups.value) {
    if (!group.material) continue
    index += 1
    order.set(group.key, index)
  }
  return order
})

const engineLabel = computed(() => {
  const engine = quiz.value?.engine || result.value?.engine
  if (engine === 'tiku') return '题库出题（按考点取题）'
  if (engine === 'tiku+bank') return '题库出题 + 内置题库补题'
  if (engine === 'tiku+llm') return '题库出题 + 模型补题'
  if (engine === 'tiku+external') return '题库出题 + 外部题库补题'
  if (engine === 'external') return '外部题库'
  if (engine === 'external+llm') return '外部题库 + 模型补题'
  if (engine === 'bank+external') return '内置题库 + 外部题库'
  if (engine === 'llm') return '智能出题'
  if (engine === 'bank+llm') return '模型出题 + 内置题库补题'
  if (engine === 'bank') return '内置题库出题'
  return '系统出题'
})

const answeredCount = computed(() => answers.value.filter((item) => item >= 0).length)

// 词汇类知识点走独立的单词卡（VocabLab），不进入随堂测选择题
const isVocabName = (name) => /词/.test(String(name || ''))
const quizPoints = computed(() => points.value.filter((point) => !isVocabName(point.name)))
const vocabPoints = computed(() => points.value.filter((point) => isVocabName(point.name)))
const kpOptions = computed(() => [
  { value: '', label: '自动选择最薄弱' },
  ...quizPoints.value.map((point) => ({
    value: point.id,
    label: `${point.name}（${Math.round(point.mastery * 100)}%）`,
    hint: pointHint(point)
  }))
])

function openVocab(point) {
  vocabTarget.value = { kpId: point.id, title: point.name }
}

const countOptions = [
  { value: 3, label: '3 道' },
  { value: 5, label: '5 道' },
  { value: 6, label: '6 道' }
]

const scoreDistribution = computed(
  () => historySummary.value.score_distribution || { excellent: 0, good: 0, warning: 0, fail: 0 }
)

const avgScore = computed(() => historySummary.value.avg_score || 0)

const totalAttempts = ref(0)
const totalCorrect = computed(() => historySummary.value.correct || 0)
const totalQuestions = computed(() => historySummary.value.questions || 0)
const overallAccuracy = computed(() => {
  if (!totalQuestions.value) return 0
  return Math.round((totalCorrect.value / totalQuestions.value) * 100)
})

const bankSummary = computed(
  () =>
    bankCatalog.value?.summary || {
      point_count: 0,
      local_count: 0,
      cached_count: 0,
      external_cached_count: 0,
      model_count: 0,
      rule_count: 0
    }
)
const selectedBankPoint = computed(() => {
  if (!kpId.value) return null
  return catalogRow(kpId.value)
})
const bankSourceLabel = (source) =>
  ({
    tiku: '题库',
    local: '内置题库',
    online_cache: '已缓存在线题',
    external_cache: '外部题库缓存',
    external_api: '外部题库',
    model: '智能出题',
    rule: '系统出题'
  })[source] || '待检查'

// 考点下拉右侧的小标签：这个考点会从哪里出题、题库里有几道
// 父级模块（阅读/听力/高等数学）在 all_points 里，叶子在 points 里，两处都要查
function catalogRow(kpId) {
  const catalog = bankCatalog.value
  if (!catalog) return null
  const id = Number(kpId)
  return (
    (catalog.all_points || []).find((item) => item.kp_id === id) ||
    (catalog.points || []).find((item) => item.kp_id === id) ||
    null
  )
}

function pointHint(point) {
  const info = catalogRow(point.id)
  if (!info) return ''
  // 标签要与真实出题来源一致：模型出题的考点不能标成「内置 N 题」
  if (info.material === 'listening') return '听力材料'
  if (info.material === 'passage') return '阅读文章'
  if (info.source === 'tiku') return `${info.tiku_question_count} 题`
  if (info.source === 'model') return '模型生成'
  if (info.source === 'external_api') return '外部题库'
  if (info.local_question_count) return `内置 ${info.local_question_count}`
  return ''
}

// 「各知识点对应题库」列表里的来源说明：材料题说明生成方式，数理题说明题库题量
function pointSourceDetail(info) {
  if (!info) return ''
  if (info.material === 'listening') return '听力材料题 · 模型生成音频脚本 + 题干'
  if (info.material === 'passage') return '阅读材料题 · 模型生成完整文章 + 多题'
  if (info.source === 'tiku') return `题库 ${info.tiku_question_count} 道对应题`
  if (info.source === 'model') return '题库未收录 · 模型实时生成'
  if (info.source === 'external_api') return '外部题库接口取题'
  if (info.local_question_count) return `${info.local_question_count} 道内置题`
  if (info.cached_question_count) return `${info.cached_question_count} 道在线缓存题`
  return '按可用网络接口出题'
}

async function loadPoints() {
  if (!store.currentGoalId) return
  if (!store.currentGoalId) {
    points.value = []
    bankCatalog.value = null
    history.value = []
    totalAttempts.value = 0
    historySummary.value = {
      correct: 0,
      questions: 0,
      avg_score: 0,
      score_distribution: { excellent: 0, good: 0, warning: 0, fail: 0 }
    }
    return
  }
  bankLoading.value = true
  const [pointsResult, catalogResult] = await Promise.allSettled([
    api.knowledgePoints(store.currentGoalId),
    api.questionBankCatalog(store.currentGoalId)
  ])
  if (pointsResult.status === 'fulfilled') points.value = pointsResult.value
  else notify(pointsResult.reason.message, true)
  if (catalogResult.status === 'fulfilled') bankCatalog.value = catalogResult.value
  else notify(catalogResult.reason.message, true)
  if (kpId.value && !points.value.some((point) => point.id === Number(kpId.value))) kpId.value = ''
  bankLoading.value = false
  await loadHistory()
}

async function loadHistory() {
  if (!store.currentGoalId) return
  historyLoading.value = true
  try {
    const response = await api.quizHistory(store.currentGoalId)
    history.value = response.items || []
    totalAttempts.value = response.total || 0
    historySummary.value = response.summary || historySummary.value
  } catch (e) {
    notify(e.message, true)
  } finally {
    historyLoading.value = false
  }
}

async function testBankApi() {
  if (!store.currentGoalId) return
  bankTesting.value = true
  bankTestResult.value = null
  try {
    const pointId =
      (selectedBankPoint.value?.kp_id || bankCatalog.value?.points?.[0]?.kp_id || null)
    const response = await api.testQuestionBank(store.currentGoalId, pointId)
    bankTestResult.value = response
    if (response.status === 'ok') {
      notify(response.detail || (`题库可用：取到 ${response.question_count} 道题`))
      bankCatalog.value = await api.questionBankCatalog(store.currentGoalId)
    } else if (response.status === 'not_configured') {
      notify(response.detail, true)
    } else {
      notify(response.detail || '题库探测未通过', true)
    }
  } catch (e) {
    bankTestResult.value = { status: 'error', detail: e.message }
    notify(e.message, true)
  } finally {
    bankTesting.value = false
  }
}

function backToSetup() {
  quiz.value = null
  result.value = null
  answers.value = []
}

async function generate() {
  if (!store.currentGoalId) return
  generating.value = true
  result.value = null
  try {
    quiz.value = await api.generateQuiz(store.currentGoalId, {
      kp_id: kpId.value ? Number(kpId.value) : null,
      count: Number(count.value)
    })
    answers.value = new Array(quiz.value.questions.length).fill(-1)
  } catch (e) {
    notify(e.message, true)
  } finally {
    generating.value = false
  }
}

function choose(index, optionIndex) {
  answers.value[index] = optionIndex
}

async function submit() {
  if (!quiz.value) return
  if (answers.value.some((item) => item < 0)) {
    notify('还有题目没有作答', true)
    return
  }
  submitting.value = true
  try {
    const data = await api.submitQuiz(store.currentGoalId, {
      quiz_id: quiz.value.quiz_id,
      answers: answers.value
    })
    result.value = data
    quiz.value = null
    await loadHistory()
    notify(`本次得分 ${data.score} 分，错题已自动归因并触发重排`)
  } catch (e) {
    notify(e.message, true)
  } finally {
    submitting.value = false
  }
}

function retry() {
  result.value = null
  generate()
}

watch(() => store.currentGoalId, loadPoints, { immediate: true })
</script>

<template>
  <div v-if="!store.currentGoalId" class="empty">
    还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建目标。
  </div>

  <div v-else class="stack">
    <div class="hero">
      <h1>AI 随堂测 · 出题、判分、归因一次完成</h1>
      <p>
        先按考点从题库取题（一个考点对应题库里的一门课，题与考点一一对应）；题库没有的考点再用模型实时出题，
        都不可用时退回内置题库兜底，每题卡片都会标注真实来源。最终由服务端判分，答错会进入错题本并更新掌握度。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ points.length }}</strong>
          <span>可选知识点</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ totalAttempts }}</strong>
          <span>累计测试</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ overallAccuracy }}%</strong>
          <span>总体正确率</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ avgScore }}</strong>
          <span>平均得分</span>
        </div>
      </div>
    </div>

    <div class="card qbank-panel">
      <div class="card-head">
        <div>
          <div class="card-title">对应题库与接口状态</div>
          <div class="card-sub">先按考点从题库取题（一个考点一门课），取不到再用模型补；题目卡片标注真实来源。</div>
        </div>
        <button class="btn btn-ghost btn-sm" :disabled="bankTesting || bankLoading" @click="testBankApi">
          {{ bankTesting ? '正在探测题库…' : '探测题库是否可用' }}
        </button>
      </div>
      <div class="grid qbank-stats">
        <div class="stat">
          <div class="stat-label">知识点</div>
          <div class="stat-value">{{ bankSummary.point_count }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">题库有对应题</div>
          <div class="stat-value">{{ bankSummary.tiku_count || 0 }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">内置题库可兜底</div>
          <div class="stat-value">{{ bankSummary.local_count }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">模型题缓存</div>
          <div class="stat-value">{{ bankSummary.cached_count }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">外部题库缓存</div>
          <div class="stat-value">{{ bankSummary.external_cached_count }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">将用模型出题</div>
          <div class="stat-value">{{ bankSummary.model_count }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">系统出题</div>
          <div class="stat-value">{{ bankSummary.rule_count }}</div>
        </div>
      </div>
      <div class="qbank-status-row">
        <span class="tag" :class="bankCatalog?.tiku_adapter?.configured ? 'tag-review' : 'tag-pending'">
          {{ bankCatalog?.tiku_adapter?.configured ? '题库已连接' : '题库暂未接入' }}
        </span>
        <span class="tag" :class="bankCatalog?.external_api_configured ? 'tag-review' : 'tag-pending'">
          {{ bankCatalog?.external_api_configured ? '外部题库已接入' : '外部题库暂未接入' }}
        </span>
        <span class="tag" :class="bankCatalog?.online_generation_available ? 'tag-study' : 'tag-pending'">
          {{ bankCatalog?.online_generation_available ? '智能出题可用' : '当前使用内置题库' }}
        </span>
        <span class="small muted">
          每个考点在题库里是一门课，选「定积分」只会取到定积分的题；阅读 / 听力是材料题，由模型生成整篇文章与听力脚本。
        </span>
      </div>
      <div v-if="bankTestResult" class="qbank-test-result" :class="`is-${bankTestResult.status}`" role="status">
        <span class="qbank-test-indicator"></span>
        <strong>
          {{
            bankTestResult.status === 'ok'
              ? '外部题库接口可用'
              : bankTestResult.status === 'not_configured'
                ? '外部题库尚未配置'
                : bankTestResult.status === 'timeout'
                  ? '外部题库请求超时'
                  : '外部题库接口未通过'
          }}
        </strong>
        <span>{{ bankTestResult.detail }}</span>
        <small v-if="bankTestResult.latency_ms !== null && bankTestResult.latency_ms !== undefined">
          {{ bankTestResult.latency_ms }} ms
        </small>
      </div>
      <div class="qbank-current">
        <span class="small muted">当前选中题库</span>
        <strong v-if="selectedBankPoint">
          {{ selectedBankPoint.module }} · {{ selectedBankPoint.kp_name }}
        </strong>
        <strong v-else>自动选择最薄弱知识点</strong>
        <span
          v-if="selectedBankPoint"
          class="tag"
          :class="selectedBankPoint.source === 'local' || selectedBankPoint.source === 'external_cache' ? 'tag-review' : selectedBankPoint.source === 'rule' ? 'tag-pending' : 'tag-study'"
        >
          {{ bankSourceLabel(selectedBankPoint.source) }}
          <template v-if="selectedBankPoint.tiku_question_count">· {{ selectedBankPoint.tiku_question_count }} 题</template>
          <template v-else-if="selectedBankPoint.local_question_count">· {{ selectedBankPoint.local_question_count }} 题</template>
        </span>
        <button class="link-quiet qbank-detail-toggle" @click="showBankPoints = !showBankPoints">
          {{ showBankPoints ? '收起题库覆盖' : '查看各知识点对应题库' }}
        </button>
      </div>
      <div v-if="showBankPoints" class="qbank-points">
        <button
          v-for="item in bankCatalog?.points || []"
          :key="item.kp_id"
          class="qbank-point"
          :class="{ active: Number(kpId) === item.kp_id }"
          @click="kpId = String(item.kp_id); showBankPoints = false; showHistory = false"
        >
          <span>
            <strong>{{ item.kp_name }}</strong>
            <small>{{ item.module }} · {{ pointSourceDetail(item) }}</small>
          </span>
          <span class="tag" :class="item.source === 'local' || item.source === 'external_cache' ? 'tag-review' : item.source === 'rule' ? 'tag-pending' : 'tag-study'">
            {{ bankSourceLabel(item.source) }}
          </span>
        </button>
        <div v-if="!bankCatalog?.points?.length" class="empty">
          {{ bankLoading ? '正在读取题库覆盖…' : '当前目标还没有知识点，请先导入资料或应用学科包。' }}
        </div>
      </div>
    </div>

    <div class="row-between">
      <div class="row">
        <button class="btn btn-ghost btn-sm" :aria-pressed="!showHistory" @click="showHistory = false">出题测试</button>
        <button class="btn btn-ghost btn-sm" :aria-pressed="showHistory" @click="showHistory = true">历史记录</button>
      </div>
      <span class="small muted">共 {{ totalAttempts }} 次测试，正确 {{ totalCorrect }} / 共 {{ totalQuestions }} 题</span>
    </div>

    <div v-if="showHistory" class="split">
      <div class="stack">
        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">得分分布</div>
              <div class="card-sub">按分数段统计历史测试得分</div>
            </div>
          </div>
          <div class="grid grid-2" style="gap: 10px; margin-top: 10px">
            <div class="stat" style="background: #ecfdf5">
              <div class="stat-label">优秀 (≥80)</div>
              <div class="stat-value" style="color: #059669">{{ scoreDistribution.excellent }}</div>
              <div class="bar" style="margin-top: 6px"><i :style="{ width: (scoreDistribution.excellent / (scoreDistribution.excellent + scoreDistribution.good + scoreDistribution.warning + scoreDistribution.fail || 1)) * 100 + '%' }" style="background: #059669"></i></div>
            </div>
            <div class="stat" style="background: #eff6ff">
              <div class="stat-label">良好 (60-79)</div>
              <div class="stat-value" style="color: #2563eb">{{ scoreDistribution.good }}</div>
              <div class="bar" style="margin-top: 6px"><i :style="{ width: (scoreDistribution.good / (scoreDistribution.excellent + scoreDistribution.good + scoreDistribution.warning + scoreDistribution.fail || 1)) * 100 + '%' }" style="background: #2563eb"></i></div>
            </div>
            <div class="stat" style="background: #fffbeb">
              <div class="stat-label">警告 (40-59)</div>
              <div class="stat-value" style="color: #d97706">{{ scoreDistribution.warning }}</div>
              <div class="bar" style="margin-top: 6px"><i :style="{ width: (scoreDistribution.warning / (scoreDistribution.excellent + scoreDistribution.good + scoreDistribution.warning + scoreDistribution.fail || 1)) * 100 + '%' }" style="background: #d97706"></i></div>
            </div>
            <div class="stat" style="background: #fef2f2">
              <div class="stat-label">不及格 (&lt;40)</div>
              <div class="stat-value" style="color: #dc2626">{{ scoreDistribution.fail }}</div>
              <div class="bar" style="margin-top: 6px"><i :style="{ width: (scoreDistribution.fail / (scoreDistribution.excellent + scoreDistribution.good + scoreDistribution.warning + scoreDistribution.fail || 1)) * 100 + '%' }" style="background: #dc2626"></i></div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">测试统计</div>
              <div class="card-sub">累计测试数据汇总</div>
            </div>
          </div>
          <div class="grid grid-2" style="gap: 10px; margin-top: 10px">
            <div class="stat">
              <div class="stat-label">累计测试</div>
              <div class="stat-value">{{ totalAttempts }}</div>
              <div class="stat-note">次</div>
            </div>
            <div class="stat">
              <div class="stat-label">平均得分</div>
              <div class="stat-value">{{ avgScore }}</div>
              <div class="stat-note">分</div>
            </div>
            <div class="stat">
              <div class="stat-label">累计答题</div>
              <div class="stat-value">{{ totalQuestions }}</div>
              <div class="stat-note">题</div>
            </div>
            <div class="stat">
              <div class="stat-label">总体正确率</div>
              <div class="stat-value">{{ overallAccuracy }}%</div>
              <div class="stat-note">{{ totalCorrect }} / {{ totalQuestions }}</div>
            </div>
          </div>
        </div>
      </div>

      <div class="stack">
        <div class="card">
          <div class="card-title">历史记录</div>
          <div v-if="historyLoading" class="empty" style="margin-top: 10px">正在从服务端读取答题历史…</div>
          <div v-else-if="!history.length" class="empty" style="margin-top: 10px">还没有测试记录，完成第一次随堂测后会自动保存。</div>
          <div v-else class="stack" style="margin-top: 10px">
            <div v-for="(item, index) in history.slice(0, 10)" :key="index" class="kv">
              <div class="row-between small">
                <span>{{ item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : '—' }}</span>
                <span :style="{ color: item.score >= 80 ? '#059669' : item.score >= 60 ? '#2563eb' : '#dc2626' }">{{ item.score }} 分</span>
              </div>
              <div class="small muted">答对 {{ item.correct }} / {{ item.total }} · 错题 {{ item.wrong }} 道 · {{ item.engine === 'llm' ? '智能出题' : item.engine === 'bank' || item.engine === 'bank+llm' ? '题库出题' : '系统出题' }}</div>
            </div>
          </div>
        </div>

      </div>
    </div>

    <div v-else-if="!quiz && !result" class="card">
      <div class="card-head">
        <div>
          <div class="card-title">生成一组随堂测</div>
          <div class="card-sub">不选知识点时，自动挑最薄弱的几个</div>
        </div>
      </div>
      <div class="grid quiz-setup-grid">
        <div class="field">
          <label>知识点</label>
          <AppSelect v-model="kpId" :options="kpOptions" />
        </div>
        <div class="field">
          <label>题目数量</label>
          <AppSelect v-model="count" :options="countOptions" />
        </div>
        <div class="field">
          <label class="label-spacer">&nbsp;</label>
          <button class="btn btn-block" :disabled="generating" @click="generate">
            {{ generating ? 'AI 出题中...' : '开始测试' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="quiz" class="card">
      <div class="card-head">
        <div>
          <div class="card-title">随堂测进行中</div>
          <div class="card-sub">{{ engineLabel }} · 已作答 {{ answeredCount }} / {{ quiz.questions.length }}</div>
        </div>
        <button class="btn btn-ghost btn-sm" @click="backToSetup">放弃本组</button>
      </div>

      <div class="stack">
        <div v-for="group in quizGroups" :key="group.key" class="quiz-group">
          <QuizMaterial
            v-if="group.material"
            :material="group.material"
            :order="materialOrder.get(group.key) || 1"
          />
          <div v-for="question in group.questions" :key="question.index" class="quiz-question">
            <div class="quiz-stem">
              <span class="quiz-index">{{ question.index + 1 }}</span>
              <span>{{ question.question }}</span>
            </div>
            <div class="quiz-options">
              <button
                v-for="(option, optionIndex) in question.options"
                :key="optionIndex"
                class="quiz-option"
                :class="{ active: answers[question.index] === optionIndex }"
                @click="choose(question.index, optionIndex)"
              >
                <span class="quiz-option-key">{{ String.fromCharCode(65 + optionIndex) }}</span>
                <span>{{ option }}</span>
              </button>
            </div>
            <div class="small muted" style="margin-top: 6px">
              知识点：{{ question.kp_name || '未关联' }}
              <span v-if="question.source"> · 来源：{{ question.source }}</span>
            </div>
          </div>
        </div>
      </div>

      <button class="btn btn-block" style="margin-top: 16px" :disabled="submitting" @click="submit">
        {{ submitting ? '判分与重排中...' : '提交并查看结果' }}
      </button>
    </div>

    <div v-if="result" class="stack">
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">本次结果</div>
            <div class="card-sub">{{ engineLabel }} · 答对 {{ result.correct }} / {{ result.total }}</div>
          </div>
          <span class="tag" :class="result.score >= 60 ? 'tag-review' : 'tag-skipped'">{{ result.score }} 分</span>
        </div>

        <div class="row" style="gap: 20px; flex-wrap: wrap; margin-bottom: 16px">
          <div class="stat" style="flex: 1; min-width: 160px">
            <div class="stat-label">得分</div>
            <div class="stat-value">{{ result.score }}</div>
            <div class="bar" style="margin-top: 8px"><i :style="{ width: result.score + '%' }"></i></div>
          </div>
          <div class="stat" style="flex: 1; min-width: 160px">
            <div class="stat-label">答对</div>
            <div class="stat-value">{{ result.correct }} / {{ result.total }}</div>
          </div>
          <div class="stat" style="flex: 1; min-width: 160px">
            <div class="stat-label">错题</div>
            <div class="stat-value">{{ result.wrong.length }}</div>
            <div class="stat-note">已写入错题本并触发重排</div>
          </div>
        </div>

        <!-- 交卷后放开材料原文：听力原文此时才可见，便于复盘 -->
        <div v-if="(result.materials || []).length" class="stack" style="margin-bottom: 14px">
          <div class="card-sub">本次材料（可展开原文复盘）</div>
          <QuizMaterial
            v-for="(material, index) in result.materials"
            :key="material.id || index"
            :material="material.kind === 'listening' ? { ...material, audio_script: material.transcript } : material"
            :order="index + 1"
            reveal
          />
        </div>

        <div v-if="result.wrong.length" class="stack">
          <div v-for="item in result.wrong" :key="item.index" class="quiz-wrong">
            <div class="row-between">
              <b>{{ item.question }}</b>
              <span class="tag" :class="`tag-${item.category}`">{{ item.category_label }}</span>
            </div>
            <div class="small" style="margin-top: 6px">
              你的答案：{{ item.chosen }}　正确答案：{{ item.correct }}
            </div>
            <div v-if="item.solution_steps && item.solution_steps.length" style="margin-top: 8px">
              <div class="small muted" style="margin-bottom: 4px">解题步骤</div>
              <ol class="quiz-steps">
                <li v-for="(step, stepIndex) in item.solution_steps" :key="stepIndex" class="small">{{ step }}</li>
              </ol>
            </div>
            <div v-if="item.misconception" class="small" style="margin-top: 6px; color: var(--brand-dark)">
              干扰项诊断：{{ item.misconception }}
            </div>
            <div class="task-reason" style="margin-top: 8px">
              {{ item.explanation || '暂无解析' }}
            </div>
          </div>
        </div>
        <div v-else class="empty">全部答对，这一组没有错题。</div>

        <div v-if="result.replan_changes?.length" style="margin-top: 14px">
          <div class="small muted" style="margin-bottom: 8px">自动重排</div>
          <div class="stack">
            <div v-for="(change, index) in result.replan_changes" :key="index" class="task-reason" style="margin-top: 0">
              {{ change.detail }}
            </div>
          </div>
        </div>

        <div class="row" style="margin-top: 16px">
          <button class="btn" :disabled="generating" @click="backToSetup">重新选题</button>
          <button class="btn btn-ghost" @click="router.push('/mistakes')">去错题本</button>
          <button class="btn btn-ghost" @click="router.push('/plan')">查看计划</button>
        </div>
      </div>
    </div>

  </div>
</template>
