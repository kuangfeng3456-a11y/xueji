<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'
import DetailModal from '../components/DetailModal.vue'

const loading = ref(true)
const data = ref(null)
const twin = ref(null)
const forecast = ref(null)
const resting = ref(false)
const detail = ref(null)

function openDetail(payload) {
  detail.value = payload
}

function openRadar(item) {
  openDetail({
    title: item.label,
    subtitle: '能力雷达',
    rows: [
      { label: '当前水平', value: `${Math.round(item.value * 100)}%` },
      { label: '含义', value: '该维度由近期任务完成、错题与自测结果综合计算。' },
      { label: '提升建议', value: item.value < 0.5 ? '优先安排基础训练，并加入对应知识点闪卡。' : '保持训练频率，用高难度题目巩固。' }
    ],
    linkTo: '/plan',
    linkText: '去调整计划'
  })
}

function openBadge(badge) {
  openDetail({
    title: badge.name,
    subtitle: badge.unlocked ? '成就已解锁' : '成就未解锁',
    rows: [
      { label: '状态', value: badge.unlocked ? '已解锁' : '未解锁' },
      { label: '说明', value: badge.description },
      { label: '进度', value: `${badge.progress} / ${badge.target} ${badge.unit}` }
    ]
  })
}

function openMatrix(point) {
  openDetail({
    title: point.name,
    subtitle: '数字孪生 · 知识矩阵',
    rows: [
      { label: '掌握度', value: `${Math.round(point.mastery * 100)}%` },
      { label: '错题数', value: `${point.mistake_count} 道` },
      { label: '状态', value: point.status }
    ],
    linkTo: '/knowledge-map',
    linkText: '查看知识漏洞地图'
  })
}

function openMistakeDist(item) {
  const advice =
    item.category === 'concept'
      ? '回到定义与边界，做概念辨析。'
      : item.category === 'method'
        ? '补齐解题步骤，按例题复述方法。'
        : item.category === 'careless'
          ? '加入检查清单与限时训练。'
          : '调整时间分配与做题节奏。'
  openDetail({
    title: item.label,
    subtitle: `错因分布 · 共 ${item.count} 道`,
    rows: [
      { label: '数量', value: `${item.count} 道` },
      { label: '应对建议', value: advice }
    ],
    linkTo: '/mistakes',
    linkText: '去错题本'
  })
}

function openTrend(item) {
  openDetail({
    title: `${item.week_start} 这一周`,
    subtitle: '行为趋势',
    rows: [
      { label: '任务完成率', value: `${Math.round(item.completion_rate * 100)}%` },
      { label: '说明', value: '该周完成率来自真实任务打卡记录，用于观察节奏变化。' }
    ],
    linkTo: '/report',
    linkText: '查看周报'
  })
}

function openStrategy(item) {
  openDetail({
    title: item.label,
    subtitle: '个人策略收益排行',
    rows: [
      { label: '平均收益', value: `${Math.round(item.avg_gain * 100)} pp` },
      { label: '实验次数', value: `${item.experiments} 次` },
      { label: '说明', value: '来自历史对照实验的真实收益，样本量较小时仅供参考。' }
    ]
  })
}

function twinColor(value) {
  return `hsl(${Math.round(Math.max(0, Math.min(1, value)) * 140)}, 65%, 88%)`
}

const levelNames = ['无学习', '轻量', '适中', '高强度', '冲刺']
const fatigueLabel = { low: '状态良好', medium: '需要留意', high: '疲劳偏高' }
const fatigueColor = { low: '#0d9488', medium: '#d97706', high: '#dc2626' }

const heatCells = computed(() => {
  if (!data.value?.heatmap?.length) return []
  const cells = []
  const first = new Date(data.value.heatmap[0].day)
  const pad = (first.getDay() + 6) % 7
  for (let index = 0; index < pad; index += 1) cells.push({ blank: true, key: `pad-${index}` })
  for (const item of data.value.heatmap) cells.push({ ...item, key: item.day })
  return cells
})

const radarPolygon = computed(() => {
  if (!data.value?.radar) return ''
  const cx = 130
  const cy = 130
  const radius = 92
  return data.value.radar
    .map((item, index) => {
      const angle = -Math.PI / 2 + (index * 2 * Math.PI) / 5
      const value = Math.max(0.04, item.value)
      return `${(cx + Math.cos(angle) * radius * value).toFixed(1)},${(cy + Math.sin(angle) * radius * value).toFixed(1)}`
    })
    .join(' ')
})

