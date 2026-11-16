<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  task: { type: Object, required: true },
  showDay: { type: Boolean, default: false },
  showTier: { type: Boolean, default: false }
})
const emit = defineEmits(['change', 'feedback', 'detail', 'tier'])
const open = ref(true)

const typeLabel = { study: '学习', review: '复习', practice: '练习', remedial: '补救' }
const statusLabel = { pending: '待完成', done: '已完成', skipped: '已跳过' }
const feedbacks = [
  { key: 'easy', label: '简单' },
  { key: 'ok', label: '刚好' },
  { key: 'hard', label: '偏难' }
]

const typeClass = computed(() => `tag-${props.task.type}`)
const statusClass = computed(() => `tag-${props.task.status}`)

function setStatus(status) {
  emit('change', { task: props.task, status })
}

function formatDay(day) {
  if (!day) return ''
  const [y, m, d] = day.split('-').map(Number)
  const target = new Date(y, m - 1, d)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const diff = Math.round((target - today) / 86400000)
  const week = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][target.getDay()]
  if (diff === 0) return '今天'
  if (diff === 1) return '明天'
  if (diff === -1) return '昨天'
  return `${m} 月 ${d} 日 ${week}`
}

defineExpose({ formatDay })
</script>

<template>
  <div class="task" :class="{ done: task.status === 'done' }">
    <div class="task-main">
      <div class="task-title click-line" @click="emit('detail', task)">{{ task.title }}</div>
      <div class="task-meta">
        <span class="tag" :class="typeClass">{{ typeLabel[task.type] || task.type }}</span>
        <span class="small muted">{{ task.duration_min }} 分钟</span>
        <span class="tag" :class="statusClass">{{ statusLabel[task.status] || task.status }}</span>
        <span v-if="showDay" class="small muted">{{ formatDay(task.day) }}</span>
        <span v-if="task.kp_name" class="small muted">· {{ task.kp_name }}</span>
      </div>
      <div v-if="open && task.reason" class="task-reason">{{ task.reason }}</div>
    </div>
    <div class="task-actions">
      <button class="btn btn-ghost btn-sm" @click="open = !open">{{ open ? '收起理由' : '为什么' }}</button>
      <template v-if="task.status === 'pending'">
        <button
          v-if="showTier && task.tiers && task.tiers.lite < task.duration_min"
          class="btn btn-ghost btn-sm"
          @click="emit('tier', { task, minutes: task.tiers.lite })"
        >
          精简 {{ task.tiers.lite }} 分钟
        </button>
        <button
          v-if="showTier && task.tiers && task.tiers.minimal < task.duration_min"
          class="btn btn-ghost btn-sm"
          @click="emit('tier', { task, minutes: task.tiers.minimal })"
        >
          最小 {{ task.tiers.minimal }} 分钟
        </button>
        <button class="btn btn-teal btn-sm" @click="setStatus('done')">完成</button>
        <button class="btn btn-ghost btn-sm" @click="setStatus('skipped')">跳过</button>
      </template>
      <template v-else-if="task.status === 'done'">
        <span class="small muted">难度</span>
        <button
          v-for="item in feedbacks"
          :key="item.key"
          class="chip"
          :class="{ active: task.feedback === item.key }"
          @click="emit('feedback', { task, feedback: item.key })"
        >
          {{ item.label }}
        </button>
        <button class="btn btn-ghost btn-sm" @click="setStatus('pending')">撤销</button>
      </template>
      <template v-else>
        <button class="btn btn-ghost btn-sm" @click="setStatus('pending')">恢复</button>
      </template>
    </div>
  </div>
</template>