<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'
import DetailModal from '../components/DetailModal.vue'

const loading = ref(true)
const detail = ref(null)

function openPlan(plan) {
  detail.value = {
    title: plan.label,
    subtitle: '未来模拟方案',
    rows: [
      { label: '考试日预测', value: `${Math.round(plan.projected_mastery * 100)}%` },
      { label: '结果区间', value: `${Math.round(plan.low * 100)}% – ${Math.round(plan.high * 100)}%` },
      { label: '每日投入', value: `${plan.daily_minutes} 分钟` },
      { label: '学习负荷', value: `${Math.round(plan.load_ratio * 100)}%` },
      { label: '风险等级', value: plan.risk_level === 'low' ? '低' : plan.risk_level === 'medium' ? '中' : '高' },
      { label: '关键假设', value: (plan.assumptions || []).join('；') }
    ],
    linkTo: '/plan',
    linkText: '按此方案生成计划'
  }
}
const applying = ref(false)
const data = ref(null)
const simulation = ref(null)
const customMinutes = ref(90)
const selectedScenario = ref('')

const chart = computed(() => {
  if (!data.value?.curve?.length) return { line: '', area: '', points: [], labels: [] }
  const width = 620
  const height = 220
  const padX = 36
  const padY = 24
  const points = data.value.curve.map((item, index) => {
    const x = padX + (index / Math.max(data.value.curve.length - 1, 1)) * (width - padX * 2)
    const y = height - padY - item.mastery * (height - padY * 2)
    return { x, y, ...item }
  })
  const line = points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ')
  const area = `${padX},${height - padY} ${line} ${width - padX},${height - padY}`
  return {
    width,
    height,
    padX,
    padY,
    points,
    line,
    area,
    targetY: height - padY - (data.value.target_mastery || 0.7) * (height - padY * 2),
    labels: points.map((point) => point.day.slice(5))
  }
})

const gapText = computed(() => {
  if (!data.value) return ''
  const gap = data.value.target_mastery - data.value.projected_mastery
  if (gap <= 0) return '当前节奏已超过目标，保持即可'
  return `距目标还差 ${Math.round(gap * 100)} 个百分点`
})

