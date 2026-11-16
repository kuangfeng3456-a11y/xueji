<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'
import DetailModal from '../components/DetailModal.vue'

const loading = ref(true)
const data = ref(null)
const loadInfo = ref(null)
const adjusting = ref(false)
const detail = ref(null)

function openTask(task) {
  detail.value = {
    title: task.title,
    subtitle: `关键任务 · ${typeText(task.type)}`,
    rows: [
      { label: '预计时长', value: `${task.duration_min} 分钟` },
      { label: '优先级', value: String(task.priority) },
      { label: '任务类型', value: typeText(task.type) },
      { label: '建议', value: '优先在精力最高的时段完成，进入专注模式可避免中断。' }
    ],
    linkTo: '/focus',
    linkText: '进入专注完成'
  }
}

const practiceTask = ref(null)
const practiceQuiz = ref(null)
const practiceAnswers = ref([])
const practiceResult = ref(null)
const practiceLoading = ref(false)

async function openPractice(task) {
  if (!task.kp_id) {
    notify('该任务未关联知识点，暂时无法生成练习。请到计划页补充知识点后再练习。', true)
    return
  }
  practiceTask.value = task
  practiceQuiz.value = null
  practiceAnswers.value = []
  practiceResult.value = null
  practiceLoading.value = true
  try {
    const quiz = await api.generateQuiz(store.currentGoalId, { kp_id: task.kp_id, count: 3 })
    practiceQuiz.value = quiz
    practiceAnswers.value = new Array(quiz.questions.length).fill(-1)
  } catch (e) {
    notify(e.message, true)
    practiceTask.value = null
  } finally {
    practiceLoading.value = false
  }
}

function choosePractice(index, option) {
  practiceAnswers.value[index] = option
}

async function submitPractice() {
  if (!practiceQuiz.value) return
  if (practiceAnswers.value.some((item) => item < 0)) {
    notify('还有题目没有作答', true)
    return
  }
  practiceLoading.value = true
  try {
    const result = await api.submitQuiz(store.currentGoalId, {
      quiz_id: practiceQuiz.value.quiz_id,
      answers: practiceAnswers.value
    })
    practiceResult.value = result
    notify(`本次练习得分 ${result.score} 分，错题已写入错题本`)
  } catch (e) {
    notify(e.message, true)
  } finally {
    practiceLoading.value = false
  }
}

async function finishPractice() {
  if (!practiceTask.value) return
  try {
    await api.updateTask(store.currentGoalId, practiceTask.value.id, 'done')
    notify('已根据本次练习完成该任务')
    closePractice()
    await load()
  } catch (e) {
    notify(e.message, true)
  }
}

function closePractice() {
  practiceTask.value = null
  practiceQuiz.value = null
  practiceAnswers.value = []
  practiceResult.value = null
}

function openRisk(risk) {
  detail.value = {
    title: risk.title,
    subtitle: '风险提示',
    rows: [
      { label: '触发原因', value: risk.reason },
      { label: '建议动作', value: risk.suggestion },
      { label: '风险等级', value: riskText(risk.level) }
    ],
    linkTo: '/risk-center',
    linkText: '进入风险救援中心'
  }
}

const goal = computed(() => store.goals.find((item) => item.id === store.currentGoalId) || null)
const readiness = computed(() => data.value?.readiness || null)
const levelLabel = { excellent: '状态稳', good: '基本可控', risk: '风险偏高', critical: '需要救援' }
const levelColor = { excellent: '#0d9488', good: '#2563eb', risk: '#d97706', critical: '#dc2626' }
const loadLabel = { low: '负荷偏低', optimal: '负荷适中', high: '负荷偏高', overload: '负荷过高' }
const loadColor = { low: '#2563eb', optimal: '#0d9488', high: '#d97706', overload: '#dc2626' }
const riskLevelClass = { high: 'tag-skipped', medium: 'tag-time', low: 'tag-study' }
const riskLevelLabel = { high: '高风险', medium: '中风险', low: '低风险' }
const typeLabel = { study: '学习', practice: '练习', review: '复习', remedial: '补救', mock: '模考' }
const typeText = (value) => typeLabel[value] || value
const riskText = (value) => riskLevelLabel[value] || value

