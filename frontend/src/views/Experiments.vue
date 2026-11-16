<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'
import AppSelect from '../components/AppSelect.vue'
import DetailModal from '../components/DetailModal.vue'

const loading = ref(true)
const data = ref({ items: [], ranking: [], strategies: [] })
const detail = ref(null)

const creating = ref(false)
const finishing = ref('')
const activeId = ref(null)
const scores = reactive({ immediate: 80, delayed: 70, note: '' })

const practiceItem = ref(null)
const practiceQuiz = ref(null)
const practiceAnswers = ref([])
const practiceResult = ref(null)
const practiceGenerating = ref(false)
const practiceSubmitting = ref(false)

const running = computed(() => data.value.items.filter((item) => item.status === 'running'))
const finished = computed(() => data.value.items.filter((item) => item.status === 'finished'))

// 到期未收尾：后端会带 expired / overdue_days，拿不到时前端按结束日自己算（避免依赖重启）。
function isExpired(item) {
  if (typeof item?.expired === 'boolean') return item.expired
  if (item?.status !== 'running' || !item?.end_date) return false
  return overdueDays(item) > 0
}
function overdueDays(item) {
  if (typeof item?.overdue_days === 'number' && item.overdue_days > 0) return item.overdue_days
  if (!item?.end_date) return 0
  const end = new Date(item.end_date + 'T00:00:00')
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const diff = Math.round((today - end) / 86400000)
  return diff > 0 ? diff : 0
}
const best = computed(() => data.value.ranking[0] || null)
const strategyLabel = computed(() => {
  const map = {}
  for (const item of data.value.strategies || []) map[item.key] = item.label
  return map
})
const practiceAnswered = computed(() => practiceAnswers.value.filter((item) => item !== -1 && item !== null).length)
// 出题引擎如实标注：命中本地题库不等于「规则兜底」，两者不能混成一个标签。
const ENGINE_LABEL = {
  llm: 'DeepSeek 实时出题',
  bank: '内置题库兜底出题',
  'bank+llm': '模型出题 + 内置题库补题',
  external: '外部题库 API',
  'external+llm': '外部题库 API + 模型补题',
  'bank+external': '内置题库 + 外部题库 API',
  rule: '系统出题'
}
const practiceEngine = computed(() => {
  const engine = practiceQuiz.value?.engine || practiceResult.value?.engine
  if (!engine) return '出题中…'
  return ENGINE_LABEL[engine] || engine
})

const form = reactive({ strategy: 'practice', days: 3 })
const strategyOptions = computed(() => (data.value.strategies || []).map((item) => ({ value: item.key, label: item.label })))
const report = ref(null)
const reportLoading = ref(false)

async function openReport(item) {
  reportLoading.value = true
  try {
    const data = await api.experimentReport(item.id)
    report.value = { title: strategyLabel.value[item.strategy] || item.strategy, ...data }
  } catch (e) {
    notify(e.message, true)
    report.value = null
  } finally {
    reportLoading.value = false
  }
}

function openFinished(item) {
  detail.value = {
    title: strategyLabel.value[item.strategy] || item.strategy,
    subtitle: '已完成的策略实验',
    rows: [
      { label: '收益', value: `${item.gain > 0 ? '+' : ''}${Math.round(item.gain * 100)} pp` },
      { label: '即时得分', value: `${item.immediate_score} 分` },
      { label: '延迟得分', value: `${item.delayed_score} 分` },
      { label: '间隔天数', value: `${item.days} 天` },
      { label: '备注', value: item.note || '无' }
    ]
  }
}

function openRanking(item) {
  detail.value = {
    title: item.label,
    subtitle: '策略收益排行',
    rows: [
      { label: '平均收益', value: `${Math.round(item.avg_gain * 100)} pp` },
      { label: '实验次数', value: `${item.experiments} 次` },
      { label: '说明', value: '排行只统计你真实完成过的实验。' }
    ],
    linkTo: '/insights',
    linkText: '查看看板'
  }
}

