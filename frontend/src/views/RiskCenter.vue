<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'
import DetailModal from '../components/DetailModal.vue'

const loading = ref(true)
const risks = ref([])
const detail = ref(null)
const cockpit = ref(null)
const resolving = ref('')
const ignored = ref([])
const result = ref(null)
const showHistory = ref(false)

function openRisk(risk) {
  detail.value = {
    title: risk.title,
    subtitle: `风险等级：${risk.level}`,
    rows: [
      { label: '触发原因', value: risk.reason },
      { label: '调整建议', value: risk.suggestion },
      { label: '调整前', value: risk.before },
      { label: '预计调整后', value: risk.after },
      { label: '建议动作', value: risk.action || '按建议调整' }
    ]
  }
}

const levelLabel = { high: '高风险', medium: '中风险', low: '提示' }
const levelClass = { high: 'tag-skipped', medium: 'tag-time', low: 'tag-study' }
const visibleRisks = computed(() => risks.value.filter((risk) => !ignored.value.includes(risk.code)))

const riskDistribution = computed(() => {
  const dist = { knowledge: 0, time: 0, execution: 0, memory: 0, strategy: 0 }
  for (const risk of risks.value) {
    if (dist[risk.code] !== undefined) dist[risk.code] += 1
  }
  return dist
})

const levelDistribution = computed(() => {
  const dist = { high: 0, medium: 0, low: 0 }
  for (const risk of risks.value) {
    dist[risk.level] += 1
  }
  return dist
})

const highRiskCount = computed(() => risks.value.filter(r => r.level === 'high').length)
const mediumRiskCount = computed(() => risks.value.filter(r => r.level === 'medium').length)
const lowRiskCount = computed(() => risks.value.filter(r => r.level === 'low').length)