const radarGrid = computed(() => {
  const cx = 130
  const cy = 130
  const radius = 92
  return [0.25, 0.5, 0.75, 1].map((ratio) =>
    Array.from({ length: 5 }, (_, index) => {
      const angle = -Math.PI / 2 + (index * 2 * Math.PI) / 5
      return `${(cx + Math.cos(angle) * radius * ratio).toFixed(1)},${(cy + Math.sin(angle) * radius * ratio).toFixed(1)}`
    }).join(' ')
  )
})

const radarAxes = computed(() => {
  const cx = 130
  const cy = 130
  const radius = 92
  return Array.from({ length: 5 }, (_, index) => {
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / 5
    return {
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius,
      labelX: cx + Math.cos(angle) * (radius + 22),
      labelY: cy + Math.sin(angle) * (radius + 22) + 4,
      label: data.value?.radar[index]?.label || ''
    }
  })
})

const unlockedCount = computed(
  () => (data.value?.achievements || []).filter((item) => item.unlocked).length
)

async function load() {
  if (!store.currentGoalId) return
  if (!store.currentGoalId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const [insightData, twinData, forecastData] = await Promise.all([
      api.insights(store.currentGoalId),
      api.twin(store.currentGoalId),
      api.twinForecast(store.currentGoalId)
    ])
    data.value = insightData
    twin.value = twinData
    forecast.value = forecastData
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function rest() {
  resting.value = true
  try {
    const result = await api.rest(store.currentGoalId)
    notify(result.summary)
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    resting.value = false
  }
}

watch(() => store.currentGoalId, load, { immediate: true })
</script>

<template>
  <div v-if="!store.currentGoalId" class="empty">
    还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建目标。
  </div>

  <div v-else-if="loading" class="empty">正在汇总学习数据...</div>

  <div v-else-if="data" class="stack">
    <div class="hero">
      <h1>学情洞察 · 看见你的学习轨迹</h1>
      <p>
        热力图看坚持，雷达看结构，疲劳指数看状态。学迹不只记录你学了多久，
        还会判断你是否该继续加压，还是该主动减负。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ data.streak }}</strong>
          <span>连续打卡</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ Math.round(data.total_minutes / 60) }}</strong>
          <span>近 12 周学习小时</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ data.active_days }}</strong>
          <span>有学习的天数</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ unlockedCount }} / {{ data.achievements.length }}</strong>
          <span>解锁徽章</span>
        </div>
      </div>
    </div>

    <div class="split">
      <div class="stack">
        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">学习热力图</div>
              <div class="card-sub">近 12 周每日完成分钟，颜色越深投入越高</div>
            </div>
            <div class="heat-legend">
              <span>少</span>
              <i v-for="level in 5" :key="level" :class="`heat-${level - 1}`"></i>
              <span>多</span>
            </div>
          </div>
          <div class="heatmap-scroll">
            <div class="heatmap">
              <div
                v-for="cell in heatCells"
                :key="cell.key"
                class="heat-cell"
                :class="cell.blank ? 'blank' : `heat-${cell.level}`"
                :title="cell.blank ? '' : `${cell.day} · ${cell.minutes} 分钟 · ${cell.done} 个任务 · ${levelNames[cell.level]}`"
              ></div>
            </div>
          </div>
          <div class="small muted" style="margin-top: 10px">
            学习分钟来自每日完成任务时长；专注分钟单独记录在强制学习中。
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">能力雷达</div>
              <div class="card-sub">掌握、节奏、专注、纠错、坚持五个维度</div>
            </div>
            <span class="tag tag-review">综合 {{ Math.round(data.radar_score * 100) }}%</span>
          </div>
          <div class="radar-wrap">
            <svg viewBox="0 0 260 260" class="radar-svg">
              <polygon
                v-for="(grid, index) in radarGrid"
                :key="index"
                :points="grid"
                fill="none"
                stroke="#e2e8f0"
                stroke-width="1"
              />
              <line
                v-for="(axis, index) in radarAxes"
                :key="`axis-${index}`"
                :x1="130"
                :y1="130"
                :x2="axis.x"
                :y2="axis.y"
                stroke="#e2e8f0"
                stroke-width="1"
              />
              <polygon
                :points="radarPolygon"
                fill="rgba(37, 99, 235, 0.18)"
                stroke="#2563eb"
                stroke-width="2"
              />
              <text
                v-for="(axis, index) in radarAxes"
                :key="`label-${index}`"
                :x="axis.labelX"
                :y="axis.labelY"
                text-anchor="middle"
                font-size="10"
                fill="#64748b"
              >
                {{ axis.label }}
              </text>
            </svg>
            <div class="radar-values">
              <div v-for="item in data.radar" :key="item.key" class="radar-value click-row" role="button" tabindex="0" @click="openRadar(item)" @keydown.enter.prevent="openRadar(item)" @keydown.space.prevent="openRadar(item)">
                <span>{{ item.label }}</span>
                <b>{{ Math.round(item.value * 100) }}%</b>
                <div class="bar"><i :style="{ width: Math.max(item.value * 100, 2) + '%' }"></i></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="stack">
        <div v-if="data.ai_report" class="card">
          <div class="card-head">
            <div>
              <div class="card-title">AI 学情诊断</div>
              <div class="card-sub">DeepSeek 基于热力图、能力雷达与疲劳数据生成</div>
            </div>
            <span class="tag" :class="data.ai_report.engine === 'llm' ? 'tag-practice' : 'tag-study'">
              {{ data.ai_report.engine === 'llm' ? '智能讲解' : '备用讲解' }}
            </span>
          </div>
          <div class="pre-wrap">{{ data.ai_report.text }}</div>
        </div>

        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">疲劳与干预</div>
              <div class="card-sub">结合专注中断、离开次数、错题增长与连续天数</div>
            </div>
            <span class="tag" :style="{ background: fatigueColor[data.fatigue.level] + '18', color: fatigueColor[data.fatigue.level] }">
              {{ fatigueLabel[data.fatigue.level] }}
            </span>
          </div>

          <div class="fatigue-score">
            <div
              class="fatigue-ring"
              :style="{
                background: `conic-gradient(${fatigueColor[data.fatigue.level]} ${data.fatigue.score * 3.6}deg, #eef2f7 0deg)`
              }"
            >
              <div class="fatigue-inner">
                <b>{{ data.fatigue.score }}</b>
                <span>疲劳指数</span>
              </div>
            </div>
            <div class="fatigue-factors">
              <div v-for="(factor, index) in data.fatigue.factors" :key="index" class="small muted">
                · {{ factor }}
              </div>
            </div>
          </div>

          <div class="task-reason" style="margin-top: 14px">{{ data.fatigue.advice }}</div>

          <button
            v-if="data.fatigue.level !== 'low'"
            class="btn btn-block"
            style="margin-top: 14px"
            :disabled="resting"
            @click="rest"
          >
            {{ resting ? '正在降载...' : `一键减负：今日只留 1 个任务，其余顺延` }}
          </button>
        </div>

        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">成就徽章</div>
              <div class="card-sub">已解锁 {{ unlockedCount }} / {{ data.achievements.length }}</div>
            </div>
          </div>
          <div class="badge-grid">
            <div
              v-for="badge in data.achievements"
              :key="badge.code"
              class="badge-card click-card"
              :class="{ unlocked: badge.unlocked }"
              role="button"
              tabindex="0"
              @click="openBadge(badge)"
              @keydown.enter.prevent="openBadge(badge)"
              @keydown.space.prevent="openBadge(badge)"
            >
              <div class="badge-icon">{{ badge.unlocked ? '★' : '☆' }}</div>
              <div class="badge-name">{{ badge.name }}</div>
              <div class="badge-desc">{{ badge.description }}</div>
              <div class="bar" style="margin-top: 8px">
                <i :style="{ width: Math.min(100, (badge.progress / badge.target) * 100) + '%' }"></i>
              </div>
              <div class="small muted" style="margin-top: 4px">
                {{ badge.progress }} / {{ badge.target }} {{ badge.unit }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="twin" class="card">
      <div class="card-head">
        <div>
          <div class="card-title">学习数字孪生</div>
          <div class="card-sub">知识矩阵、错因分布、行为趋势与策略偏好</div>
        </div>
        <router-link class="btn btn-ghost btn-sm" to="/knowledge-map">查看漏洞地图</router-link>
      </div>

      <div class="twin-grid">
        <div>
          <div class="small muted" style="margin-bottom: 8px">知识热力矩阵（颜色越浅掌握越低）</div>
          <div class="twin-matrix">
            <div
              v-for="point in twin.knowledge_matrix"
              :key="point.kp_id"
              class="twin-cell click-card"
              :style="{ background: twinColor(point.mastery) }"
              role="button"
              tabindex="0"
              @click="openMatrix(point)"
              @keydown.enter.prevent="openMatrix(point)"
              @keydown.space.prevent="openMatrix(point)"
              :title="`${point.name} · 掌握 ${Math.round(point.mastery * 100)}% · 错题 ${point.mistake_count} 道 · ${point.status}`"
            >
              {{ point.name }}
            </div>
          </div>
        </div>

        <div class="stack" style="gap: 10px">
          <div class="small muted">错因分布</div>
          <div v-for="item in twin.mistake_distribution" :key="item.category" class="click-line" style="padding: 6px; border-radius: 8px" role="button" tabindex="0" @click="openMistakeDist(item)" @keydown.enter.prevent="openMistakeDist(item)" @keydown.space.prevent="openMistakeDist(item)">
            <div class="row-between small">
              <span>{{ item.label }}</span>
              <b>{{ item.count }}</b>
            </div>
            <div class="bar" style="margin-top: 4px">
              <i :style="{ width: Math.max(2, Math.min(100, item.count * 12)) + '%' }"></i>
            </div>
          </div>
        </div>
      </div>

      <div class="grid grid-2" style="margin-top: 18px">
        <div>
          <div class="small muted" style="margin-bottom: 8px">行为趋势（近 8 周完成率）</div>
          <div class="trend-bars">
            <div v-for="item in twin.behavior_trend" :key="item.week_start" class="trend-item click-card" role="button" tabindex="0" @click="openTrend(item)" @keydown.enter.prevent="openTrend(item)" @keydown.space.prevent="openTrend(item)">
              <i :style="{ height: Math.max(4, item.completion_rate * 100) + '%' }"></i>
              <span>{{ item.week_start.slice(5) }}</span>
            </div>
          </div>
        </div>
        <div>
          <div class="small muted" style="margin-bottom: 8px">策略偏好</div>
          <div v-if="!twin.strategy_ranking.length" class="empty">完成策略实验后这里会显示个人收益排行。</div>
          <div v-else class="stack" style="gap: 8px">
            <div v-for="(item, index) in twin.strategy_ranking" :key="item.strategy" class="strategy-row click-line" style="padding: 6px; border-radius: 8px" role="button" tabindex="0" @click="openStrategy(item)" @keydown.enter.prevent="openStrategy(item)" @keydown.space.prevent="openStrategy(item)">
              <span class="rank-badge" :class="`rank-${index + 1}`">{{ index + 1 }}</span>
              <div style="flex: 1">
                <div class="row-between small">
                  <b>{{ item.label }}</b>
                  <span>{{ Math.round(item.avg_gain * 100) }}pp / {{ item.experiments }} 次</span>
                </div>
                <div class="bar" style="margin-top: 4px">
                  <i :style="{ width: Math.max(4, Math.min(100, item.avg_gain * 500)) + '%' }"></i>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="forecast" class="stack" style="margin-top: 18px">
        <div class="row-between">
          <div class="small muted">情景推演（{{ forecast.method }}）</div>
          <span class="tag" :class="forecast.insufficient ? 'tag-time' : 'tag-review'">
            {{ forecast.insufficient ? '证据不足' : '数据点 ' + forecast.data_points }}
          </span>
        </div>
        <div class="grid grid-3" style="gap: 10px">
          <div v-for="h in forecast.horizons" :key="h.horizon_days" class="stat">
            <div class="stat-label">{{ h.horizon_days }} 天后</div>
            <div class="stat-value">{{ Math.round(h.projected_mastery * 100) }}%</div>
            <div class="small muted">区间 {{ Math.round(h.low * 100) }}% ~ {{ Math.round(h.high * 100) }}%</div>
            <div class="bar" style="margin-top: 6px"><i :style="{ width: Math.round(h.projected_mastery * 100) + '%' }"></i></div>
            <div class="stat-note">置信度 {{ Math.round(h.confidence * 100) }}%</div>
          </div>
        </div>
        <div class="small muted">
          {{ forecast.uncertainty }} 假设：{{ forecast.horizons[0] ? forecast.horizons[0].assumptions.join('；') : '' }}
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