async function load() {
  if (!store.currentGoalId) return
  if (!store.currentGoalId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    data.value = await api.experiments(store.currentGoalId)
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function create() {
  creating.value = true
  try {
    await api.createExperiment(store.currentGoalId, {
      strategy: form.strategy,
      days: Number(form.days)
    })
    notify('实验已开始，先做一组实验题，再按所选策略学习')
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    creating.value = false
  }
}

async function openPractice(item) {
  practiceItem.value = item
  practiceQuiz.value = null
  practiceAnswers.value = []
  practiceResult.value = null
  await generatePractice()
}

async function generatePractice() {
  if (!store.currentGoalId) {
    notify('请先创建考试目标', true)
    return
  }
  practiceGenerating.value = true
  practiceResult.value = null
  try {
    const result = await api.generateQuiz(store.currentGoalId, { kp_id: null, count: 3 })
    practiceQuiz.value = result
    practiceAnswers.value = new Array(result.questions.length).fill(-1)
  } catch (e) {
    notify(e.message, true)
  } finally {
    practiceGenerating.value = false
  }
}

function choosePractice(index, optionIndex) {
  const next = [...practiceAnswers.value]
  next[index] = optionIndex
  practiceAnswers.value = next
}

async function submitPractice() {
  if (!practiceQuiz.value) return
  if (practiceAnswers.value.some((item) => item < 0)) {
    notify('还有题目没有作答', true)
    return
  }
  practiceSubmitting.value = true
  try {
    const result = await api.submitQuiz(store.currentGoalId, {
      quiz_id: practiceQuiz.value.quiz_id,
      answers: practiceAnswers.value
    })
    practiceResult.value = result
    scores.immediate = result.score
    notify(`实验题得分 ${result.score} 分，已作为本次实验的即时得分`)
  } catch (e) {
    notify(e.message, true)
  } finally {
    practiceSubmitting.value = false
  }
}

function closePractice() {
  practiceItem.value = null
  practiceQuiz.value = null
  practiceAnswers.value = []
  practiceResult.value = null
}

function openFinish(item) {
  activeId.value = item.id
  scores.immediate = practiceResult.value?.score ?? 80
  scores.delayed = 70
  scores.note = ''
}

async function finish(item) {
  finishing.value = String(item.id)
  try {
    await api.finishExperiment(item.id, {
      immediate_score: Number(scores.immediate),
      delayed_score: Number(scores.delayed),
      note: scores.note
    })
    notify('实验已结束，收益已计入策略排行')
    activeId.value = null
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    finishing.value = ''
  }
}

watch(() => store.currentGoalId, load, { immediate: true })
onMounted(() => {})
</script>

<template>
  <div v-if="!store.currentGoalId" class="empty">
    还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建目标。
  </div>

  <div v-else-if="loading" class="empty">正在读取实验记录...</div>

  <div v-else class="stack">
    <div class="hero">
      <h1>策略实验室</h1>
      <p>
        不同的人适合不同的学习方式。用 3 天小实验比较精读、刷题、闪卡与 AI 讲解的真实收益。
        点开进行中的实验即可现场做一组真实题目，得分直接作为实验的即时测试分数，而不是手填。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ running.length }}</strong>
          <span>进行中实验</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ finished.length }}</strong>
          <span>已完成实验</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ best ? best.label : '暂无' }}</strong>
          <span>当前最佳策略</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ best ? Math.round(best.avg_gain * 100) + 'pp' : '—' }}</strong>
          <span>平均掌握增益</span>
        </div>
      </div>
    </div>

    <div class="split">
      <div class="stack">
        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">进行中的实验</div>
              <div class="card-sub">点开实验现场做题，真实得分写入即时测试</div>
            </div>
          </div>
          <div v-if="!running.length" class="empty">还没有进行中的实验，在右侧创建一个。</div>
          <div v-else class="stack">
            <div v-for="item in running" :key="item.id" class="experiment-card">
              <div class="row-between">
                <div>
                  <b>{{ strategyLabel[item.strategy] || item.strategy }}</b>
                  <span v-if="isExpired(item)" class="tag tag-skipped" style="margin-left: 6px">已到期</span>
                  <div class="small muted">
                    {{ item.start_date }} ~ {{ item.end_date }} · 实验前掌握度
                    {{ Math.round(item.pre_mastery * 100) }}%
                  </div>
                  <div v-if="isExpired(item)" class="small" style="margin-top: 4px; color: var(--amber)">
                    已超期 {{ overdueDays(item) }} 天，补一次延迟测试后「结束并记录」，否则不会有增益数据
                  </div>
                </div>
                <div class="row" style="gap: 6px">
                  <button class="btn btn-sm" @click.stop="openPractice(item)">做实验题</button>
                  <button class="btn btn-ghost btn-sm" @click.stop="openFinish(item)">结束并记录</button>
                </div>
              </div>

              <div v-if="activeId === item.id" class="stack" style="margin-top: 12px">
                <div class="grid grid-2" style="gap: 10px">
                  <div class="field" style="margin: 0">
                    <label>即时测试分数（做题后自动带入）</label>
                    <input v-model.number="scores.immediate" class="input" type="number" min="0" max="100" />
                  </div>
                  <div class="field" style="margin: 0">
                    <label>延迟测试分数</label>
                    <input v-model.number="scores.delayed" class="input" type="number" min="0" max="100" />
                  </div>
                </div>
                <div class="field" style="margin: 0">
                  <label>实验备注（可选）</label>
                  <input v-model="scores.note" class="input" placeholder="例如：刷题时正确率更高" />
                </div>
                <button class="btn btn-block" :disabled="finishing === String(item.id)" @click="finish(item)">
                  {{ finishing === String(item.id) ? '提交中...' : '提交实验结论' }}
                </button>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">历史实验</div>
              <div class="card-sub">按掌握度增益从高到低排序</div>
            </div>
          </div>
          <div v-if="!finished.length" class="empty">还没有完成的实验。</div>
          <div v-else class="stack">
            <div v-for="item in finished" :key="item.id" class="experiment-row click-line" style="padding: 8px; border-radius: 10px" role="button" tabindex="0" @click="openFinished(item)" @keydown.enter.prevent="openFinished(item)" @keydown.space.prevent="openFinished(item)">
              <div class="row-between">
                <b>{{ strategyLabel[item.strategy] || item.strategy }}</b>
                <span class="tag" :class="item.gain > 0 ? 'tag-review' : 'tag-pending'">
                  {{ item.gain > 0 ? '+' : '' }}{{ Math.round(item.gain * 100) }}pp
                </span>
              </div>
              <div class="small muted">
                即时 {{ item.immediate_score }} 分 · 延迟 {{ item.delayed_score }} 分 · {{ item.days }} 天
                <span v-if="item.note"> · {{ item.note }}</span>
              </div>
              <div class="row" style="margin-top: 6px">
                <button class="btn btn-ghost btn-sm" @click.stop="openReport(item)">实验报告</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="stack">
        <div class="card">
          <div class="card-title">创建实验</div>
          <div class="card-sub" style="margin-bottom: 12px">建议 3 天，实验期间只改变学习方式，不改变目标</div>
          <div class="field">
            <label>学习方式</label>
            <AppSelect v-model="form.strategy" :options="strategyOptions" placeholder="选择策略" />
          </div>
          <div class="field">
            <label>实验天数</label>
            <div class="row" style="gap: 6px; flex-wrap: wrap">
              <button
                v-for="d in [3, 5, 7]"
                :key="d"
                class="chip"
                :class="{ active: form.days === d }"
                @click="form.days = d"
              >
                {{ d }} 天
              </button>
              <input v-model.number="form.days" class="input" type="number" min="1" max="14" style="width: 90px" />
            </div>
          </div>
          <button class="btn btn-block" :disabled="creating" @click="create">
            {{ creating ? '创建中...' : '开始实验' }}
          </button>
        </div>

        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">策略收益排行</div>
              <div class="card-sub">来自已完成实验的平均掌握度增益</div>
            </div>
          </div>
          <div v-if="!data.ranking.length" class="empty">完成实验后这里会出现排行。</div>
          <div v-else class="stack">
            <div v-for="(item, index) in data.ranking" :key="item.strategy" class="strategy-row click-line" style="padding: 6px; border-radius: 8px" role="button" tabindex="0" @click="openRanking(item)" @keydown.enter.prevent="openRanking(item)" @keydown.space.prevent="openRanking(item)">
              <span class="rank-badge" :class="`rank-${index + 1}`">{{ index + 1 }}</span>
              <div style="flex: 1">
                <div class="row-between">
                  <b>{{ item.label }}</b>
                  <span>{{ Math.round(item.avg_gain * 100) }}pp</span>
                </div>
                <div class="bar" style="margin-top: 5px">
                  <i :style="{ width: Math.max(4, Math.min(100, item.avg_gain * 500)) + '%' }"></i>
                </div>
                <div class="small muted">{{ item.experiments }} 次实验</div>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-title">实验怎么算收益</div>
          <div class="small muted" style="margin-top: 10px; line-height: 1.9">
            收益 = 实验结束时平均掌握度 − 实验开始时平均掌握度。
            实验题由大模型基于目标知识点实时生成，做完拿到真实得分，避免手填导致收益失真。
          </div>
        </div>
      </div>
    </div>

    <div v-if="report" class="modal-mask" @click.self="report = null">
      <div class="modal knowledge-modal">
        <div class="card-head">
          <div>
            <div class="card-title">实验报告 · {{ report.title }}</div>
            <div class="card-sub">
              {{ report.days }} 天 · 样本量 {{ report.sample_size }} · 完成率 {{ Math.round(report.completion_rate * 100) }}%
            </div>
          </div>
          <button class="btn btn-ghost btn-sm" @click="report = null">关闭</button>
        </div>
        <div class="stack">
          <div class="grid grid-3" style="gap: 10px">
            <div class="stat">
              <div class="stat-label">前测掌握度</div>
              <div class="stat-value">{{ Math.round(report.pre_mastery * 100) }}%</div>
            </div>
            <div class="stat">
              <div class="stat-label">后测掌握度</div>
              <div class="stat-value">{{ Math.round(report.post_mastery * 100) }}%</div>
            </div>
            <div class="stat">
              <div class="stat-label">掌握度变化</div>
              <div class="stat-value">
                {{ report.mastery_gain > 0 ? '+' : '' }}{{ Math.round(report.mastery_gain * 100) }}pp
              </div>
            </div>
          </div>
          <div v-if="report.metrics.length" class="stack">
            <div class="small muted">指标</div>
            <div v-for="m in report.metrics" :key="m.metric + m.phase" class="kv">
              <span>{{ m.metric }}（{{ m.phase }}）</span>
              <strong>{{ m.value }}</strong>
            </div>
          </div>
          <div class="task-reason">{{ report.verdict }}</div>
          <div class="stack">
            <div class="small muted">局限说明</div>
            <div v-for="(item, index) in report.limitations" :key="index" class="small muted">· {{ item }}</div>
          </div>
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

    <div v-if="practiceItem" class="modal-mask" @click.self="closePractice">
      <div class="modal knowledge-modal">
        <div class="card-head">
          <div>
            <div class="card-title">本次实验的即时测题</div>
            <div class="card-sub">
              策略：{{ strategyLabel[practiceItem.strategy] || practiceItem.strategy }} ·
              {{ practiceItem.start_date }} ~ {{ practiceItem.end_date }} · {{ practiceEngine }}
            </div>
          </div>
          <button class="btn btn-ghost btn-sm" @click="closePractice">关闭</button>
        </div>

        <div v-if="practiceGenerating" class="empty">AI 正在基于当前目标知识点生成真实题目...</div>

        <div v-else-if="practiceResult" class="stack">
          <div class="row-between">
            <b>本次实验题结果</b>
            <span class="tag" :class="practiceResult.score >= 60 ? 'tag-review' : 'tag-skipped'">{{ practiceResult.score }} 分</span>
          </div>
          <div class="row" style="gap: 16px; flex-wrap: wrap">
            <span class="small muted">答对 {{ practiceResult.correct }} / {{ practiceResult.total }}</span>
            <span class="small muted">错题 {{ practiceResult.wrong.length }}</span>
            <span class="small muted">得分已作为实验即时测试分数</span>
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
          <div v-else class="empty">全部答对，这个策略下掌握得很好。</div>
          <div class="row" style="margin-top: 10px">
            <button class="btn btn-sm" :disabled="practiceGenerating" @click="generatePractice">再出一组</button>
            <button class="btn btn-ghost btn-sm" @click="closePractice">完成</button>
          </div>
        </div>

        <div v-else-if="practiceQuiz" class="stack">
          <div class="task-reason">
            题目按当前目标的知识点随机抽取，与所选策略无关——策略只改变学习方式，不改变题目学科。这一组分数记为「{{
              strategyLabel[practiceItem.strategy] || practiceItem.strategy
            }}」实验的即时测试得分。
          </div>
          <div class="small muted">
            共 {{ practiceQuiz.questions.length }} 题，已作答 {{ practiceAnswered }} / {{ practiceQuiz.questions.length }}
          </div>
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
          <button class="btn btn-block" :disabled="practiceSubmitting" @click="submitPractice">
            {{ practiceSubmitting ? '判分中...' : '提交实验题并取真实得分' }}
          </button>
        </div>

        <div v-else class="empty">暂无题目，请稍后重试。</div>
      </div>
    </div>
  </div>
</template>