async function load() {
  if (!store.currentGoalId) return
  if (!store.currentGoalId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const [cockpitData, loadData] = await Promise.all([
      api.cockpit(store.currentGoalId),
      api.cognitiveLoad(store.currentGoalId)
    ])
    data.value = cockpitData
    loadInfo.value = loadData
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function adjustLoad() {
  adjusting.value = true
  try {
    const result = await api.applyCognitiveLoad(store.currentGoalId, 'auto')
    notify(result.message)
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    adjusting.value = false
  }
}

watch(() => store.currentGoalId, load, { immediate: true })
onMounted(() => {})
</script>

<template>
  <div v-if="!store.currentGoalId" class="empty">
    还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建目标。
  </div>

  <div v-else-if="loading" class="empty">正在汇总学习状态...</div>

  <div v-else-if="data" class="stack">
    <div class="hero">
      <h1>学习驾驶舱 · {{ goal?.exam_name }}还剩 {{ goal?.days_left }} 天</h1>
      <p>
        一屏看清三件事：现在准备到什么程度、哪些风险正在发生、今天最关键的任务是什么。
        风险不会只提醒，确认后系统会直接调整计划并给出前后对比。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ readiness.score }}%</strong>
          <span>整体准备度</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ readiness.level === 'excellent' ? '稳' : readiness.level === 'good' ? '可控' : '有风险' }}</strong>
          <span>{{ levelLabel[readiness.level] }}</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ data.gap_count + data.verified_gap_count }}</strong>
          <span>知识漏洞</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ data.risks.length }}</strong>
          <span>当前风险</span>
        </div>
      </div>
    </div>

    <div class="cockpit-grid">
      <div class="card readiness-card">
        <div class="card-head">
          <div>
            <div class="card-title">整体准备度</div>
            <div class="card-sub">按高权重知识点覆盖、时间负荷与风险扣分计算</div>
          </div>
          <span class="tag" :style="{ background: levelColor[readiness.level] + '18', color: levelColor[readiness.level] }">
            {{ levelLabel[readiness.level] }}
          </span>
        </div>
        <div class="readiness-wrap">
          <div
            class="readiness-ring"
            :style="{ background: `conic-gradient(${levelColor[readiness.level]} ${readiness.score * 3.6}deg, #eef2f7 0deg)` }"
          >
            <div class="readiness-inner">
              <b>{{ readiness.score }}</b>
              <span>准备度</span>
            </div>
          </div>
          <div class="stack" style="gap: 8px">
            <div class="kv"><span>知识覆盖</span><strong>{{ Math.round(readiness.coverage * 100) }}%</strong></div>
            <div class="kv"><span>时间负荷</span><strong>{{ Math.round(readiness.load_ratio * 100) }}%</strong></div>
            <div class="kv"><span>已验证漏洞</span><strong>{{ readiness.gap_count }} 个</strong></div>
            <div v-for="(factor, index) in readiness.factors" :key="index" class="small muted">· {{ factor }}</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">今日关键任务</div>
            <div class="card-sub">按优先级取前 3 个，完成后准备度会同步刷新</div>
          </div>
          <router-link class="btn btn-ghost btn-sm" to="/plan">全部任务</router-link>
        </div>
        <div v-if="!data.critical_tasks.length" class="empty">今天没有待完成任务，可能已经全部完成。</div>
        <div v-else class="stack">
          <div v-for="task in data.critical_tasks" :key="task.id" class="focus-task click-line" style="padding: 6px; border-radius: 10px" role="button" tabindex="0" @click="openPractice(task)" @keydown.enter.prevent="openPractice(task)" @keydown.space.prevent="openPractice(task)">
            <span class="tag" :class="`tag-${task.type}`">{{ typeText(task.type) }}</span>
            <span class="focus-task-main">
              <b>{{ task.title }}</b>
              <small>{{ task.duration_min }} 分钟 · 优先级 {{ task.priority }}</small>
            </span>
            <router-link class="btn btn-ghost btn-sm" to="/focus">专注完成</router-link>
          </div>
        </div>
      </div>
    </div>

    <div v-if="loadInfo" class="card">
      <div class="card-head">
        <div>
          <div class="card-title">认知负荷调节器</div>
          <div class="card-sub">根据疲劳、任务量与错题率动态调整难度与任务颗粒度</div>
        </div>
        <span class="tag" :style="{ background: loadColor[loadInfo.level] + '18', color: loadColor[loadInfo.level] }">
          {{ loadLabel[loadInfo.level] }}
        </span>
      </div>
      <div class="readiness-wrap">
        <div
          class="readiness-ring"
          :style="{
            width: '100px',
            height: '100px',
            flex: '0 0 100px',
            background: `conic-gradient(${loadColor[loadInfo.level]} ${loadInfo.score * 3.6}deg, #eef2f7 0deg)`
          }"
        >
          <div class="readiness-inner" style="width: 76px; height: 76px">
            <b>{{ loadInfo.score }}</b>
            <span>负荷</span>
          </div>
        </div>
        <div class="stack" style="gap: 6px; flex: 1">
          <div class="small">{{ loadInfo.advice }}</div>
          <div v-for="(factor, index) in loadInfo.factors" :key="index" class="small muted">
            · {{ factor }}
          </div>
          <div class="row" style="margin-top: 8px">
            <button class="btn btn-sm" :disabled="adjusting" @click="adjustLoad">
              {{ adjusting ? '调节中...' : '按负荷自动调节' }}
            </button>
            <span class="small muted">
              建议 {{ loadInfo.recommended_tasks }} 个任务 / {{ loadInfo.recommended_minutes }} 分钟
            </span>
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">风险提示</div>
          <div class="card-sub">识别原因 → 给出动作 → 确认后自动调整并对比前后</div>
        </div>
        <router-link class="btn btn-ghost btn-sm" to="/risk-center">进入风险救援中心</router-link>
      </div>
      <div v-if="!data.risks.length" class="empty">当前没有明显风险，保持节奏即可。</div>
      <div v-else class="grid grid-3">
        <div v-for="risk in data.risks.slice(0, 3)" :key="risk.code" class="risk-mini click-card" role="button" tabindex="0" @click="openRisk(risk)" @keydown.enter.prevent="openRisk(risk)" @keydown.space.prevent="openRisk(risk)">
          <div class="row-between">
            <b>{{ risk.title }}</b>
            <span class="tag" :class="riskLevelClass[risk.level]">{{ riskText(risk.level) }}</span>
          </div>
          <div class="small muted" style="margin-top: 6px; line-height: 1.7">{{ risk.reason }}</div>
          <div class="small" style="margin-top: 6px; color: var(--brand-dark)">{{ risk.suggestion }}</div>
        </div>
      </div>
    </div>

    <div class="grid grid-4">
      <router-link class="quick-card" to="/knowledge-map">
        <div class="quick-icon">⌘</div>
        <b>知识漏洞地图</b>
        <small>先修依赖 + 验证题确认</small>
      </router-link>
      <router-link class="quick-card" to="/twin">
        <div class="quick-icon">◈</div>
        <b>数字孪生推演</b>
        <small>7 / 14 / 30 天的变化区间</small>
      </router-link>
      <router-link class="quick-card" to="/panel">
        <div class="quick-icon">⚖</div>
        <b>评审团复核</b>
        <small>多角色独立审查当前方案</small>
      </router-link>
      <router-link class="quick-card" to="/insights">
        <div class="quick-icon">▦</div>
        <b>学情洞察</b>
        <small>热力图、能力雷达与疲劳信号</small>
      </router-link>
    </div>

    <div v-if="practiceTask" class="modal-mask" @click.self="closePractice">
      <div class="modal knowledge-modal">
        <div class="card-head">
          <div>
            <div class="card-title">练习：{{ practiceTask.title }}</div>
            <div class="card-sub">
              {{ typeText(practiceTask.type) }} · {{ practiceTask.duration_min }} 分钟 · 真实作答后自动记录掌握度
            </div>
          </div>
          <button class="btn btn-ghost btn-sm" @click="closePractice">关闭</button>
        </div>

        <div v-if="practiceLoading" class="empty">正在生成真实题目或判分...</div>

        <div v-else-if="practiceResult" class="stack">
          <div class="row-between">
            <b>练习结果</b>
            <span class="tag" :class="practiceResult.score >= 60 ? 'tag-review' : 'tag-skipped'">
              {{ practiceResult.score }} 分
            </span>
          </div>
          <div class="small muted">
            答对 {{ practiceResult.correct }} / {{ practiceResult.total }} · 错题 {{ practiceResult.wrong.length }} 道已写入错题本
          </div>
          <div v-if="practiceResult.wrong.length" class="stack">
            <div v-for="item in practiceResult.wrong" :key="item.index" class="quiz-wrong">
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
          <div class="row" style="margin-top: 10px">
            <button class="btn" @click="finishPractice">完成并标记任务</button>
            <button class="btn btn-ghost" @click="closePractice">稍后再做</button>
          </div>
        </div>

        <div v-else-if="practiceQuiz" class="stack">
          <div v-for="question in practiceQuiz.questions" :key="question.index" class="quiz-question">
            <div class="quiz-stem">
              <span class="quiz-index">{{ question.index + 1 }}</span>
              <span>{{ question.question }}</span>
            </div>
            <div class="quiz-options">
              <button
                v-for="(option, optionIndex) in question.options"
                :key="optionIndex"
                class="quiz-option"
                :class="{ active: practiceAnswers[question.index] === optionIndex }"
                @click="choosePractice(question.index, optionIndex)"
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
          <button class="btn btn-block" :disabled="practiceLoading" @click="submitPractice">
            {{ practiceLoading ? '判分中...' : '提交并查看真实得分' }}
          </button>
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
