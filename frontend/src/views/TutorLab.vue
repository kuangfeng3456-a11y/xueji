<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'
import AppSelect from '../components/AppSelect.vue'
import { streamSse } from '../sse'

const points = ref([])
const kpId = ref('')
const kpOptions = computed(() => points.value.map((point) => ({ value: point.id, label: point.name })))
const modeOptions = [
  { value: 'hint', label: '提示模式' },
  { value: 'explain', label: '讲解模式' },
  { value: 'exam', label: '考试模式' }
]
const levelOptions = [
  { value: 'direction', label: '方向提示' },
  { value: 'concept', label: '概念提示' },
  { value: 'step', label: '步骤提示' },
  { value: 'full', label: '完整讲解' }
]
const resourceOptions = [
  { value: 'flashcard', label: '闪卡' },
  { value: 'variant', label: '变式题' },
  { value: 'outline', label: '微课提纲' }
]

const mode = ref('hint')
const level = ref('concept')
const message = ref('')
const reply = ref(null)
const asking = ref(false)
const streaming = ref(false)
const streamStage = ref('')
const streamResult = ref(null)
const streamFallback = ref('')
const recallText = ref('')
const recallResult = ref(null)
const recallLoading = ref(false)
const resourceType = ref('flashcard')
const resource = ref(null)
const generating = ref(false)
const history = ref([])

const current = computed(() => points.value.find((item) => item.id === Number(kpId.value)) || null)
const levelLabel = { direction: '方向提示', concept: '概念提示', step: '步骤提示', full: '完整讲解' }

async function load() {
  if (!store.currentGoalId) return
  try {
    points.value = await api.knowledgePoints(store.currentGoalId)
    if (!kpId.value && points.value.length) kpId.value = points.value[0].id
  } catch (e) {
    notify(e.message, true)
  }
}

async function askStream() {
  if (!store.currentGoalId || !kpId.value) {
    notify('请先选择目标与知识点', true)
    return
  }
  streaming.value = true
  streamResult.value = null
  streamFallback.value = ''
  streamStage.value = '连接中…'
  try {
    await streamSse(`/api/goals/${store.currentGoalId}/socratic/stream`, {
      kp_id: Number(kpId.value),
      message: message.value,
      level: level.value
    }, {
      onStage: (data) => {
        streamStage.value = data.label || data.stage || ''
      },
      onResult: (data) => {
        streamResult.value = data
        streamStage.value = ''
      },
      onFallback: (data) => {
        streamFallback.value = data.text || '规则兜底'
        streamStage.value = ''
      }
    })
  } catch (e) {
    notify(e.message, true)
  } finally {
    streaming.value = false
  }
}

async function ask() {
  if (!store.currentGoalId || !kpId.value) {
    notify('请先选择目标与知识点', true)
    return
  }
  asking.value = true
  reply.value = null
  try {
    reply.value = await api.socratic(store.currentGoalId, {
      kp_id: Number(kpId.value),
      message: message.value,
      mode: mode.value,
      level: level.value
    })
    history.value.unshift({
      level: reply.value.level_label,
      mode: reply.value.mode_label,
      text: reply.value.reply,
      engine: reply.value.engine
    })
  } catch (e) {
    notify(e.message, true)
  } finally {
    asking.value = false
  }
}

async function checkRecall() {
  if (!kpId.value || !recallText.value.trim()) {
    notify('请先选择知识点并输入复述', true)
    return
  }
  recallLoading.value = true
  try {
    recallResult.value = await api.socraticRecall(store.currentGoalId, {
      kp_id: Number(kpId.value),
      recall: recallText.value
    })
  } catch (e) {
    notify(e.message, true)
  } finally {
    recallLoading.value = false
  }
}

async function genResource() {
  if (!kpId.value) {
    notify('请先选择知识点', true)
    return
  }
  generating.value = true
  resource.value = null
  try {
    resource.value = await api.generateResources(store.currentGoalId, {
      kp_id: Number(kpId.value),
      resource_type: resourceType.value,
      count: 3
    })
  } catch (e) {
    notify(e.message, true)
  } finally {
    generating.value = false
  }
}

watch(() => store.currentGoalId, load, { immediate: true })
onMounted(load)
</script>

