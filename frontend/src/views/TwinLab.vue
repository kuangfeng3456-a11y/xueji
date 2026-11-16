<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'

const loading = ref(true)
const forecast = ref(null)
const twin = ref(null)
const detail = ref(null)
const monte = ref(null)
const phase = ref(null)
const fatigue = ref(null)

const horizons = computed(() => forecast.value?.horizons || [])
const current = computed(() => forecast.value?.current_mastery ?? 0)
const dataPoints = computed(() => forecast.value?.data_points ?? 0)
const insufficient = computed(() => forecast.value?.insufficient ?? true)

async function load() {
  if (!store.currentGoalId) return
  if (!store.currentGoalId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const [forecastData, twinData, monteData, phaseData, fatigueData] = await Promise.all([
      api.twinForecast(store.currentGoalId),
      api.twin(store.currentGoalId),
      api.monteCarloForecast(store.currentGoalId, 0.7),
      api.phaseInfo(store.currentGoalId),
      api.fatigueInfo(store.currentGoalId)
    ])
    forecast.value = forecastData
    twin.value = twinData
    monte.value = monteData
    phase.value = phaseData
    fatigue.value = fatigueData
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

function openHorizon(item) {
  detail.value = {
    title: `${item.horizon_days} 天后预测`,
    subtitle: `方法 ${forecast.value?.method || '—'} · 置信度 ${Math.round(item.confidence * 100)}%`,
    rows: [
      { label: '预测掌握度', value: `${Math.round(item.projected_mastery * 100)}%` },
      { label: '预测区间', value: `${Math.round(item.low * 100)}% ~ ${Math.round(item.high * 100)}%` },
      { label: '置信度', value: `${Math.round(item.confidence * 100)}%（数据点 ${dataPoints.value}）` },
      { label: '输入假设', value: item.assumptions.join('；') },
      { label: '说明', value: forecast.value?.uncertainty || '—' }
    ]
  }
}

watch(() => store.currentGoalId, load, { immediate: true })
onMounted(load)
</script>

<template>
  <div v-if="!store.currentGoalId" class="empty">
    还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建目标。
  </div>

  <div v-else-if="loading" class="empty">正在构建学习数字孪生...</div>

  <div v-else class="stack">
    <div class="hero">
      <h1>学习数字孪生实验室</h1>
      <p>
        以学生-知识点状态为单位维护掌握度快照，并在明确假设下推演 7 / 14 / 30 天的变化区间。
        预测不是成绩承诺：这里展示输入假设、区间与不确定性，数据不足时会明确标注。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ Math.round(current * 100) }}%</strong>
          <span>当前平均掌握度</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ dataPoints }}</strong>
          <span>数据点</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ forecast?.method || '—' }}</strong>
          <span>推演方法</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ insufficient ? '证据不足' : '可用' }}</strong>
          <span>数据状态</span>
        </div>
      </div>
    </div>

    <div class="grid grid-3" style="gap: 12px">
      <div
        v-for="item in horizons"
        :key="item.horizon_days"
        class="card click-card"
        role="button"
        tabindex="0"
        @click="openHorizon(item)"
        @keydown.enter.prevent="openHorizon(item)"
        @keydown.space.prevent="openHorizon(item)"
      >
        <div class="row-between">
          <div class="card-title">{{ item.horizon_days }} 天后</div>
          <span class="tag" :class="item.confidence >= 0.6 ? 'tag-review' : 'tag-time'">
            置信度 {{ Math.round(item.confidence * 100) }}%
          </span>
        </div>
        <div class="stat-value" style="margin-top: 12px">{{ Math.round(item.projected_mastery * 100) }}%</div>
        <div class="bar" style="margin-top: 8px"><i :style="{ width: Math.round(item.projected_mastery * 100) + '%' }"></i></div>
        <div class="small muted" style="margin-top: 8px">
          区间 {{ Math.round(item.low * 100) }}% ~ {{ Math.round(item.high * 100) }}%
        </div>
        <div class="small muted" style="margin-top: 4px">点击查看输入假设</div>
      </div>
    </div>

    <div v-if="phase" class="card">
      <div class="card-head">
        <div>
          <div class="card-title">备考阶段状态机</div>
          <div class="card-sub">阶段切换会自动调整任务配比、总量与目标保持率</div>
        </div>
        <span class="tag tag-study">{{ phase.label }} · 剩 {{ phase.days_left }} 天</span>
      </div>
      <div class="grid grid-3" style="gap: 10px; margin-top: 10px">
        <div class="stat">
          <div class="stat-label">任务配比</div>
          <div class="stat-value" style="font-size: 14px">{{ phase.ratio }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">目标保持率</div>
          <div class="stat-value">{{ Math.round(phase.target_retention * 100) }}%</div>
        </div>
        <div class="stat">
          <div class="stat-label">总量系数</div>
          <div class="stat-value">×{{ phase.total_factor }}</div>
        </div>
      </div>
    </div>

    <div v-if="monte" class="card">
      <div class="card-head">
        <div>
          <div class="card-title">
            蒙特卡洛预测区间
            <span class="tag tag-study" style="margin-left: 6px">模拟估算</span>
          </div>
          <div class="card-sub">
            {{ monte.samples }} 次抽样 · 随机种子 {{ monte.seed }} 可复算 · 目标 {{ monte.target_score }} 分
            · 非真实考试成绩
          </div>
        </div>
        <span class="tag" :class="monte.probability_to_target >= 0.6 ? 'tag-review' : 'tag-time'">
          达标概率 {{ Math.round(monte.probability_to_target * 100) }}%
        </span>
      </div>
      <div class="grid grid-3" style="gap: 10px; margin-top: 10px">
        <div class="stat">
          <div class="stat-label">P10 悲观（分）</div>
          <div class="stat-value">{{ monte.score_p10 }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">P50 中位（分）</div>
          <div class="stat-value">{{ monte.score_p50 }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">P90 乐观（分）</div>
          <div class="stat-value">{{ monte.score_p90 }}</div>
        </div>
      </div>
      <div class="small muted" style="margin-top: 10px">
        当前掌握度 {{ Math.round(monte.current_mastery * 100) }}% · 覆盖 {{ monte.knowledge_count }} 个知识点 · 剩余 {{ monte.days_left }} 天 ·
        近 28 天完成率 {{ Math.round(monte.completion_rate_28d * 100) }}% · {{ monte.method }}
      </div>
    </div>

    <div v-if="fatigue" class="split">
      <div class="card">
        <div class="card-title">疲劳指数</div>
        <div class="stat-value" style="margin-top: 8px">{{ fatigue.fatigue.index }}<span style="font-size: 14px"> / 100</span></div>
        <div class="bar" style="margin-top: 8px"><i :style="{ width: fatigue.fatigue.index + '%' }"></i></div>
        <div class="kv" style="margin-top: 8px"><span>等级</span><strong>{{ fatigue.fatigue.level }}</strong></div>
        <div class="small" style="margin-top: 8px">{{ fatigue.fatigue.suggestion }}</div>
        <div class="small muted" style="margin-top: 6px">{{ fatigue.fatigue.formula }}</div>
      </div>
      <div class="card">
        <div class="card-title">认知负荷</div>
        <div class="stat-value" style="margin-top: 8px">{{ fatigue.load.index }}<span style="font-size: 14px"> / 100</span></div>
        <div class="bar" style="margin-top: 8px"><i :style="{ width: fatigue.load.index + '%' }"></i></div>
        <div class="kv" style="margin-top: 8px"><span>等级</span><strong>{{ fatigue.load.level }}</strong></div>
        <div class="kv"><span>今日计划</span><strong>{{ fatigue.planned_minutes }} / {{ fatigue.daily_minutes }} 分钟</strong></div>
        <div class="small" style="margin-top: 8px">{{ fatigue.load.suggestion }}</div>
        <div class="small muted" style="margin-top: 6px">{{ fatigue.load.formula }}</div>
      </div>
    </div>

    <div class="split">
      <div class="card">
        <div class="card-title">推演假设与不确定性</div>
        <div class="stack" style="margin-top: 10px">
          <div class="kv"><span>方法版本</span><strong>{{ forecast?.method || '—' }}</strong></div>
          <div class="kv"><span>数据点</span><strong>{{ dataPoints }}</strong></div>
          <div class="kv"><span>不确定性</span><strong>{{ forecast?.uncertainty || '—' }}</strong></div>
        </div>
        <div v-if="horizons.length" class="stack" style="margin-top: 12px">
          <div class="small muted">输入假设</div>
          <div v-for="(item, index) in horizons[0].assumptions" :key="index" class="small">· {{ item }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">学习状态快照</div>
        <div v-if="!twin" class="empty" style="margin-top: 10px">暂无数字孪生数据。</div>
        <div v-else class="stack" style="margin-top: 10px">
          <div class="kv">
            <span>知识矩阵</span>
            <strong>{{ Array.isArray(twin.knowledge_matrix) ? twin.knowledge_matrix.length + ' 组' : '已生成' }}</strong>
          </div>
          <div class="kv">
            <span>错因分布</span>
            <strong>{{ Array.isArray(twin.mistake_distribution) ? twin.mistake_distribution.length + ' 类' : '已生成' }}</strong>
          </div>
          <div class="kv">
            <span>行为趋势</span>
            <strong>{{ Array.isArray(twin.behavior_trend) ? twin.behavior_trend.length + ' 个周期' : '已生成' }}</strong>
          </div>
          <div class="kv">
            <span>策略偏好</span>
            <strong>{{ Array.isArray(twin.strategy_ranking) ? twin.strategy_ranking.length + ' 种策略' : '已生成' }}</strong>
          </div>
          <div class="small muted">
            数字孪生同时保留掌握度、错因、行为趋势与策略偏好，可在「学情洞察」查看完整热力图与雷达。
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">为什么用区间而不是单点预测</div>
      <div class="small muted" style="margin-top: 10px; line-height: 1.9">
        学习状态受投入时间、完成率、复习间隔与中断影响。单点预测容易制造确定性错觉，
        因此这里给出区间、置信度与输入假设；数据点不足时显示「证据不足」，不把推演当作成绩承诺。
      </div>
    </div>

    <div v-if="detail" class="modal-mask" @click.self="detail = null">
      <div class="modal knowledge-modal">
        <div class="card-head">
          <div>
            <div class="card-title">{{ detail.title }}</div>
            <div class="card-sub">{{ detail.subtitle }}</div>
          </div>
          <button class="btn btn-ghost btn-sm" @click="detail = null">关闭</button>
        </div>
        <div class="stack">
          <div v-for="row in detail.rows" :key="row.label" class="kv">
            <span>{{ row.label }}</span>
            <strong>{{ row.value }}</strong>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>