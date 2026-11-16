<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'
import DetailModal from '../components/DetailModal.vue'

const loading = ref(true)
const items = ref([])
const kind = ref('')
const expanded = ref(null)
const detail = ref(null)
const events = ref([])
const eventStats = ref(null)

const kinds = [
  { key: '', label: '全部' },
  { key: 'probe_generate', label: '主动探针' },
  { key: 'thought_trace', label: '思维回放' },
  { key: 'panel_review', label: '评审团' },
  { key: 'freshness_scan', label: '时效扫描' },
  { key: 'cognitive_load', label: '认知负荷' },
  { key: 'risk_knowledge', label: '风险救援' }
]

const kindLabel = {
  probe_generate: '主动探针',
  probe_answer: '探针作答',
  transfer_generate: '迁移测试',
  challenge_generate: '反脆弱挑战',
  thought_trace: '思维路径回放',
  panel_review: '多智能体评审',
  freshness_scan: '内容时效扫描',
  cognitive_load: '认知负荷调节',
  risk_knowledge: '知识风险救援',
  risk_time: '时间风险救援',
  risk_execution: '执行风险救援'
}

const engineCount = computed(() => {
  const result = { llm: 0, rule: 0 }
  for (const item of items.value) result[item.engine] = (result[item.engine] || 0) + 1
  return result
})

async function load() {
  if (!store.currentGoalId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const [evidenceData, eventsData, statsData] = await Promise.all([
      api.evidence(store.currentGoalId, kind.value),
      api.learningEvents(store.currentGoalId, { limit: 30 }),
      api.learningEventStats(store.currentGoalId)
    ])
    items.value = evidenceData
    events.value = eventsData.events || []
    eventStats.value = statsData
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

function toggle(item) {
  expanded.value = expanded.value === item.id ? null : item.id
}

function openDetail(item) {
  const payloadStr = JSON.stringify(item.payload, null, 2)
  detail.value = {
    title: kindLabel[item.kind] || item.kind,
    subtitle: item.subject + ' · ' + (item.engine === 'llm' ? 'DeepSeek' : '规则引擎'),
    rows: [
      { label: '类型', value: kindLabel[item.kind] || item.kind },
      { label: '主题', value: item.subject },
      { label: '引擎', value: item.engine === 'llm' ? 'DeepSeek 大模型' : '规则引擎' },
      { label: '输出', value: item.output },
      { label: '时间', value: item.created_at ? item.created_at.slice(0, 16).replace('T', ' ') : '—' },
      { label: '输入数据', value: payloadStr.length > 200 ? payloadStr.slice(0, 200) + '...' : payloadStr }
    ]
  }
}

watch(() => [store.currentGoalId, kind.value], load, { immediate: true })
onMounted(() => {})
</script>

<template>
  <div v-if="!store.currentGoalId" class="empty">
    还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建目标。
  </div>

  <div v-else class="stack">
    <div class="hero">
      <h1>学习证据链</h1>
      <p>
        每个 AI 判断都必须能追溯依据。这里按时间记录探针出题、错题回放、评审团意见、内容时效扫描、
        认知负荷调节与风险救援的输入数据、规则与输出，现场可以逐条展开核对。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ items.length }}</strong>
          <span>证据记录</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ engineCount.llm }}</strong>
          <span>模型生成</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ engineCount.rule }}</strong>
          <span>规则生成</span>
        </div>
        <div class="hero-meta-item">
          <strong>可追溯</strong>
          <span>输入 + 规则 + 输出</span>
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

    <div v-if="loading" class="empty">正在读取证据链...</div>
    <div v-else-if="!items.length" class="empty">
      当前筛选下还没有记录。去使用探针、评审团、时效扫描或风险救援后，证据会自动写入。
    </div>

    <div v-else class="evidence-timeline">
      <div v-for="item in items" :key="item.id" class="evidence-item click-line" role="button" tabindex="0" @click="toggle(item)" @keydown.enter.prevent="toggle(item)" @keydown.space.prevent="toggle(item)">
        <div class="evidence-dot" :class="item.engine"></div>
        <div class="evidence-body">
          <div class="row-between">
            <div>
              <b>{{ kindLabel[item.kind] || item.kind }}</b>
              <span class="small muted" style="margin-left: 8px">{{ item.subject }}</span>
            </div>
            <span class="tag" :class="item.engine === 'llm' ? 'tag-practice' : 'tag-study'">
              {{ item.engine === 'llm' ? 'DeepSeek' : '规则' }}
            </span>
          </div>
          <div class="small" style="margin-top: 6px">{{ item.output }}</div>
          <div class="row" style="margin-top: 6px; gap: 12px">
            <span class="small muted">{{ item.created_at.slice(0, 16).replace('T', ' ') }}</span>
            <button class="link-btn small" @click.stop="toggle(item)">
              {{ expanded === item.id ? '收起依据' : '展开依据' }}
            </button>
            <button class="link-btn small" @click.stop="openDetail(item)">详情</button>
          </div>
          <pre v-if="expanded === item.id" class="evidence-payload">{{ JSON.stringify(item.payload, null, 2) }}</pre>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">学习事件流</div>
          <div class="card-sub">答题、复习、任务完成等真实事件，按时间倒序</div>
        </div>
        <span v-if="eventStats" class="tag tag-study">
          共 {{ eventStats.total }} 条 · 近 7 天 {{ eventStats.recent_7d }}
        </span>
      </div>
      <div v-if="!events.length" class="empty">暂无学习事件。完成答题或任务后会自动记录。</div>
      <div v-else class="stack" style="margin-top: 10px">
        <div v-for="event in events" :key="event.id" class="kv">
          <span>{{ event.label }}</span>
          <strong>
            {{ event.occurred_at ? event.occurred_at.slice(0, 16).replace('T', ' ') : '' }}
            <span v-if="event.payload.correct === true" style="color: #059669"> · 正确</span>
            <span v-else-if="event.payload.correct === false" style="color: #dc2626"> · 错误</span>
            <span v-else-if="event.payload.title"> · {{ event.payload.title }}</span>
          </strong>
        </div>
        <div v-if="eventStats && eventStats.by_type.length" class="small muted">
          {{ eventStats.by_type.map((t) => t.label + ' ' + t.count).join(' · ') }}
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">为什么需要证据链</div>
      <div class="small muted" style="margin-top: 10px; line-height: 1.9">
        大模型会犯错，教育产品不能只给结论。证据链把每次判断的数据快照、规则与模型来源保留下来，
        用户可以追问「你为什么这样判断」，也可以据此修正数据或反馈错误。
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