<template>
  <div v-if="!store.currentGoalId" class="empty">
    还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建目标。
  </div>

  <div v-else class="stack">
    <div class="hero">
      <h1>AI 苏格拉底导师</h1>
      <p>
        导师优先用递进问题启发你，而不是直接给答案。提示分四级：方向 / 概念 / 步骤 / 完整讲解；
        讲完要求你复述，并可生成闪卡、变式题与微课提纲。所有交互都会作为学习事件写入证据链。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ points.length }}</strong>
          <span>可辅导知识点</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ history.length }}</strong>
          <span>本次对话轮次</span>
        </div>
        <div class="hero-meta-item">
          <strong>4</strong>
          <span>提示级别</span>
        </div>
        <div class="hero-meta-item">
          <strong>3</strong>
          <span>教学模式</span>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">选择知识点与教学方式</div>
          <div class="card-sub">当前知识点：{{ current ? current.name : '未选择' }}</div>
        </div>
      </div>
      <div class="grid grid-3" style="gap: 10px; margin-top: 10px">
        <div class="field">
          <label>知识点</label>
          <AppSelect v-model="kpId" :options="kpOptions" placeholder="选择知识点" />
        </div>
        <div class="field">
          <label>模式</label>
          <AppSelect v-model="mode" :options="modeOptions" />
        </div>
        <div class="field">
          <label>提示级别</label>
          <AppSelect v-model="level" :options="levelOptions" />
        </div>
      </div>
      <div class="row" style="gap: 8px; margin-top: 10px">
        <input v-model="message" class="input" placeholder="说说你卡在哪一步，或者你想先理解什么…" style="flex: 1" @keyup.enter="ask" />
        <button class="btn" :disabled="asking" @click="ask">{{ asking ? '思考中...' : '请教导师' }}</button>
        <button class="btn btn-ghost" :disabled="streaming" @click="askStream">
          {{ streaming ? '流式生成中…' : '流式讲解（SSE）' }}
        </button>
      </div>

      <div v-if="streaming || streamStage" class="small muted" style="margin-top: 8px">
        {{ streamStage || '连接中…' }}
      </div>

      <div v-if="streamResult" class="task-reason" style="margin-top: 12px">
        <b>{{ current?.name }} · 第 {{ streamResult.data?.level || 1 }} 级提示</b>
        <div style="margin-top: 6px">{{ streamResult.data?.reply }}</div>
        <div v-if="streamResult.data?.check_question" class="small" style="margin-top: 8px; color: var(--brand-dark)">
          自检：{{ streamResult.data.check_question }}
        </div>
        <div v-if="streamResult.data?.next_level_hint" class="small muted" style="margin-top: 4px">
          {{ streamResult.data.next_level_hint }}
        </div>
        <div class="row" style="gap: 8px; margin-top: 8px; flex-wrap: wrap">
          <span class="tag tag-review">AI 生成 · DeepSeek</span>
          <span class="tag tag-study">{{ streamResult.prompt?.id }} v{{ streamResult.prompt?.version }}</span>
          <span class="tag tag-pending">置信度 {{ Math.round((streamResult.confidence || 0) * 100) }}%</span>
        </div>
      </div>

      <div v-else-if="streamFallback" class="task-reason" style="margin-top: 12px">
        <b>备用讲解</b>
        <div style="margin-top: 6px">{{ streamFallback }}</div>
      </div>

      <div v-if="reply" class="task-reason" style="margin-top: 12px">
        <b>{{ reply.level_label }} · {{ reply.mode_label }}</b>
        <div style="margin-top: 6px">{{ reply.reply }}</div>
        <div v-if="reply.next_question" class="small" style="margin-top: 8px; color: var(--brand-dark)">
          下一步：{{ reply.next_question }}
        </div>
        <div class="small muted" style="margin-top: 4px">
          引擎：{{ reply.engine === 'llm' ? '智能讲解' : '备用讲解' }}
        </div>
      </div>
    </div>

    <div class="split">
      <div class="card">
        <div class="card-title">复述检查</div>
        <div class="card-sub" style="margin-top: 4px">用自己的话复述，系统按关键词覆盖度判断是否真正理解</div>
        <textarea v-model="recallText" class="input" rows="4" placeholder="用 2-3 句话说明定义、条件与用法…" style="margin-top: 10px"></textarea>
        <button class="btn btn-block" :disabled="recallLoading" style="margin-top: 10px" @click="checkRecall">
          {{ recallLoading ? '检查中...' : '提交复述' }}
        </button>
        <div v-if="recallResult" class="stack" style="margin-top: 10px">
          <div class="row-between">
            <b>覆盖度</b>
            <span class="tag" :class="recallResult.passed ? 'tag-review' : 'tag-time'">{{ recallResult.coverage }}%</span>
          </div>
          <div class="bar"><i :style="{ width: recallResult.coverage + '%' }"></i></div>
          <div class="small">{{ recallResult.feedback }}</div>
          <div v-if="recallResult.matched.length" class="small muted">命中：{{ recallResult.matched.join('、') }}</div>
          <div v-if="recallResult.missing.length" class="small muted">缺失：{{ recallResult.missing.join('、') }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">学习资源工厂</div>
        <div class="card-sub" style="margin-top: 4px">生成闪卡、变式题或微课提纲，内容标记待审核</div>
        <div class="row" style="gap: 8px; margin-top: 10px">
          <AppSelect v-model="resourceType" :options="resourceOptions" style="width: 140px" />
          <button class="btn" :disabled="generating" @click="genResource">{{ generating ? '生成中...' : '生成资源' }}</button>
        </div>
        <div v-if="resource" class="stack" style="margin-top: 10px">
          <div class="small muted">
            {{ resource.resource_label }} · {{ resource.engine === 'llm' ? '智能讲解' : '备用讲解' }} · {{ resource.review_status }}
          </div>
          <div v-for="(item, index) in resource.items" :key="index" class="gap-row">
            <div class="small">{{ item.front || item.question || item.title }}</div>
            <span class="tag tag-study">#{{ index + 1 }}</span>
          </div>
          <div class="small muted">{{ resource.note }}</div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">本次对话记录</div>
      <div v-if="!history.length" class="empty" style="margin-top: 10px">还没有对话。选择知识点后向导师提问。</div>
      <div v-else class="stack" style="margin-top: 10px">
        <div v-for="(item, index) in history.slice(0, 8)" :key="index" class="task-reason" style="margin-top: 0">
          <b>{{ item.level }} · {{ item.mode }}</b>
          <div class="small" style="margin-top: 4px">{{ item.text }}</div>
        </div>
      </div>
    </div>

  </div>
</template>