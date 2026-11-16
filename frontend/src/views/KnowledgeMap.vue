<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'
import DetailModal from '../components/DetailModal.vue'

const loading = ref(true)
const data = ref(null)
const detail = ref(null)
const risks = ref(null)
const riskLoading = ref(false)
const riskRunning = ref(false)
const riskQuizTarget = ref(null)
const riskQuestions = ref([])
const riskChoices = ref([])
const riskResult = ref(null)
const ragQuery = ref('')
const ragResults = ref([])
const ragLoading = ref(false)
const selected = ref(null)
const verifyingGap = ref(null)
const quiz = ref(null)
const answers = ref([])
const verifyResult = ref(null)
const verifying = ref(false)
const submitting = ref(false)
const external = ref(null)
const externalLoading = ref(false)

function selectNode(node) {
  selected.value = node
  external.value = null
}

async function lookupExternal() {
  if (!selected.value || externalLoading.value) return
  externalLoading.value = true
  try {
    external.value = await api.knowledgeLookup(selected.value.name)
    notify(`外部知识库返回 ${external.value.available_count} 个来源`)
  } catch (e) {
    notify(e.message, true)
  } finally {
    externalLoading.value = false
  }
}

const levelLabel = { excellent: '稳', good: '可控', risk: '风险', critical: '危急' }

const layout = computed(() => {
  if (!data.value) return { positions: {}, width: 600, height: 400, groups: [] }
  const groups = new Map()
  for (const node of data.value.nodes) {
    const key = node.parent || '根知识点'
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(node)
  }
  const positions = {}
  let groupIndex = 0
  let maxRows = 1
  for (const [key, items] of groups) {
    items.forEach((node, index) => {
      positions[node.kp_id] = {
        ...node,
        x: 100 + groupIndex * 200,
        y: 60 + index * 74
      }
    })
    maxRows = Math.max(maxRows, items.length)
    groupIndex += 1
  }
  return {
    positions,
    width: 100 + groupIndex * 200 + 80,
    height: Math.max(360, 100 + maxRows * 74),
    groups: [...groups.keys()]
  }
})

function masteryColor(value) {
  const hue = Math.round(Math.max(0, Math.min(1, value)) * 140)
  return `hsl(${hue}, 65%, 88%)`
}

function statusStroke(status) {
  if (status === 'verified') return '#dc2626'
  if (status === 'candidate') return '#f59e0b'
  if (status === 'fixed') return '#0d9488'
  return '#cbd5e1'
}

function shortName(name) {
  return name.length > 8 ? name.slice(0, 8) + '…' : name
}

function prereqChain(kpId) {
  if (!data.value) return []
  const reverse = {}
  for (const edge of data.value.edges) {
    if (!reverse[edge.target]) reverse[edge.target] = []
    reverse[edge.target].push(edge.source)
  }
  const result = []
  let frontier = [kpId]
  for (let depth = 0; depth < 4; depth += 1) {
    const next = []
    for (const node of frontier) {
      for (const parent of reverse[node] || []) {
        if (!result.includes(parent)) {
          result.push(parent)
          next.push(parent)
        }
      }
    }
    if (!next.length) break
    frontier = next
  }
  return result.map((id) => layout.value.positions[id]).filter(Boolean)
}

