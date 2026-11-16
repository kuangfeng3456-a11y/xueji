<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'
import DetailModal from '../components/DetailModal.vue'

const scales = ref([])
const resources = ref([])
const history = ref([])
const loading = ref(true)
const active = ref(null)
const answers = ref([])
const result = ref(null)
const submitting = ref(false)
const detail = ref(null)

const answeredCount = computed(() => answers.value.filter((item) => item >= 0).length)
const complete = computed(() => active.value && answeredCount.value === active.value.questions.length)
const scorePercent = computed(() =>
  result.value ? Math.round((result.value.score / result.value.max_score) * 100) : 0
)
const toneColor = computed(() => {
  if (!result.value) return '#0d9488'
  if (result.value.tone === 'good') return '#0d9488'
  if (result.value.tone === 'mild') return '#2563eb'
  if (result.value.tone === 'medium') return '#d97706'
  return '#dc2626'
})

async function load() {
  loading.value = true
  try {
    const [scaleData, hist] = await Promise.all([api.psychScales(), api.psychHistory()])
    scales.value = scaleData.scales
    resources.value = scaleData.resources
    history.value = hist.items
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function openScale(scale) {
  try {
    const data = await api.psychScale(scale.key)
    active.value = data
    answers.value = new Array(data.questions.length).fill(-1)
    result.value = null
  } catch (e) {
    notify(e.message, true)
  }
}

function choose(index, value) {
  const next = [...answers.value]
  next[index] = value
  answers.value = next
}

async function submit() {
  if (!active.value) return
  if (!complete.value) {
    notify('还有题目未作答', true)
    return
  }
  submitting.value = true
  try {
    result.value = await api.psychAssess({
      scale: active.value.key,
      answers: answers.value
    })
    notify(`评估完成：${result.value.level}`)
    const hist = await api.psychHistory()
    history.value = hist.items
  } catch (e) {
    notify(e.message, true)
  } finally {
    submitting.value = false
  }
}

function openHistory(item) {
  detail.value = {
    title: item.level || '历史评估',
    subtitle: `${item.scale.toUpperCase()} · ${item.score} / ${item.max_score}`,
    rows: [
      { label: '量表', value: item.scale.toUpperCase() },
      { label: '得分', value: `${item.score} / ${item.max_score}` },
      { label: '分级', value: item.level },
      { label: '解读引擎', value: item.engine === 'llm' ? 'DeepSeek' : '规则文案' },
      { label: '评估时间', value: (item.created_at || '').slice(0, 16).replace('T', ' ') },
      { label: '解读摘要', value: item.summary }
    ]
  }
}

function openEvidence(source) {
  detail.value = {
    title: source.name,
    subtitle: '外部知识库证据',
    rows: [
      { label: '来源', value: source.name },
      { label: '摘要', value: source.summary },
      { label: '链接', value: source.link }
    ]
  }
}

function openResource(resource) {
  detail.value = {
    title: resource.name,
    subtitle: resource.contact,
    rows: [
      { label: '联系方式', value: resource.contact },
      { label: '说明', value: resource.note },
      { label: '提示', value: '如遇紧急情况，请优先联系身边信任的人或直接前往医院。' }
    ]
  }
}

onMounted(load)

const mindStats = computed(() => ({
  scales: scales.value.length,
  assessments: history.value.length,
  lastScore: history.value.length ? history.value[0].score : '—',
  resources: resources.value.length
}))
</script>

<template>
  <div class="stack">
    <div class="hero">
      <h1>心理评估 · 状态与支持</h1>
      <p>
        使用公开标准自评量表（PHQ-9 / GAD-7 / PSS-10）做自我觉察。计分由本地规则完成，
        解读由 DeepSeek 生成，并同时检索 OpenAlex、Crossref 与百度百科作为外部证据。
        本模块不提供医学诊断，点击任意卡片可查看详情。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ scales.length }}</strong>
          <span>可用量表</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ history.length }}</strong>
          <span>历史评估</span>
        </div>
        <div class="hero-meta-item">
          <strong>3</strong>
          <span>外部证据源</span>
        </div>
        <div class="hero-meta-item">
          <strong>24h</strong>
          <span>公开援助热线</span>
        </div>
      </div>
    </div>

    <div v-if="loading" class="empty">正在加载量表...</div>

    <template v-else>
      <div class="grid grid-3">
        <div
          v-for="scale in scales"
          :key="scale.key"
          class="card click-card"
          :class="{ 'scale-active': active?.key === scale.key }"
          role="button"
          tabindex="0"
          @click="openScale(scale)"
          @keydown.enter.prevent="openScale(scale)"
          @keydown.space.prevent="openScale(scale)"
        >
          <div class="card-title">{{ scale.name }}</div>
          <div class="card-sub">{{ scale.intro }}</div>
          <div class="small muted" style="margin-top: 10px">
            {{ scale.question_count }} 题 · 满分 {{ scale.max_score }}
          </div>
          <div class="click-hint"><span>{{ active?.key === scale.key ? '正在作答' : '开始评估' }}</span><span>→</span></div>
        </div>
      </div>

      <div v-if="active" class="card">
        <div class="card-head">
          <div>
            <div class="card-title">{{ active.name }}</div>
            <div class="card-sub">{{ active.intro }} · 已完成 {{ answeredCount }} / {{ active.questions.length }}</div>
          </div>
          <span class="tag tag-study">{{ active.source }}</span>
        </div>

        <div class="stack" style="margin-top: 14px">
          <div v-for="(question, index) in active.questions" :key="index" class="psy-question">
            <div class="psy-question-title">{{ index + 1 }}. {{ question }}</div>
            <div class="psy-options">
              <button
                v-for="option in active.options"
                :key="option.value"
                type="button"
                class="psy-option"
                :class="{ active: answers[index] === option.value }"
                @click="choose(index, option.value)"
              >
                {{ option.label }}
              </button>
            </div>
          </div>
        </div>

        <button class="btn btn-block" style="margin-top: 16px" :disabled="submitting || !complete" @click="submit">
          {{ submitting ? '正在生成解读...' : complete ? '提交并生成解读' : `还有 ${active.questions.length - answeredCount} 题未作答` }}
        </button>
      </div>

      <div v-if="result" class="card">
        <div class="card-head">
          <div>
            <div class="card-title">评估结果</div>
            <div class="card-sub">{{ result.scale_name }} · {{ result.answered_at }}</div>
          </div>
          <span class="tag" :class="result.tone === 'good' ? 'tag-review' : result.tone === 'mild' ? 'tag-study' : result.tone === 'medium' ? 'tag-time' : 'tag-skipped'">
            {{ result.level }}
          </span>
        </div>

        <div class="psy-result">
          <div
            class="psy-ring"
            :style="{ background: `conic-gradient(${toneColor} ${scorePercent * 3.6}deg, #eef2f7 0deg)` }"
          >
            <div class="psy-ring-inner">
              <b>{{ result.score }}</b>
              <span>/ {{ result.max_score }}</span>
            </div>
          </div>
          <div class="stack" style="flex: 1; gap: 8px">
            <div class="task-reason">{{ result.interpretation.text }}</div>
            <div class="small muted">
              解读引擎：{{ result.interpretation.engine === 'llm' ? '智能解读' : '基础解读' }}
            </div>
          </div>
        </div>

        <div v-if="result.safety.urgent" class="psy-safety">{{ result.safety.message }}</div>

        <div class="card-sub" style="margin-top: 16px">外部知识库证据（点击查看来源）</div>
        <div v-if="result.evidence.available" class="stack" style="margin-top: 8px">
          <div
            v-for="source in result.evidence.sources"
            :key="source.name"
            class="kv click-line"
            style="padding: 8px; border-radius: 10px"
            role="button"
            tabindex="0"
            @click="openEvidence(source)"
            @keydown.enter.prevent="openEvidence(source)"
            @keydown.space.prevent="openEvidence(source)"
          >
            <span>{{ source.name }}</span>
            <strong class="small">{{ source.summary }}</strong>
          </div>
        </div>
        <div v-else class="empty" style="margin-top: 8px">外部知识库暂未返回证据，请稍后重试。</div>

        <div class="card-sub" style="margin-top: 16px">公开援助资源（点击查看）</div>
        <div class="grid grid-3" style="margin-top: 8px">
          <div
            v-for="resource in result.resources"
            :key="resource.contact"
            class="card click-card"
            role="button"
            tabindex="0"
            @click="openResource(resource)"
            @keydown.enter.prevent="openResource(resource)"
            @keydown.space.prevent="openResource(resource)"
          >
            <div class="card-title" style="font-size: 14px">{{ resource.name }}</div>
            <div class="stat-value" style="font-size: 20px; margin-top: 4px">{{ resource.contact }}</div>
            <div class="small muted">{{ resource.note }}</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">历史评估</div>
            <div class="card-sub">每次评估都会存入 RDS，可点击查看完整解读</div>
          </div>
        </div>
        <div v-if="!history.length" class="empty" style="margin-top: 10px">还没有评估记录。</div>
        <div v-else class="stack" style="margin-top: 10px">
          <div
            v-for="item in history"
            :key="item.id"
            class="kv click-line"
            style="padding: 8px; border-radius: 10px"
            role="button"
            tabindex="0"
            @click="openHistory(item)"
            @keydown.enter.prevent="openHistory(item)"
            @keydown.space.prevent="openHistory(item)"
          >
            <span>{{ (item.created_at || '').slice(0, 16).replace('T', ' ') }} · {{ item.scale.toUpperCase() }}</span>
            <strong>{{ item.score }} / {{ item.max_score }} · {{ item.level }}</strong>
          </div>
        </div>
      </div>
    </template>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">心理评估概览</div>
          <div class="card-sub">量表数量、评估历史与最近得分</div>
        </div>
      </div>
      <div class="grid grid-4" style="margin-top: 10px">
        <div class="stat">
          <div class="stat-label">量表数</div>
          <div class="stat-value">{{ mindStats.scales }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">评估次数</div>
          <div class="stat-value">{{ mindStats.assessments }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">最近得分</div>
          <div class="stat-value">{{ mindStats.lastScore }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">援助资源</div>
          <div class="stat-value">{{ mindStats.resources }}</div>
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