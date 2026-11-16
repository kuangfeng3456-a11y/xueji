<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'

const loading = ref(true)
const testing = ref(false)
const items = ref([])
const configuredCount = ref(0)
const healthyCount = ref(0)
const total = ref(0)
const lastTested = ref('')

const detailOpen = ref(false)
const active = ref(null)
const retesting = ref(false)

const kbTerm = ref('machine learning')
const kbLoading = ref(false)
const kbResult = ref(null)
const cloud = ref(null)
const cloudLoading = ref(false)
const cloudServices = ref(null)
const cloudServicesLoading = ref(false)
const questionBankProbe = ref(null)
const questionBankTesting = ref(false)
const evalRunning = ref(false)
const evalResult = ref(null)
const evalHistory = ref([])

const typeLabel = {
  model: '模型接口',
  network: '网络服务',
  cloud: '云服务',
  browser: '浏览器能力'
}

const statusLabel = {
  ok: '正常',
  client: '浏览器侧',
  degraded: '降级运行',
  not_configured: '未配置',
  error: '异常',
  unavailable: '不可用',
  unknown: '待测试',
  timeout: '请求超时',
  invalid_response: '响应无效',
  no_knowledge_points: '缺少知识点'
}

const statusClass = {
  ok: 'tag-review',
  client: 'tag-study',
  degraded: 'tag-time',
  not_configured: 'tag-pending',
  error: 'tag-skipped',
  timeout: 'tag-skipped',
  invalid_response: 'tag-skipped',
  no_knowledge_points: 'tag-pending',
  unavailable: 'tag-skipped',
  unknown: 'tag-pending'
}

const modelItem = computed(() => items.value.find((item) => item.key === 'deepseek'))
const healthyRate = computed(() =>
  total.value ? Math.round((healthyCount.value / total.value) * 100) : 0
)
const activeSources = computed(() => active.value?.sources || [])

