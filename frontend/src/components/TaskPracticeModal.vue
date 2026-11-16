<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { notify } from '../store'

const typeLabel = { study: '学习', practice: '练习', review: '复习', remedial: '补救', mock: '模考' }
const typeText = (value) => typeLabel[value] || value

const props = defineProps({
  task: { type: Object, required: true },
  goalId: { type: Number, required: true }
})
const emit = defineEmits(['close', 'done'])

const loading = ref(false)
const quiz = ref(null)
const answers = ref([])
const result = ref(null)
const submitting = ref(false)
const finishing = ref(false)

async function generate() {
  if (!props.task.kp_id) {
    notify('该任务未关联知识点，无法生成练习。请到计划页为任务补充知识点。', true)
    return
  }
  loading.value = true
  result.value = null
  quiz.value = null
  try {
    const data = await api.generateQuiz(props.goalId, { kp_id: props.task.kp_id, count: 3 })
    quiz.value = data
    answers.value = new Array(data.questions.length).fill(-1)
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

function choose(index, option) {
  answers.value[index] = option
}

async function submit() {
  if (!quiz.value) return
  if (answers.value.some((item) => item < 0)) {
    notify('还有题目没有作答', true)
    return
  }
  submitting.value = true
  try {
    result.value = await api.submitQuiz(props.goalId, {
      quiz_id: quiz.value.quiz_id,
      answers: answers.value
    })
    notify(`本次练习得分 ${result.value.score} 分，错题已写入错题本`)
  } catch (e) {
    notify(e.message, true)
  } finally {
    submitting.value = false
  }
}

async function finish() {
  finishing.value = true
  try {
    await api.updateTask(props.goalId, props.task.id, 'done')
    notify('已根据本次练习完成该任务')
    emit('done')
    emit('close')
  } catch (e) {
    notify(e.message, true)
  } finally {
    finishing.value = false
  }
}

onMounted(generate)
</script>

<template>
  <div class="modal-mask" @click.self="emit('close')">
    <div class="modal knowledge-modal">
      <div class="card-head">
        <div>
          <div class="card-title">练习：{{ task.title }}</div>
          <div class="card-sub">
            {{ typeText(task.type) }} · {{ task.duration_min }} 分钟 · 真实作答后自动记录掌握度
          </div>
        </div>
        <button class="btn btn-ghost btn-sm" @click="emit('close')">关闭</button>
      </div>

      <div v-if="!task.kp_id" class="empty">
        该任务未关联知识点，无法生成练习。请到「学习计划」为任务补充知识点后再做。
      </div>

      <div v-else-if="loading" class="empty">正在生成真实题目...</div>

      <div v-else-if="result" class="stack">
        <div class="row-between">
          <b>练习结果</b>
          <span class="tag" :class="result.score >= 60 ? 'tag-review' : 'tag-skipped'">
            {{ result.score }} 分
          </span>
        </div>
        <div class="small muted">
          答对 {{ result.correct }} / {{ result.total }} · 错题 {{ result.wrong.length }} 道已写入错题本
        </div>
        <div v-if="result.wrong.length" class="stack">
          <div v-for="item in result.wrong" :key="item.index" class="quiz-wrong">
            <div class="row-between">
              <b>{{ item.question }}</b>
              <span class="tag" :class="`tag-${item.category}`">{{ item.category_label }}</span>
            </div>
            <div class="small" style="margin-top: 6px">
              你的答案：{{ item.chosen }}　正确答案：{{ item.correct }}
            </div>
            <div class="task-reason" style="margin-top: 8px">{{ item.explanation || '暂无解析' }}</div>
          </div>
        </div>
        <div v-else class="empty">全部答对，这个知识点掌握得很好。</div>
        <div class="row" style="margin-top: 10px">
          <button class="btn" :disabled="finishing" @click="finish">
            {{ finishing ? '提交中...' : '完成并标记任务' }}
          </button>
          <button class="btn btn-ghost" @click="emit('close')">稍后再做</button>
        </div>
      </div>

      <div v-else-if="quiz" class="stack">
      <div v-if="quiz.engine === 'rule'" class="small muted" style="border-left: 2px solid var(--line); padding: 8px 10px; background: var(--paper)">
        这是根据知识点生成的练习题，用于核对掌握情况。
      </div>
        <div v-for="question in quiz.questions" :key="question.index" class="quiz-question">
          <div class="quiz-stem">
            <span class="quiz-index">{{ question.index + 1 }}</span>
            <span>{{ question.question }}</span>
          </div>
          <div class="quiz-options">
            <button
              v-for="(option, optionIndex) in question.options"
              :key="optionIndex"
              class="quiz-option"
              :class="{ active: answers[question.index] === optionIndex }"
              @click="choose(question.index, optionIndex)"
            >
              <span class="quiz-option-key">{{ String.fromCharCode(65 + optionIndex) }}</span>
              <span>{{ option }}</span>
            </button>
          </div>
          <div class="small muted" style="margin-top: 6px">
            知识点：{{ question.kp_name || '未关联' }}
            <span v-if="question.source"> · 来源：{{ question.source }}</span>
          </div>
        </div>
        <button class="btn btn-block" :disabled="submitting" @click="submit">
          {{ submitting ? '判分中...' : '提交并查看真实得分' }}
        </button>
      </div>

      <div v-else class="empty">暂无题目，请稍后重试。</div>
    </div>
  </div>
</template>