async function load(dailyMinutes) {
  if (!store.currentGoalId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const [forecastData, simulationData] = await Promise.all([
      api.forecast(store.currentGoalId, dailyMinutes),
      api.simulate(store.currentGoalId)
    ])
    data.value = forecastData
    simulation.value = simulationData
    customMinutes.value = dailyMinutes || store.goals.find((g) => g.id === store.currentGoalId)?.daily_minutes || 90
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function chooseScenario(scenario) {
  selectedScenario.value = scenario.label
  await load(scenario.daily_minutes)
}

async function simulate() {
  selectedScenario.value = '自定义'
  await load(Number(customMinutes.value))
}

async function applyPlan() {
  const minutes = data.value?.required_daily_minutes || data.value?.scenarios?.[2]?.daily_minutes || customMinutes.value
  applying.value = true
  try {
    const result = await api.applyForecast(store.currentGoalId, Number(minutes))
    notify(`已把每日时长调整为 ${minutes} 分钟并重排计划`)
    store.goals = await api.goals()
    await load(minutes)
  } catch (e) {
    notify(e.message, true)
  } finally {
    applying.value = false
  }
}

watch(() => store.currentGoalId, () => load(), { immediate: true })
onMounted(() => {})
</script>

<template>
  <div v-if="!store.currentGoalId" class="empty">
    还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建目标。
  </div>

  <div v-else-if="loading" class="empty">正在模拟冲刺结果...</div>

  <div v-else-if="data" class="stack">
    <div class="hero">
      <h1>未来模拟实验室</h1>
      <p>
        基于当前掌握度、知识点权重与剩余天数，模拟每天投入不同时长时考试日能达到的平均掌握度。
        不是拍脑袋定计划，而是先看见结果，再决定今天投入多少。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ data.days_left }}</strong>
          <span>距考试天数</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ Math.round(data.current_mastery * 100) }}%</strong>
          <span>当前掌握度</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ Math.round(data.projected_mastery * 100) }}%</strong>
          <span>预计考试日 · 模拟估算</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ data.required_daily_minutes ? data.required_daily_minutes + ' 分钟' : '较难达成' }}</strong>
          <span>达标所需每日</span>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">掌握度预测曲线</div>
          <div class="card-sub">
            目标线 {{ Math.round(data.target_mastery * 100) }}% · {{ gapText }}
          </div>
        </div>
        <span class="tag tag-study">{{ selectedScenario || '当前节奏' }}</span>
      </div>

      <svg :viewBox="`0 0 ${chart.width} ${chart.height}`" class="sprint-svg">
        <line
          :x1="chart.padX"
          :y1="chart.targetY"
          :x2="chart.width - chart.padX"
          :y2="chart.targetY"
          stroke="#f59e0b"
          stroke-dasharray="6 5"
          stroke-width="1.5"
        />
        <text :x="chart.width - chart.padX" :y="chart.targetY - 7" text-anchor="end" font-size="10" fill="#b45309">
          目标 {{ Math.round(data.target_mastery * 100) }}%
        </text>
        <polygon :points="chart.area" fill="rgba(13, 148, 136, 0.12)" />
        <polyline :points="chart.line" fill="none" stroke="#0d9488" stroke-width="3" stroke-linejoin="round" />
        <circle
          v-for="(point, index) in chart.points"
          :key="index"
          :cx="point.x"
          :cy="point.y"
          r="3.5"
          fill="#fff"
          stroke="#0d9488"
          stroke-width="2"
        />
        <text
          v-for="(label, index) in chart.labels"
          :key="`label-${index}`"
          :x="chart.points[index].x"
          :y="chart.height - 5"
          text-anchor="middle"
          font-size="9"
          fill="#94a3b8"
        >
          {{ label }}
        </text>
      </svg>

      <div class="task-reason">{{ data.recommendation }}</div>
    </div>

    <div class="grid grid-3">
      <button
        v-for="scenario in data.scenarios"
        :key="scenario.label"
        class="scenario-card"
        :class="{ active: selectedScenario === scenario.label }"
        @click="chooseScenario(scenario)"
      >
        <div class="scenario-label">{{ scenario.label }}</div>
        <div class="scenario-value">{{ Math.round(scenario.projected_mastery * 100) }}%</div>
        <div class="small muted">每天 {{ scenario.daily_minutes }} 分钟</div>
        <div class="tag" :class="scenario.feasible ? 'tag-review' : 'tag-skipped'" style="margin-top: 8px">
          {{ scenario.feasible ? '可达目标' : '低于目标' }}
        </div>
      </button>
    </div>

    <div v-if="simulation" class="card">
      <div class="card-head">
        <div>
          <div class="card-title">多策略方案对比</div>
          <div class="card-sub">同时比较时间投入与漏洞修复顺序，展示结果区间而非单点承诺</div>
        </div>
        <span class="tag tag-study">4 个方案</span>
      </div>
      <div class="grid grid-2">
        <div v-for="plan in simulation.plans" :key="plan.key" class="sim-plan click-card" role="button" tabindex="0" @click="openPlan(plan)" @keydown.enter.prevent="openPlan(plan)" @keydown.space.prevent="openPlan(plan)">
          <div class="row-between">
            <b>{{ plan.label }}</b>
            <span class="tag" :class="plan.risk_level === 'low' ? 'tag-review' : plan.risk_level === 'medium' ? 'tag-time' : 'tag-skipped'">
              {{ plan.risk_level === 'low' ? '风险低' : plan.risk_level === 'medium' ? '风险中' : '风险高' }}
            </span>
          </div>
          <div class="sim-value">{{ Math.round(plan.projected_mastery * 100) }}%</div>
          <div class="small muted">
            区间 {{ Math.round(plan.low * 100) }}%–{{ Math.round(plan.high * 100) }}% ·
            每天 {{ plan.daily_minutes }} 分钟 · 负荷 {{ Math.round(plan.load_ratio * 100) }}%
          </div>
          <div class="small muted" style="margin-top: 6px">
            {{ plan.assumptions[plan.assumptions.length - 1] }}
          </div>
        </div>
      </div>
      <div class="task-reason" style="margin-top: 12px">{{ simulation.recommendation }}</div>
      <div class="small muted" style="margin-top: 8px">{{ simulation.uncertainty }}</div>
    </div>

    <div class="split">
      <div class="card">
        <div class="card-title">自定义模拟</div>
        <div class="card-sub" style="margin-bottom: 12px">拖动或输入每日分钟，立即看到考试日预测</div>
        <div class="row">
          <input v-model.number="customMinutes" class="input" type="range" min="20" max="300" step="10" style="flex: 1" />
          <b style="min-width: 70px; text-align: right">{{ customMinutes }} 分钟</b>
        </div>
        <button class="btn btn-block" style="margin-top: 14px" @click="simulate">模拟这个投入</button>
      </div>

      <div class="card">
        <div class="card-title">把预测变成计划</div>
        <div class="card-sub" style="margin-bottom: 12px">
          应用推荐时长后，系统会更新每日预算并重排后续任务
        </div>
        <div class="kv">
          <span>推荐每日时长</span>
          <strong>{{ data.required_daily_minutes ? data.required_daily_minutes + ' 分钟' : '难以达成，建议缩减范围' }}</strong>
        </div>
        <div class="kv">
          <span>预计提升</span>
          <strong>
            +{{ Math.max(0, Math.round((data.projected_mastery - data.current_mastery) * 100)) }} 个百分点
          </strong>
        </div>
        <button class="btn btn-teal btn-block" style="margin-top: 14px" :disabled="applying" @click="applyPlan">
          {{ applying ? '正在应用...' : '应用推荐时长并重排' }}
        </button>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">AI 冲刺策略</div>
          <div class="card-sub">DeepSeek 基于预测结果生成，不改动预测数值</div>
        </div>
        <span class="tag" :class="data.ai_engine === 'llm' ? 'tag-practice' : 'tag-study'">
          {{ data.ai_engine === 'llm' ? '智能讲解' : '备用讲解' }}
        </span>
      </div>
      <div class="task-reason" style="margin-top: 0">{{ data.ai_strategy || data.recommendation }}</div>
    </div>

    <div class="card">
      <div class="card-title">模型怎么算的</div>
      <div class="stack" style="margin-top: 10px">
        <div class="kv"><span>每日覆盖</span><strong>每天按薄弱度与权重优先覆盖约 {{ Math.max(1, Math.floor(customMinutes / 20)) }} 个知识点</strong></div>
        <div class="kv"><span>单次提升</span><strong>每次覆盖向 1.0 靠近 12%</strong></div>
        <div class="kv"><span>遗忘衰减</span><strong>未复习知识点每天衰减 0.5%</strong></div>
        <div class="kv"><span>目标设定</span><strong>当前掌握度 + 20 个百分点，最高 90%</strong></div>
      </div>
      <div class="small muted" style="margin-top: 10px">
        这是可解释的近似模型，用于比较不同投入的相对效果，不替代真实考试结果。
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