<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'
import DetailModal from '../components/DetailModal.vue'

const topic = ref('今日学习计划')
const review = ref(null)
const detail = ref(null)

function openOpinion(opinion) {
  detail.value = {
    title: opinion.role,
    subtitle: '多智能体评审发言',
    rows: [
      { label: '核心观点', value: opinion.view },
      { label: '主要担忧', value: opinion.concern },
      { label: '建议动作', value: opinion.suggestion }
    ]
  }
}
const history = ref([])
const loading = ref(true)
const running = ref(false)
const debate = ref(null)
const debateRuns = ref([])
const debateRunning = ref(false)

function openDebateAgent(item) {
  detail.value = {
    title: `${item.role}（${item.agent}）`,
    subtitle: `立场：${item.stance}`,
    rows: [
      { label: '观察', value: item.view },
      { label: '证据', value: item.evidence.length ? item.evidence.join('；') : '暂无结构化证据' },
      { label: '担忧', value: item.concern },
      { label: '建议', value: item.suggestion }
    ]
  }
}

async function runDebate() {
  debateRunning.value = true
  try {
    debate.value = await api.panelDebate(store.currentGoalId, topic.value)
    debateRuns.value = await api.panelRuns(store.currentGoalId, debate.value.run_id)
    notify('六角色辩论完成，裁决与轨迹已写入证据链')
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    debateRunning.value = false
  }
}

const topics = ['今日学习计划', '冲刺策略', '风险救援建议', '本周复盘']
const roleColors = {
  计划官: 'tag-study',
  诊断官: 'tag-practice',
  风险官: 'tag-skipped',
  教练: 'tag-review',
  学科导师: 'tag-review',
  证据审查官: 'tag-pending',
  planner: 'tag-study',
  diagnoser: 'tag-practice',
  tutor: 'tag-review',
  risk_officer: 'tag-skipped',
  evidence_reviewer: 'tag-pending'
}

