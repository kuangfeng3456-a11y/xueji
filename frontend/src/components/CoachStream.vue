<script setup>
import { computed, ref } from 'vue'
import { streamSse } from '../sse'

const props = defineProps({
  goalId: { type: [Number, String], default: null }
})

const running = ref(false)
const stages = ref([])
const preview = ref('')
const result = ref(null)
const fallback = ref('')
const error = ref('')
const meta = ref(null)

const stageText = computed(() => stages.value.map((item) => item.label).join(' → '))
const canRun = computed(() => Boolean(props.goalId) && !running.value)

async function run() {
  if (!props.goalId) {
    error.value = '请先创建或选择一个考试目标'
    return
  }
  running.value = true
  stages.value = []
  preview.value = ''
  result.value = null
  fallback.value = ''
  error.value = ''
  meta.value = null

  try {
    await streamSse(`/goals/${props.goalId}/coach/stream`, null, {
      onStage: (data) => stages.value.push(data),
      onDelta: (data) => {
        preview.value = (preview.value + (data.text || '')).slice(-400)
      },
      onResult: (data) => {
        result.value = data
        meta.value = data.prompt
      },
      onFallback: (data) => {
        fallback.value = data.reason || '模型不可用'
      },
      onError: (data) => {
        error.value = data.message || '流式生成失败，请稍后重试'
      }
    })
  } catch (e) {
    error.value = e.message
  } finally {
    running.value = false
  }
}
</script>

<template>
  <div class="card">
    <div class="card-head">
      <div>
        <div class="card-title">教练一句话 · 流式生成</div>
        <div class="card-sub">SSE 逐段返回：规则先算，模型只负责表达，校验通过后才展示</div>
      </div>
      <button class="btn btn-sm" :disabled="!canRun" @click="run">
        {{ running ? '生成中…' : '生成今日提醒' }}
      </button>
    </div>

    <div v-if="error" class="small" style="color: #b91c1c; margin-top: 10px">{{ error }}</div>

    <div v-if="running || stages.length" class="small muted" style="margin-top: 10px">
      {{ stageText || '连接中…' }}
      <span v-if="running" class="tag tag-study" style="margin-left: 8px">流式接收中</span>
    </div>

    <div v-if="result" class="stack" style="margin-top: 12px; gap: 8px">
      <div class="coach-line">{{ result.data?.message || result.data?.headline }}</div>
      <div v-if="result.data?.headline && result.data?.message" class="small muted">
        {{ result.data.headline }}
      </div>
      <div class="row" style="gap: 8px; flex-wrap: wrap">
        <span class="tag tag-review">AI 生成 · DeepSeek</span>
        <span class="tag tag-study">{{ meta?.id }} v{{ meta?.version }}</span>
        <span class="tag tag-pending">置信度 {{ Math.round((result.confidence || 0) * 100) }}%</span>
        <span v-for="warn in result.warnings || []" :key="warn" class="tag tag-time">{{ warn }}</span>
      </div>
    </div>

    <div v-else-if="fallback" class="stack" style="margin-top: 12px; gap: 6px">
      <div class="coach-line">{{ fallback }}</div>
      <div class="small muted">智能教练暂不可用，已为你提供备用讲解。</div>
    </div>

    <div v-if="running && preview" class="small muted" style="margin-top: 8px; max-height: 60px; overflow: hidden">
      已接收 {{ preview.length }} 字（校验通过前不展示正文）
    </div>
  </div>
</template>

<style scoped>
.coach-line {
  font-size: 15px;
  line-height: 1.7;
  padding: 12px 14px;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(47, 91, 216, 0.06), rgba(15, 157, 143, 0.06));
  border: 1px solid var(--line);
}
</style>