async function load() {
  loading.value = true
  try {
    const data = await api.integrations()
    items.value = data.items.map((item) => ({ ...item, status: item.status || 'unknown', latency_ms: null }))
    configuredCount.value = data.configured_count
    total.value = data.total
    healthyCount.value = 0
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

function applyResult(data) {
  items.value = data.items
  configuredCount.value = data.configured_count
  healthyCount.value = data.healthy_count
  total.value = data.total
  lastTested.value = new Date().toLocaleTimeString()
  if (active.value) {
    const fresh = data.items.find((item) => item.key === active.value.key)
    if (fresh) active.value = fresh
  }
}

async function testAll(force = false) {
  testing.value = true
  try {
    const data = await api.testIntegrations(force)
    applyResult(data)
    notify(`接入测试完成：${data.healthy_count} / ${data.total} 项可用`)
  } catch (e) {
    notify(e.message, true)
  } finally {
    testing.value = false
  }
}

async function loadCloud() {
  if (cloud.value || cloudLoading.value) return
  cloudLoading.value = true
  try {
    cloud.value = await api.cloudInstances()
  } catch (e) {
    cloud.value = { detail: e.message, rds: { items: [] }, dcs: { items: [] } }
  } finally {
    cloudLoading.value = false
  }
}

function openDetail(item) {
  active.value = item
  detailOpen.value = true
  kbResult.value = null
  if (['database', 'cache'].includes(item.key)) loadCloud()
  if (item.key === 'external' && !(item.sources && item.sources.length)) {
    retestActive()
  }
}

function closeDetail() {
  detailOpen.value = false
}

async function retestActive() {
  if (!active.value) return
  retesting.value = true
  try {
    const data = await api.testIntegrations(true)
    applyResult(data)
    notify(`已重新探测：${active.value?.name || ''}`)
  } catch (e) {
    notify(e.message, true)
  } finally {
    retesting.value = false
  }
}

async function testQuestionBankApi() {
  if (!store.currentGoalId) {
    notify('请先创建或选择考试目标，再用目标中的知识点探测题库接口', true)
    return
  }
  questionBankTesting.value = true
  questionBankProbe.value = null
  try {
    const data = await api.testQuestionBank(store.currentGoalId)
    questionBankProbe.value = data
    if (data.status === 'ok') {
      notify(data.detail || (`题库可用：取到 ${data.question_count} 道题`))
    } else {
      notify(data.detail || '题库探测未通过', true)
    }
  } catch (e) {
    questionBankProbe.value = { status: 'error', detail: e.message }
    notify(e.message, true)
  } finally {
    questionBankTesting.value = false
  }
}

async function lookupKnowledge() {
  const term = kbTerm.value.trim()
  if (!term) {
    notify('请输入要查询的术语', true)
    return
  }
  kbLoading.value = true
  try {
    kbResult.value = await api.knowledgeLookup(term)
    notify(`外部知识库返回 ${kbResult.value.available_count} 个来源结果`)
  } catch (e) {
    notify(e.message, true)
  } finally {
    kbLoading.value = false
  }
}

function openSource(source) {
  if (!source?.link) return
  window.open(source.link, '_blank', 'noopener')
}

async function copyActive() {
  if (!active.value) return
  const text = [
    active.value.name,
    `状态：${statusLabel[active.value.status] || active.value.status}`,
    `类型：${typeLabel[active.value.type] || active.value.type}`,
    `配置：${active.value.configured ? '是' : '否'}`,
    `延迟：${active.value.latency_ms ?? '—'} ms`,
    `详情：${active.value.detail}`
  ].join('\n')
  try {
    await navigator.clipboard.writeText(text)
    notify('接入信息已复制')
  } catch (e) {
    notify('浏览器未授权剪贴板，请手动选择文本', true)
  }
}

async function loadEvalHistory() {
  try {
    evalHistory.value = (await api.evalRuns()).runs || []
  } catch (e) {
    /* ignore */
  }
}

async function runEval() {
  evalRunning.value = true
  evalResult.value = null
  try {
    evalResult.value = await api.evalRun(6)
    evalHistory.value = (await api.evalRuns()).runs || []
    notify(`评测完成：正确率 ${Math.round(evalResult.value.accuracy * 100)}%`)
  } catch (e) {
    notify(e.message, true)
  } finally {
    evalRunning.value = false
  }
}

async function loadCloudServices() {
  cloudServicesLoading.value = true
  try {
    cloudServices.value = await api.cloudServices()
  } catch (e) {
    notify(e.message, true)
  } finally {
    cloudServicesLoading.value = false
  }
}

onMounted(async () => {
  await load()
  await testAll(false)
  await loadEvalHistory()
  await loadCloudServices()
})
</script>

<template>
  <div class="stack">
    <div class="hero">
      <h1>系统接入 · 全部走真实接口</h1>
      <p>
        学迹的智能环节统一接入 DeepSeek 模型接口；业务数据、缓存、文件存储走网络服务；
        外部知识库已接通 OpenAlex、Crossref 与百度百科；语音与摄像头使用浏览器原生能力。
        点击任意卡片可查看探测明细。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ configuredCount }} / {{ total }}</strong>
          <span>已配置接口</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ healthyCount }} / {{ total }}</strong>
          <span>当前可用</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ modelItem?.configured ? 'DeepSeek' : '未接入' }}</strong>
          <span>模型引擎</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ healthyRate }}%</strong>
          <span>健康率</span>
        </div>
      </div>
    </div>

    <div class="row-between">
      <div class="small muted">
        最近测试：{{ lastTested || '尚未测试' }} · 模型密钥仅显示配置状态，不会回传明文
      </div>
      <button class="btn" :disabled="testing" @click="testAll(true)">
        {{ testing ? '正在逐项测试...' : '重新测试全部接口' }}
      </button>
    </div>

    <div v-if="loading" class="empty">正在读取接入配置...</div>

    <div v-else class="integration-grid">
      <div
        v-for="item in items"
        :key="item.key"
        class="integration-card it-clickable"
        role="button"
        tabindex="0"
        :aria-label="`查看 ${item.name} 详情`"
        @click="openDetail(item)"
        @keydown.enter.prevent="openDetail(item)"
        @keydown.space.prevent="openDetail(item)"
      >
        <div class="row-between">
          <div>
            <div class="integration-name">{{ item.name }}</div>
            <div class="small muted">{{ typeLabel[item.type] || item.type }}</div>
          </div>
          <span class="tag" :class="statusClass[item.status] || 'tag-pending'">
            {{ statusLabel[item.status] || item.status }}
          </span>
        </div>
        <div class="integration-detail">{{ item.detail }}</div>
        <div class="integration-meta">
          <span>配置：{{ item.configured ? '是' : '否' }}</span>
          <span v-if="item.latency_ms !== null && item.latency_ms !== undefined">延迟：{{ item.latency_ms }} ms</span>
          <span v-else>延迟：—</span>
        </div>
        <div class="bar" style="margin-top: 10px">
          <i
            :style="{
              width: item.status === 'ok' ? '100%' : item.status === 'client' ? '70%' : item.configured ? '45%' : '15%'
            }"
          ></i>
        </div>
        <div class="it-hint">
          <span>{{ item.key === 'external' ? '查看来源与在线查询' : '查看探测明细' }}</span>
          <span>→</span>
        </div>
      </div>
    </div>

    <div class="split">
      <div class="card">
        <div class="card-title">模型接口覆盖范围</div>
        <div class="stack" style="margin-top: 12px">
          <div class="kv"><span>Planner</span><strong>计划摘要与学习策略润色</strong></div>
          <div class="kv"><span>Diagnoser</span><strong>错题四类归因与补救建议</strong></div>
          <div class="kv"><span>Coach</span><strong>每日提醒与鼓励</strong></div>
          <div class="kv"><span>Reporter</span><strong>周报点评</strong></div>
          <div class="kv"><span>Insights</span><strong>学情诊断与优先改善建议</strong></div>
          <div class="kv"><span>Forecast</span><strong>冲刺策略与风险提醒</strong></div>
          <div class="kv"><span>Flashcards</span><strong>卡片释义、记忆技巧、常见误区</strong></div>
          <div class="kv"><span>Quiz</span><strong>现场出题与解析</strong></div>
          <div class="kv"><span>Knowledge</span><strong>资料抽取知识点树</strong></div>
          <div class="kv"><span>Voice</span><strong>语音问答自然语言回答</strong></div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">接入原则</div>
        <div class="small muted" style="margin-top: 10px; line-height: 1.9">
          智能文本由云端模型生成，必要时使用备用讲解。学习计划与掌握度由系统规则计算。外部资料会标明来源。密钥只保存在服务端。
        </div>
        <div v-if="store.meta" class="task-reason" style="margin-top: 12px">
          当前后端：{{ store.meta.llm_enabled ? store.meta.llm_model : '规则引擎模式' }} ·
          {{ store.meta.cache_backend === 'redis' ? 'Redis 缓存' : '内存缓存' }}
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">AI 可靠性评测</div>
          <div class="card-sub">内置 6 道基准题，真实调用模型，按关键词命中复算正确率、延迟与失败率</div>
        </div>
        <button class="btn" :disabled="evalRunning" @click="runEval">
          {{ evalRunning ? '评测中...' : '运行评测' }}
        </button>
      </div>
      <div v-if="evalResult" class="stack" style="margin-top: 10px">
        <div class="grid grid-4" style="gap: 10px">
          <div class="stat">
            <div class="stat-label">正确率</div>
            <div class="stat-value">{{ Math.round(evalResult.accuracy * 100) }}%</div>
            <div class="stat-note">{{ evalResult.correct }} / {{ evalResult.total }}</div>
          </div>
          <div class="stat">
            <div class="stat-label">平均延迟</div>
            <div class="stat-value">{{ evalResult.avg_latency_ms }}<span style="font-size: 13px"> ms</span></div>
          </div>
          <div class="stat">
            <div class="stat-label">失败数</div>
            <div class="stat-value">{{ evalResult.failures }}</div>
          </div>
          <div class="stat">
            <div class="stat-label">引擎</div>
            <div class="stat-value" style="font-size: 16px">{{ evalResult.engine }}</div>
            <div class="stat-note">{{ evalResult.model_version || '—' }}</div>
          </div>
        </div>
        <div class="stack">
          <div v-for="item in evalResult.cases" :key="item.case_id" class="kv">
            <span>{{ item.subject }} · {{ item.question.slice(0, 24) }}…</span>
            <strong>
              <span class="tag" :class="item.passed ? 'tag-review' : 'tag-skipped'">{{ item.passed ? '通过' : '未通过' }}</span>
              {{ item.latency_ms }}ms
            </strong>
          </div>
        </div>
        <div class="small muted">
          {{ evalResult.cost_note }}{{ evalResult.note ? ' ' + evalResult.note : '' }}
        </div>
      </div>
      <div v-if="evalHistory.length" class="stack" style="margin-top: 10px">
        <div class="small muted">历史评测</div>
        <div v-for="run in evalHistory.slice(0, 5)" :key="run.run_id" class="kv">
          <span>{{ run.created_at ? run.created_at.slice(0, 16).replace('T', ' ') : '' }}</span>
          <strong>{{ Math.round(run.accuracy * 100) }}% · {{ run.avg_latency_ms }}ms · {{ run.engine }}</strong>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">云端能力</div>
          <div class="card-sub">拍题识别、语音和对象存储等服务的当前状态</div>
        </div>
        <button class="btn btn-ghost btn-sm" :disabled="cloudServicesLoading" @click="loadCloudServices">
          {{ cloudServicesLoading ? '读取中…' : '刷新状态' }}
        </button>
      </div>
      <div v-if="!cloudServices" class="empty">尚未读取云服务状态。</div>
      <div v-else class="stack" style="margin-top: 10px">
        <div
          v-for="item in cloudServices.items"
          :key="item.key"
          class="row-between"
          style="padding: 8px 0; border-bottom: 1px solid var(--line)"
        >
          <div>
            <strong>{{ item.name }}</strong>
            <span class="small muted" style="margin-left: 8px">{{ item.cloud }}</span>
            <div class="small muted">{{ item.detail }}</div>
          </div>
          <div class="row" style="gap: 6px; align-items: center">
            <span class="tag" :class="item.sdk_available ? 'tag-study' : 'tag-pending'">
              SDK {{ item.sdk_available ? '已安装' : '未安装' }}
            </span>
            <span class="tag" :class="statusClass[item.status] || 'tag-pending'">
              {{ statusLabel[item.status] || item.status }}
            </span>
          </div>
        </div>
        <div class="small muted">
        </div>
      </div>
    </div>

    <div v-if="detailOpen" class="it-mask" @click.self="closeDetail">
      <div class="it-modal" role="dialog" aria-modal="true">
        <div class="it-modal-head">
          <div>
            <div class="it-modal-title">{{ active?.name }}</div>
            <div class="small muted">{{ typeLabel[active?.type] || active?.type }} · {{ active?.key }}</div>
          </div>
          <div class="it-modal-head-right">
            <span class="tag" :class="statusClass[active?.status] || 'tag-pending'">
              {{ statusLabel[active?.status] || active?.status }}
            </span>
            <button class="it-close" aria-label="关闭详情" @click="closeDetail">×</button>
          </div>
        </div>

        <div class="it-facts">
          <div class="it-fact"><span>配置状态</span><strong>{{ active?.configured ? '已配置' : '未配置' }}</strong></div>
          <div class="it-fact">
            <span>探测延迟</span>
            <strong>{{ active?.latency_ms !== null && active?.latency_ms !== undefined ? `${active?.latency_ms} ms` : '—' }}</strong>
          </div>
          <div class="it-fact"><span>接入类型</span><strong>{{ typeLabel[active?.type] || active?.type }}</strong></div>
        </div>

        <div class="it-detail">{{ active?.detail }}</div>

        <template v-if="['database', 'cache'].includes(active?.key)">
          <div class="it-section-title">云端实例状态</div>
          <div v-if="cloudLoading" class="empty" style="padding: 10px">正在查询云端实例…</div>
          <div v-else-if="cloud" class="it-kb-result">
            <div class="small muted">{{ cloud.detail }}</div>
            <div v-for="inst in cloud.rds.items" :key="`rds-${inst.id}`" class="it-kb-row">
              <div class="it-kb-row-head">
                <b>RDS · {{ inst.name }}</b>
                <span class="small muted">{{ inst.status }}</span>
              </div>
              <p>公网：{{ (inst.public_ips || []).join('、') || '无' }} · 端口 {{ inst.port || '—' }}</p>
            </div>
            <div v-for="inst in cloud.dcs.items" :key="`dcs-${inst.id}`" class="it-kb-row">
              <div class="it-kb-row-head">
                <b>DCS · {{ inst.name }}</b>
                <span class="small muted">{{ inst.status }}</span>
              </div>
              <p>公网：{{ inst.public_ip || '无' }} · 端口 {{ inst.port || '—' }}</p>
            </div>
            <div v-if="cloud.rds?.error || cloud.dcs?.error" class="small muted">
              {{ cloud.rds?.error || cloud.dcs?.error }}
            </div>
            <div class="small muted">查询时间：{{ cloud.checked_at }}</div>
          </div>
        </template>

        <template v-if="active?.key === 'external'">
          <div class="it-section-title">知识来源（点击打开真实站点）</div>
          <div class="it-sources">
            <button
              v-for="source in activeSources"
              :key="source.key"
              class="it-source"
              type="button"
              @click="openSource(source)"
            >
              <span class="it-dot" :class="source.status === 'ok' ? 'ok' : 'bad'"></span>
              <span class="it-source-main">
                <b>{{ source.name }}</b>
                <small>{{ source.kind }} · {{ source.status === 'ok' ? `${source.latency_ms} ms` : source.detail }}</small>
              </span>
              <span class="it-source-link">打开 ↗</span>
            </button>
          </div>

          <div class="it-section-title">在线查询（真实请求外部知识库）</div>
          <div class="it-query">
            <input
              v-model.trim="kbTerm"
              placeholder="输入术语，例如 machine learning"
              @keydown.enter="lookupKnowledge"
            />
            <button class="btn" :disabled="kbLoading" @click="lookupKnowledge">
              {{ kbLoading ? '查询中...' : '查询知识库' }}
            </button>
          </div>
          <div v-if="kbLoading" class="empty" style="padding: 12px">正在并发请求 OpenAlex / Crossref / 百度百科...</div>
          <div v-else-if="kbResult" class="it-kb-result">
            <div class="small muted">「{{ kbResult.term }}」共 {{ kbResult.available_count }} / {{ kbResult.total }} 个来源返回结果</div>
            <div v-for="source in kbResult.sources" :key="source.key" class="it-kb-row">
              <div class="it-kb-row-head">
                <b>{{ source.name }}</b>
                <span class="small muted">{{ source.status === 'ok' ? `${source.latency_ms} ms` : source.status === 'empty' ? '无匹配' : '不可用' }}</span>
              </div>
              <p>{{ source.summary }}</p>
              <button v-if="source.link" class="link-btn" type="button" @click="openSource(source)">查看来源 ↗</button>
            </div>
          </div>
        </template>

        <template v-if="active?.key === 'question_bank'">
          <div class="it-section-title">题库连通探测</div>
          <div class="small muted">
            会先检查已接入的外部题库，再用当前目标的一个知识点取题，结果可供后续练习使用。
          </div>
          <div class="row" style="margin-top: 10px">
            <button
              class="btn"
              :disabled="questionBankTesting || !store.currentGoalId"
              @click="testQuestionBankApi"
            >
              {{ questionBankTesting ? '正在探测题库…' : '探测题库是否可用' }}
            </button>
            <span v-if="!store.currentGoalId" class="small muted">请先选择考试目标</span>
          </div>
          <div v-if="questionBankProbe" class="it-kb-result">
            <div class="it-kb-row">
              <div class="it-kb-row-head">
                <b>结果：{{ statusLabel[questionBankProbe.status] || questionBankProbe.status }}</b>
                <span v-if="questionBankProbe.latency_ms != null" class="small muted">
                  {{ questionBankProbe.latency_ms }} ms
                </span>
              </div>
              <p>{{ questionBankProbe.detail }}</p>
              <p v-if="questionBankProbe.kp_name">
                知识点：{{ questionBankProbe.kp_name }} · 通过校验：{{ questionBankProbe.question_count }} 题
              </p>
            </div>
          </div>
        </template>

        <div class="it-modal-foot">
          <button class="btn-ghost" @click="copyActive">复制接入信息</button>
          <button class="btn" :disabled="retesting" @click="retestActive">
            {{ retesting ? '正在探测...' : '重新探测此项' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