async function load() {
  if (!store.currentGoalId) return
  if (!store.currentGoalId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    history.value = await api.panelReviews(store.currentGoalId)
    if (!review.value && history.value.length) review.value = history.value[0]
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function run() {
  running.value = true
  try {
    review.value = await api.panelReview(store.currentGoalId, topic.value)
    notify('评审团已完成审查，结论已写入证据链')
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    running.value = false
  }
}

function useHistory(item) {
  review.value = item
  topic.value = item.topic
}

watch(() => store.currentGoalId, load, { immediate: true })
onMounted(() => {})

const panelStats = computed(() => {
  const support =
    debate.value && debate.value.arbiter
      ? debate.value.arbiter.score
      : review.value && review.value.votes && review.value.votes.length
        ? Math.round(
            (review.value.votes.filter((vote) => vote === '支持').length /
              review.value.votes.length) *
              100
          )
        : 0
  return { reviews: history.value.length, roles: 6, support, runs: debateRuns.value.length }
})
</script>

<template>
  <div v-if="!store.currentGoalId" class="empty">
    还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建目标。
  </div>

  <div v-else class="stack">
    <div class="hero">
      <h1>多智能体学习评审团</h1>
      <p>
        不让一个 AI 直接替你决定。计划官、诊断官、风险官、教练分别从不同职责审查当前学习决策，
        给出观察、担忧与建议，再由主持人汇总裁决。每个角色意见都会进入学习证据链。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>4</strong>
          <span>评审角色</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ history.length }}</strong>
          <span>历史评审</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ review ? review.votes.filter((v) => v === '支持').length : '—' }}</strong>
          <span>本次支持票</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ review ? review.engine : '—' }}</strong>
          <span>评审引擎</span>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">发起一次评审</div>
          <div class="card-sub">选择议题，评审团会读取准备度、风险、漏洞与今日任务后独立发言</div>
        </div>
        <div class="row">
          <button class="btn btn-ghost" :disabled="debateRunning" @click="runDebate">
            {{ debateRunning ? '辩论中...' : '六角色辩论' }}
          </button>
          <button class="btn" :disabled="running" @click="run">
            {{ running ? '评审中...' : '召集评审团' }}
          </button>
        </div>
      </div>
      <div class="chip-list">
        <button
          v-for="item in topics"
          :key="item"
          class="chip"
          :class="{ active: topic === item }"
          @click="topic = item"
        >
          {{ item }}
        </button>
      </div>
      <div class="field" style="margin-top: 12px">
        <label>自定义议题</label>
        <input v-model.trim="topic" class="input" placeholder="例如：今晚要不要继续加练？" />
      </div>
    </div>

    <div v-if="loading" class="empty">正在读取评审记录...</div>

    <div v-else-if="review" class="stack">
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">评审结论：{{ review.topic }}</div>
            <div class="card-sub">由 {{ review.engine === 'llm' ? 'DeepSeek' : '规则评审' }} 生成</div>
          </div>
          <span class="tag tag-review">{{ review.votes.join(' / ') || '已汇总' }}</span>
        </div>
        <div class="panel-grid">
          <div v-for="opinion in review.opinions" :key="opinion.role" class="panel-card click-card" role="button" tabindex="0" @click="openOpinion(opinion)" @keydown.enter.prevent="openOpinion(opinion)" @keydown.space.prevent="openOpinion(opinion)">
            <div class="row-between">
              <b>{{ opinion.role }}</b>
              <span class="tag" :class="roleColors[opinion.role] || 'tag-pending'">发言</span>
            </div>
            <div class="small" style="margin-top: 6px">{{ opinion.view }}</div>
            <div class="small muted" style="margin-top: 4px">担忧：{{ opinion.concern }}</div>
            <div class="small" style="margin-top: 6px; color: var(--brand-dark)">建议：{{ opinion.suggestion }}</div>
          </div>
        </div>
        <div class="task-reason" style="margin-top: 14px">{{ review.verdict }}</div>
      </div>

      <div class="card">
        <div class="card-title">历史评审</div>
        <div v-if="!history.length" class="empty" style="margin-top: 10px">暂无历史。</div>
        <div v-else class="stack" style="margin-top: 10px">
          <button
            v-for="item in history"
            :key="item.id"
            class="experiment-row"
            style="text-align: left; cursor: pointer; width: 100%"
            @click="useHistory(item)"
          >
            <div class="row-between">
              <b>{{ item.topic }}</b>
              <span class="small muted">{{ item.created_at.slice(0, 10) }}</span>
            </div>
            <div class="small muted" style="margin-top: 4px">{{ item.verdict }}</div>
          </button>
        </div>
      </div>
    </div>

    <div v-else class="empty">
      还没有评审记录。选择议题后点击「召集评审团」。
    </div>

    <div v-if="debate" class="card">
      <div class="card-head">
        <div>
          <div class="card-title">六角色辩论：{{ debate.topic }}</div>
          <div class="card-sub">
            run {{ debate.run_id }} · {{ debate.engine === 'llm' ? '智能讲解' : '备用讲解' }} · 点击角色查看证据
          </div>
        </div>
        <span class="tag" :class="debate.arbiter && debate.arbiter.score >= 60 ? 'tag-review' : 'tag-time'">
          {{ debate.arbiter ? '支持率 ' + debate.arbiter.score + '%' : '待裁决' }}
        </span>
      </div>

      <div class="panel-grid">
        <div
          v-for="item in debate.opinions"
          :key="item.agent"
          class="panel-card click-card"
          role="button"
          tabindex="0"
          @click="openDebateAgent(item)"
          @keydown.enter.prevent="openDebateAgent(item)"
          @keydown.space.prevent="openDebateAgent(item)"
        >
          <div class="row-between">
            <b>{{ item.role }}</b>
            <span class="tag" :class="item.stance === '支持' ? 'tag-review' : 'tag-time'">{{ item.stance }}</span>
          </div>
          <div class="small" style="margin-top: 6px">{{ item.view }}</div>
          <div class="small muted" style="margin-top: 4px">
            证据 {{ item.evidence.length }} 条 · 担忧：{{ item.concern }}
          </div>
        </div>
      </div>

      <div v-if="debate.arbiter" class="task-reason" style="margin-top: 14px">
        <b>裁决器（{{ debate.arbiter.rule_version }}）：</b>{{ debate.arbiter.decision }}
        <div class="small muted" style="margin-top: 4px">{{ debate.arbiter.rationale }}</div>
        <div v-if="debate.arbiter.dissent && debate.arbiter.dissent.length" class="small" style="margin-top: 6px">
          分歧：{{ debate.arbiter.dissent.join('；') }}
        </div>
      </div>

      <div v-if="debateRuns.length" style="margin-top: 14px">
        <div class="small muted" style="margin-bottom: 6px">运行轨迹（agent_runs）</div>
        <div class="stack">
          <div v-for="(run, index) in debateRuns.slice(0, 6)" :key="run.run_id + index" class="kv">
            <span>{{ run.agent_name }}</span>
            <strong>{{ run.status }} · {{ run.engine }} · {{ run.latency_ms }}ms · {{ run.prompt_version }}</strong>
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">评审团概览</div>
          <div class="card-sub">角色数、历史评审、支持率与运行轨迹</div>
        </div>
      </div>
      <div class="grid grid-4" style="margin-top: 10px">
        <div class="stat">
          <div class="stat-label">评审角色</div>
          <div class="stat-value">{{ panelStats.roles }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">历史评审</div>
          <div class="stat-value">{{ panelStats.reviews }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">支持率</div>
          <div class="stat-value">{{ panelStats.support }}%</div>
        </div>
        <div class="stat">
          <div class="stat-label">运行轨迹</div>
          <div class="stat-value">{{ panelStats.runs }}</div>
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