async function load() {
  if (!store.currentGoalId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    data.value = await api.knowledgeGraph(store.currentGoalId)
    await loadRisks()
    if (selected.value) {
      selected.value = data.value.nodes.find((node) => node.kp_id === selected.value.kp_id) || null
    }
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function verify(gap) {
  verifyingGap.value = gap
  verifying.value = true
  verifyResult.value = null
  try {
    quiz.value = await api.verifyGap(gap.id)
    answers.value = new Array(quiz.value.questions.length).fill(-1)
  } catch (e) {
    notify(e.message, true)
    verifyingGap.value = null
  } finally {
    verifying.value = false
  }
}

function choose(index, option) {
  answers.value[index] = option
}

async function submitVerify() {
  if (!quiz.value || !verifyingGap.value) return
  if (answers.value.some((item) => item < 0)) {
    notify('还有验证题未作答', true)
    return
  }
  submitting.value = true
  try {
    const result = await api.submitGap(verifyingGap.value.id, {
      quiz_id: quiz.value.quiz_id,
      answers: answers.value
    })
    verifyResult.value = result
    notify(result.gap.status === 'verified' ? '验证未通过，已确认漏洞并插入修复任务' : '验证通过，已排除该漏洞')
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    submitting.value = false
  }
}

function closeVerify() {
  verifyingGap.value = null
  quiz.value = null
  verifyResult.value = null
}

async function loadRisks() {
  if (!store.currentGoalId) return
  riskLoading.value = true
  try {
    risks.value = await api.riskForecast(store.currentGoalId)
  } catch (e) {
    notify(e.message, true)
  } finally {
    riskLoading.value = false
  }
}

function openRisk(item) {
  detail.value = {
    title: item.kp_name,
    subtitle: `风险分 ${item.risk_score} · ${item.level} · 置信度 ${Math.round(item.confidence * 100)}%`,
    rows: [
      { label: '风险分', value: `${item.risk_score} / 100` },
      { label: '置信度', value: `${Math.round(item.confidence * 100)}%（样本 ${item.sample_size}）` },
      {
        label: '因素贡献',
        value: item.factors.map((factor) => `${factor.label} ${factor.value} × ${factor.weight}`).join('；')
      },
      {
        label: '证据',
        value: `近 7 天错题 ${item.evidence.recent_mistakes_7d}、迁移题失败 ${item.evidence.probe_failures}/${item.evidence.probe_attempts}、逾期任务 ${item.evidence.task_overdue}/${item.evidence.task_total}`
      },
      {
        label: '数据说明',
        value: item.evidence.insufficient
          ? '证据不足，仅作方向参考'
          : `数据点 ${item.evidence.data_points}，窗口 ${item.evidence.window_days} 天，模型 ${item.model_version}`
      }
    ]
  }
}

async function startRiskVerify(item) {
  riskRunning.value = true
  riskResult.value = null
  try {
    const data = await api.riskQuestions(item.id, 2)
    riskQuizTarget.value = item
    riskQuestions.value = data.questions
    riskChoices.value = new Array(data.questions.length).fill(-1)
  } catch (e) {
    notify(e.message, true)
    riskQuizTarget.value = null
  } finally {
    riskRunning.value = false
  }
}

function chooseRisk(index, option) {
  riskChoices.value[index] = option
}

async function submitRiskVerify() {
  if (!riskQuizTarget.value || !riskQuestions.value.length) return
  if (riskChoices.value.some((item) => item < 0)) {
    notify('还有验证题未作答', true)
    return
  }
  riskRunning.value = true
  try {
    let allCorrect = true
    for (let i = 0; i < riskQuestions.value.length; i += 1) {
      const result = await api.submitProbe(riskQuestions.value[i].id, riskChoices.value[i])
      if (!result.correct) allCorrect = false
    }
    const result = await api.riskVerify(riskQuizTarget.value.id, allCorrect)
    riskResult.value = result
    notify(result.message)
    await Promise.all([load(), loadRisks()])
  } catch (e) {
    notify(e.message, true)
  } finally {
    riskRunning.value = false
  }
}

function closeRiskVerify() {
  riskQuizTarget.value = null
  riskQuestions.value = []
  riskChoices.value = []
  riskResult.value = null
}

async function markRisk(item, verdict) {
  try {
    await api.riskFeedback(item.id, verdict)
    notify('反馈已记录，该风险将不再提示')
    await loadRisks()
  } catch (e) {
    notify(e.message, true)
  }
}

async function runRagSearch() {
  const query = ragQuery.value.trim()
  if (!query) {
    notify('请输入检索关键词', true)
    return
  }
  ragLoading.value = true
  try {
    const data = await api.ragSearch(store.currentGoalId, query, 5)
    ragResults.value = data.results || []
    if (!data.found) notify('未检索到可靠来源，不编造引用。', true)
  } catch (e) {
    notify(e.message, true)
  } finally {
    ragLoading.value = false
  }
}

watch(() => store.currentGoalId, load, { immediate: true })
onMounted(() => {})

const mapStats = computed(() => ({
  nodes: data.value?.nodes?.length || 0,
  edges: data.value?.edges?.length || 0,
  candidates: data.value?.candidates?.length || 0,
  verified: data.value?.verified?.length || 0,
  risks: risks.value?.active_count || 0
}))
</script>

<template>
  <div v-if="!store.currentGoalId" class="empty">
    还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建目标。
  </div>

  <div v-else-if="loading" class="empty">正在构建知识依赖图...</div>

  <div v-else-if="data" class="stack">
    <div class="hero">
      <h1>知识漏洞地图</h1>
      <p>
        错题不只是这道题不会。系统顺着先修依赖向上追溯，找出更底层的薄弱知识点，
        先列为候选漏洞，再用验证题确认，避免凭感觉补错地方。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ data.nodes.length }}</strong>
          <span>知识点节点</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ data.edges.length }}</strong>
          <span>先修依赖</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ data.candidates.length }}</strong>
          <span>候选漏洞</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ data.verified.length }}</strong>
          <span>已验证漏洞</span>
        </div>
      </div>
    </div>

    <div class="knowledge-layout">
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">知识点依赖图</div>
            <div class="card-sub">颜色越浅掌握越低；橙边候选漏洞、红边已验证、绿边已排除</div>
          </div>
          <button class="btn btn-ghost btn-sm" @click="load">刷新</button>
        </div>
        <div class="graph-scroll">
          <svg :viewBox="`0 0 ${layout.width} ${layout.height}`" class="graph-svg">
            <line
              v-for="(edge, index) in data.edges"
              :key="`edge-${index}`"
              :x1="layout.positions[edge.source]?.x"
              :y1="layout.positions[edge.source]?.y"
              :x2="layout.positions[edge.target]?.x"
              :y2="layout.positions[edge.target]?.y"
              stroke="#cbd5e1"
              stroke-width="1.2"
            />
            <g
              v-for="node in data.nodes"
              :key="node.kp_id"
              class="graph-node"
              @click="selectNode(node)"
            >
              <rect
                :x="layout.positions[node.kp_id].x - 68"
                :y="layout.positions[node.kp_id].y - 20"
                width="136"
                height="40"
                rx="10"
                :fill="masteryColor(node.mastery)"
                :stroke="statusStroke(node.status)"
                :stroke-width="node.status === 'normal' ? 1.2 : 2.5"
              />
              <text
                :x="layout.positions[node.kp_id].x"
                :y="layout.positions[node.kp_id].y + 4"
                text-anchor="middle"
                font-size="11"
                fill="#0f172a"
              >
                {{ shortName(node.name) }}
              </text>
            </g>
          </svg>
        </div>
        <div class="small muted" style="margin-top: 8px">
          当前布局按模块分组，箭头方向为先修 → 后继。点击节点查看先修链。
        </div>
      </div>

      <div class="stack">
        <div v-if="selected" class="card">
          <div class="card-head">
            <div>
              <div class="card-title">{{ selected.name }}</div>
              <div class="card-sub">{{ selected.parent || '根知识点' }} · 权重 {{ selected.weight }}</div>
            </div>
            <span class="tag" :class="selected.status === 'verified' ? 'tag-skipped' : selected.status === 'candidate' ? 'tag-time' : 'tag-pending'">
              {{ selected.status }}
            </span>
          </div>
          <div class="kv"><span>掌握度</span><strong>{{ Math.round(selected.mastery * 100) }}%</strong></div>
          <div class="kv"><span>错题数</span><strong>{{ selected.mistake_count }} 道</strong></div>
          <div class="kv"><span>先修链</span><strong>{{ prereqChain(selected.kp_id).map((item) => item.name).join(' → ') || '无' }}</strong></div>
          <div class="row-between" style="margin-top: 10px">
            <div class="small muted">外部知识库</div>
            <button class="btn btn-sm" :disabled="externalLoading" @click="lookupExternal">
              {{ externalLoading ? '查询中...' : '查询百科' }}
            </button>
          </div>
          <div v-if="external" class="stack" style="margin-top: 8px">
            <div v-for="src in external.sources" :key="src.key" class="kv">
              <span>{{ src.name }}</span>
              <strong class="small">
                {{ src.status === 'ok' ? src.summary : src.status === 'empty' ? '无匹配词条' : '暂不可用' }}
              </strong>
            </div>
            <div class="small muted">
              共 {{ external.available_count }} / {{ external.total }} 个来源返回
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">候选与已验证漏洞</div>
              <div class="card-sub">先验证，再修复，避免无效努力</div>
            </div>
          </div>
          <div v-if="!data.candidates.length && !data.verified.length" class="empty">
            当前没有发现明显漏洞。保持答题与错题记录，系统会继续追踪。
          </div>
          <div v-else class="stack">
            <div v-for="gap in data.verified" :key="`v-${gap.id}`" class="gap-row verified">
              <div>
                <b>{{ gap.kp_name }}</b>
                <div class="small muted">{{ gap.evidence }}</div>
              </div>
              <span class="tag tag-skipped">已验证</span>
            </div>
            <div v-for="gap in data.candidates" :key="`c-${gap.id}`" class="gap-row">
              <div>
                <b>{{ gap.kp_name }}</b>
                <div class="small muted">{{ gap.evidence }}</div>
              </div>
              <button class="btn btn-sm" :disabled="verifying" @click="verify(gap)">验证</button>
            </div>
          </div>
          <div class="small muted" style="margin-top: 10px">
            已排除 {{ data.fixed_count }} 个候选漏洞。
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">知识漏洞早期预警</div>
          <div class="card-sub">
            可复算风险分：遗忘 30% / 先修 25% / 错误 20% / 迁移 15% / 逾期 10% · 点击查看证据
          </div>
        </div>
        <span v-if="risks" class="tag tag-time">
          高 {{ risks.high_count }} · 中 {{ risks.medium_count }} · 证据不足 {{ risks.insufficient_count }}
        </span>
      </div>
      <div v-if="riskLoading" class="empty">正在计算风险分...</div>
      <div v-else-if="!risks || !risks.items.length" class="empty">暂无风险数据。</div>
      <div v-else class="stack">
        <div
          v-for="item in risks.items.slice(0, 6)"
          :key="item.id"
          class="gap-row"
          :class="{ verified: item.level === 'high' }"
        >
          <div
            class="click-line"
            style="flex: 1"
            role="button"
            tabindex="0"
            @click="openRisk(item)"
            @keydown.enter.prevent="openRisk(item)"
            @keydown.space.prevent="openRisk(item)"
          >
            <div class="row-between">
              <b>{{ item.kp_name }}</b>
              <span
                class="tag"
                :class="item.level === 'high' ? 'tag-skipped' : item.level === 'medium' ? 'tag-time' : 'tag-study'"
              >
                {{ item.level }}
              </span>
            </div>
            <div class="small muted">
              风险分 {{ item.risk_score }} · 置信度 {{ Math.round(item.confidence * 100) }}% · 样本 {{ item.sample_size }}
            </div>
            <div class="bar" style="margin-top: 4px"><i :style="{ width: item.risk_score + '%' }"></i></div>
            <div class="small muted" style="margin-top: 4px">
              {{ item.factors.map((factor) => factor.label + ' ' + factor.value).join(' · ') }}
            </div>
          </div>
          <div class="row" style="gap: 6px">
            <button class="btn btn-sm" :disabled="riskRunning" @click="startRiskVerify(item)">验证</button>
            <button class="btn btn-ghost btn-sm" @click="markRisk(item, 'false_positive')">误报</button>
          </div>
        </div>
        <div class="small muted">
          风险仅作候选线索，验证后才会生成修复任务。阈值：高 {{ risks.thresholds.high }} / 中 {{ risks.thresholds.medium }} · 模型 {{ risks.model_version }}
        </div>
      </div>
    </div>

    <div v-if="verifyingGap" class="modal-mask" @click.self="closeVerify">
      <div class="modal knowledge-modal">
        <div class="card-head">
          <div>
            <div class="card-title">验证漏洞：{{ verifyingGap.kp_name }}</div>
            <div class="card-sub">答对全部题目即排除漏洞；答错则确认并生成修复任务</div>
          </div>
          <button class="btn btn-ghost btn-sm" @click="closeVerify">关闭</button>
        </div>

        <div v-if="verifying" class="empty">正在生成验证题...</div>

        <div v-else-if="verifyResult" class="stack">
          <div class="row-between">
            <b>{{ verifyResult.gap.status === 'verified' ? '漏洞已确认' : '漏洞已排除' }}</b>
            <span class="tag" :class="verifyResult.gap.status === 'verified' ? 'tag-skipped' : 'tag-review'">
              {{ verifyResult.gap.status }}
            </span>
          </div>
          <div class="task-reason">{{ verifyResult.gap.evidence }}</div>
          <div class="small muted">得分 {{ verifyResult.result.score }} · 答对 {{ verifyResult.result.correct }} / {{ verifyResult.result.total }}</div>
          <button class="btn btn-block" @click="closeVerify">完成</button>
        </div>

        <div v-else-if="quiz" class="stack">
          <div v-for="question in quiz.questions" :key="question.index" class="quiz-question">
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
          </div>
          <button class="btn btn-block" :disabled="submitting" @click="submitVerify">
            {{ submitting ? '判分中...' : '提交验证' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="riskQuizTarget" class="modal-mask" @click.self="closeRiskVerify">
      <div class="modal knowledge-modal">
        <div class="card-head">
          <div>
            <div class="card-title">风险验证：{{ riskQuizTarget.kp_name }}</div>
            <div class="card-sub">答对全部题目即排除风险；答错则确认并生成修复任务</div>
          </div>
          <button class="btn btn-ghost btn-sm" @click="closeRiskVerify">关闭</button>
        </div>

        <div v-if="riskRunning" class="empty">正在生成验证题或判分...</div>

        <div v-else-if="riskResult" class="stack">
          <div class="row-between">
            <b>{{ riskResult.status === 'verified' ? '风险已确认' : '风险已排除' }}</b>
            <span class="tag" :class="riskResult.status === 'verified' ? 'tag-skipped' : 'tag-review'">
              {{ riskResult.status }}
            </span>
          </div>
          <div class="task-reason">{{ riskResult.message }}</div>
          <div v-if="riskResult.task_id" class="small muted">已生成修复任务 #{{ riskResult.task_id }}，可在学习计划中查看。</div>
          <button class="btn btn-block" @click="closeRiskVerify">完成</button>
        </div>

        <div v-else-if="riskQuestions.length" class="stack">
          <div v-for="(question, index) in riskQuestions" :key="question.id" class="quiz-question">
            <div class="quiz-stem">
              <span class="quiz-index">{{ index + 1 }}</span>
              <span>{{ question.question }}</span>
            </div>
            <div class="quiz-options">
              <button
                v-for="(option, optionIndex) in question.options"
                :key="optionIndex"
                class="quiz-option"
                :class="{ active: riskChoices[index] === optionIndex }"
                @click="chooseRisk(index, optionIndex)"
              >
                <span class="quiz-option-key">{{ String.fromCharCode(65 + optionIndex) }}</span>
                <span>{{ option }}</span>
              </button>
            </div>
          </div>
          <button class="btn btn-block" :disabled="riskRunning" @click="submitRiskVerify">
            {{ riskRunning ? '判分中...' : '提交验证' }}
          </button>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">资料引用检索（RAG）</div>
          <div class="card-sub">回答附文件名与段落定位，检索不到时明确说明证据不足</div>
        </div>
      </div>
      <div class="row" style="gap: 8px; margin-top: 10px">
        <input
          v-model="ragQuery"
          class="input"
          placeholder="例如：听力主旨、导数定义"
          style="flex: 1"
          @keyup.enter="runRagSearch"
        />
        <button class="btn" :disabled="ragLoading" @click="runRagSearch">
          {{ ragLoading ? '检索中...' : '检索资料' }}
        </button>
      </div>
      <div v-if="ragResults.length" class="stack" style="margin-top: 10px">
        <div v-for="(item, index) in ragResults" :key="index" class="gap-row">
          <div>
            <b>{{ item.filename }}</b>
            <div class="small muted">第 {{ item.chunk_index + 1 }} 段 · 相关度 {{ Math.round(item.score * 100) }}%</div>
            <div class="small">{{ item.snippet }}</div>
          </div>
          <span class="tag tag-study">{{ item.page_no ? 'P' + item.page_no : '段落' }}</span>
        </div>
      </div>
      <div v-else-if="ragQuery && !ragLoading" class="empty">未检索到可靠来源，不编造引用。</div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">知识地图概览</div>
          <div class="card-sub">节点、依赖边、漏洞与风险的整体规模</div>
        </div>
      </div>
      <div class="grid grid-4" style="margin-top: 10px">
        <div class="stat">
          <div class="stat-label">知识点节点</div>
          <div class="stat-value">{{ mapStats.nodes }}</div>
          <div class="stat-note">依赖边 {{ mapStats.edges }} 条</div>
        </div>
        <div class="stat">
          <div class="stat-label">候选漏洞</div>
          <div class="stat-value">{{ mapStats.candidates }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">已验证漏洞</div>
          <div class="stat-value">{{ mapStats.verified }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">风险预警</div>
          <div class="stat-value">{{ mapStats.risks }}</div>
        </div>
      </div>
    </div>

    <DetailModal
      :open="Boolean(detail)"
      :title="detail?.title || ''"
      :subtitle="detail?.subtitle || ''"
      :rows="detail?.rows || []"
      @close="detail = null"
    />
  </div>
</template>