async function load() {
  if (!store.currentGoalId) return
  if (!store.currentGoalId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const [riskList, cockpitData] = await Promise.all([
      api.risks(store.currentGoalId),
      api.cockpit(store.currentGoalId)
    ])
    risks.value = riskList
    cockpit.value = cockpitData
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function resolve(risk) {
  resolving.value = risk.code
  result.value = null
  try {
    const data = await api.resolveRisk(store.currentGoalId, risk.code)
    result.value = data
    notify(data.message)
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    resolving.value = ''
  }
}

function ignore(risk) {
  ignored.value = [...ignored.value, risk.code]
  notify(`已暂缓「${risk.title}」，稍后可在刷新后再次查看`)
}

watch(() => store.currentGoalId, load, { immediate: true })
onMounted(() => {})
</script>

<template>
  <div v-if="!store.currentGoalId" class="empty">
    还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建目标。
  </div>

  <div v-else class="stack">
    <div class="hero">
      <h1>风险救援中心</h1>
      <p>
        系统持续监测五类风险：知识、时间、执行、记忆、策略。每条风险都给出触发原因、
        建议动作，以及调整前后的准备度对比；你确认后系统才会改计划。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ cockpit?.readiness.score }}%</strong>
          <span>当前准备度</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ visibleRisks.length }}</strong>
          <span>待处理风险</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ highRiskCount }}</strong>
          <span>高风险</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ mediumRiskCount }}</strong>
          <span>中风险</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ lowRiskCount }}</strong>
          <span>低风险</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ cockpit?.gap_count + cockpit?.verified_gap_count }}</strong>
          <span>知识漏洞</span>
        </div>
      </div>
    </div>

    <div class="row-between">
      <div class="row">
        <button class="btn btn-ghost btn-sm" :aria-pressed="!showHistory" @click="showHistory = false">当前风险</button>
        <button class="btn btn-ghost btn-sm" :aria-pressed="showHistory" @click="showHistory = true">风险分布</button>
      </div>
      <span class="small muted">风险由系统自动监测，确认后才会执行调整</span>
    </div>

    <div v-if="result" class="card">
      <div class="card-head">
        <div>
          <div class="card-title">调整结果</div>
          <div class="card-sub">{{ result.message }}</div>
        </div>
        <span class="tag tag-review">已执行</span>
      </div>
      <div class="risk-compare">
        <div class="risk-compare-item">
          <span>调整前</span>
          <b>{{ result.before.score }}%</b>
          <small>今日任务 {{ result.before.today_tasks }} 个 · {{ result.before.today_minutes }} 分钟</small>
        </div>
        <div class="risk-arrow">→</div>
        <div class="risk-compare-item after">
          <span>调整后</span>
          <b>{{ result.after.score }}%</b>
          <small>今日任务 {{ result.after.today_tasks }} 个 · {{ result.after.today_minutes }} 分钟</small>
        </div>
      </div>
      <div v-if="result.changes?.length" class="stack" style="margin-top: 12px">
        <div v-for="(change, index) in result.changes" :key="index" class="task-reason" style="margin-top: 0">
          {{ change.detail }}
        </div>
      </div>
    </div>

    <div v-if="showHistory" class="split">
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">风险类型分布</div>
            <div class="card-sub">按风险代码统计当前风险数量</div>
          </div>
        </div>
        <div class="grid grid-2" style="gap: 10px; margin-top: 10px">
          <div class="stat" style="background: #fef2f2">
            <div class="stat-label">知识风险</div>
            <div class="stat-value" style="color: #dc2626">{{ riskDistribution.knowledge }}</div>
            <div class="stat-note">高权重知识点连续验证失败</div>
          </div>
          <div class="stat" style="background: #fffbeb">
            <div class="stat-label">时间风险</div>
            <div class="stat-value" style="color: #d97706">{{ riskDistribution.time }}</div>
            <div class="stat-note">待完成负荷超过剩余可用时间</div>
          </div>
          <div class="stat" style="background: #eff6ff">
            <div class="stat-label">执行风险</div>
            <div class="stat-value" style="color: #2563eb">{{ riskDistribution.execution }}</div>
            <div class="stat-note">连续未完成核心任务</div>
          </div>
          <div class="stat" style="background: #f0fdf4">
            <div class="stat-label">记忆风险</div>
            <div class="stat-value" style="color: #059669">{{ riskDistribution.memory }}</div>
            <div class="stat-note">到期复习积压</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">风险等级分布</div>
            <div class="card-sub">按风险等级统计当前风险数量</div>
          </div>
        </div>
        <div class="grid grid-2" style="gap: 10px; margin-top: 10px">
          <div class="stat" style="background: #fef2f2">
            <div class="stat-label">高风险</div>
            <div class="stat-value" style="color: #dc2626">{{ levelDistribution.high }}</div>
            <div class="bar" style="margin-top: 6px"><i :style="{ width: (levelDistribution.high / (levelDistribution.high + levelDistribution.medium + levelDistribution.low || 1)) * 100 + '%' }" style="background: #dc2626"></i></div>
          </div>
          <div class="stat" style="background: #fffbeb">
            <div class="stat-label">中风险</div>
            <div class="stat-value" style="color: #d97706">{{ levelDistribution.medium }}</div>
            <div class="bar" style="margin-top: 6px"><i :style="{ width: (levelDistribution.medium / (levelDistribution.high + levelDistribution.medium + levelDistribution.low || 1)) * 100 + '%' }" style="background: #d97706"></i></div>
          </div>
          <div class="stat" style="background: #f0fdf4">
            <div class="stat-label">低风险</div>
            <div class="stat-value" style="color: #059669">{{ levelDistribution.low }}</div>
            <div class="bar" style="margin-top: 6px"><i :style="{ width: (levelDistribution.low / (levelDistribution.high + levelDistribution.medium + levelDistribution.low || 1)) * 100 + '%' }" style="background: #059669"></i></div>
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="!visibleRisks.length" class="card">
      <div class="empty">当前没有需要处理的风险，保持当前节奏即可。</div>
    </div>

    <div v-else class="stack">
      <div v-for="risk in visibleRisks" :key="risk.code" class="card risk-card click-card" role="button" tabindex="0" @click="openRisk(risk)" @keydown.enter.prevent="openRisk(risk)" @keydown.space.prevent="openRisk(risk)">
        <div class="card-head">
          <div>
            <div class="card-title">{{ risk.title }}</div>
            <div class="card-sub">触发原因：{{ risk.reason }}</div>
          </div>
          <span class="tag" :class="levelClass[risk.level]">{{ levelLabel[risk.level] }}</span>
        </div>
        <div class="task-reason">{{ risk.suggestion }}</div>
        <div class="risk-before-after">
          <span>调整前：{{ risk.before }}</span>
          <span class="risk-arrow">→</span>
          <span>预计：{{ risk.after }}</span>
        </div>
        <div class="row" style="margin-top: 14px">
          <button class="btn" :disabled="resolving === risk.code" @click.stop="resolve(risk)">
            {{ resolving === risk.code ? '正在调整...' : `确认调整：${risk.action || '执行'}` }}
          </button>
          <button class="btn btn-ghost" @click="ignore(risk)">暂不处理</button>
        </div>
      </div>
    </div>

    <div class="split">
      <div class="card">
        <div class="card-title">风险类型与处理方式</div>
        <div class="stack" style="margin-top: 10px">
          <div class="kv"><span>知识风险</span><strong>高权重知识点连续验证失败 → 生成修复任务 + 验证题</strong></div>
          <div class="kv"><span>时间风险</span><strong>待完成负荷超过剩余可用时间 → 压缩低优先级并重排</strong></div>
          <div class="kv"><span>执行风险</span><strong>连续未完成核心任务 → 降低任务颗粒度，先恢复节奏</strong></div>
          <div class="kv"><span>记忆风险</span><strong>到期复习积压 → 插入针对性复习任务</strong></div>
          <div class="kv"><span>策略风险</span><strong>学习方式收益未知 → 先用小样本对照验证再放大投入</strong></div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">风险监测维度</div>
        <div class="stack" style="margin-top: 10px">
          <div class="kv"><span>准备度</span><strong>按高权重知识点覆盖、时间负荷与风险扣分计算</strong></div>
          <div class="kv"><span>任务完成</span><strong>连续未完成核心任务会触发执行风险</strong></div>
          <div class="kv"><span>错题增长</span><strong>错题增长会触发知识风险与时间风险</strong></div>
          <div class="kv"><span>复习积压</span><strong>到期复习积压会触发记忆风险</strong></div>
        </div>
        <div class="small muted" style="margin-top: 12px; line-height: 1.8">
          风险不会只提醒，确认后系统会直接调整计划并给出前后对比。
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">风险处理原则</div>
      <div class="stack" style="margin-top: 10px">
        <div class="kv"><span>自动监测</span><strong>系统持续监测，不需要手动触发</strong></div>
        <div class="kv"><span>确认执行</span><strong>风险不会自动执行，需要你确认后才会调整</strong></div>
        <div class="kv"><span>前后对比</span><strong>每次调整都会给出调整前后的准备度对比</strong></div>
        <div class="kv"><span>可追溯</span><strong>所有调整都会写入学习证据链，可追溯可复盘</strong></div>
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
