<script setup>
/**
 * 备考方案页：把「我要备考」变成一份可执行的网课式课表。
 *
 * 展示层级：
 * 1. 阶段时间轴（基础期 / 强化期 / 冲刺期 / 考前 3 日）+ 阶段模考成绩
 * 2. 天数选择器
 * 3. 当天的上午 / 下午 / 晚上三段课 —— 每段含：
 *    学什么（知识点 + 掌握度）、知识网络（先修/易混淆）、真实视频课程、随堂测入口
 */
import { computed, ref, watch } from 'vue'
import { api, apiUrl } from '../api'
import { store, notify } from '../store'
import QuizMaterial from '../components/QuizMaterial.vue'

const plan = ref(null)
const dayDetail = ref(null)
const loading = ref(true)
const dayLoading = ref(false)
const currentDay = ref(1)
const error = ref('')
const busy = ref(false)

const quiz = ref(null)
const quizAnswers = ref([])
const quizResult = ref(null)
const examBusy = ref(false)
const playing = ref(null)

function openPlayer(video) {
  if (!video) return
  playing.value = video
}

function closePlayer() {
  playing.value = null
}

const ROLE_LABEL = { new: '学新课', practice: '练题', review: '复习巩固' }

const stages = computed(() => (plan.value ? plan.value.stages : []))
const days = computed(() => (plan.value ? plan.value.days : []))
const currentStage = computed(() => {
  if (!plan.value || !dayDetail.value) return null
  return stages.value.find((item) => item.id === dayDetail.value.stage?.id) || null
})

function phaseTone(phase) {
  if (phase === 'foundation') return 'tag-study'
  if (phase === 'reinforce') return 'tag-practice'
  if (phase === 'sprint') return 'tag-conc'
  return 'tag-review'
}

function masteryPercent(value) {
  return Math.round((value || 0) * 100)
}

function masteryTone(value) {
  if (value >= 0.8) return 'tag-done'
  if (value >= 0.6) return 'tag-pending'
  if (value >= 0.4) return 'tag-review'
  return 'tag-skipped'
}

/**
 * 取某时段第 index 个知识点的掌握度。
 * 后端返回的 mastery 形如 {"10": 0.61}，键是 kp_id 的字符串形式，
 * 所以必须用 kp_ids[index] 查，否则永远取到 undefined 显示成 0%。
 */
function masteryOf(slot, index) {
  if (!slot || !slot.mastery) return 0
  const id = slot.kp_ids && slot.kp_ids[index]
  if (id === undefined || id === null) return 0
  const value = slot.mastery[String(id)]
  return typeof value === 'number' ? value : 0
}

// 阅读/听力题共享同一份材料，按 material.id 分组后材料只渲染一次
const quizGroups = computed(() => {
  const list = quiz.value?.questions || []
  const groups = []
  const byMaterial = new Map()
  list.forEach((question, index) => {
    const material = question.material
    const key = material?.id
    if (key && byMaterial.has(key)) {
      const group = byMaterial.get(key)
      group.questions.push({ question, index })
      return
    }
    const group = {
      key: key || `solo-${index}`,
      material: material || null,
      questions: [{ question, index }]
    }
    if (key) byMaterial.set(key, group)
    groups.push(group)
  })
  return groups
})

const materialOrder = computed(() => {
  const order = new Map()
  let index = 0
  for (const group of quizGroups.value) {
    if (!group.material) continue
    index += 1
    order.set(group.key, index)
  }
  return order
})

async function load() {
  // 目标尚未就绪（首次进入时 goals 列表还在异步加载）时不发请求，
  // 等 syncGoalSelection 设置好 currentGoalId 后 watch 会再次触发。
  if (!store.currentGoalId) return
  loading.value = true
  error.value = ''
  try {
    plan.value = await api.examPrepPlan(store.currentGoalId)
    currentDay.value = 1
    await loadDay(1)
  } catch (e) {
    error.value = e.message || '方案生成失败'
    notify(error.value, true)
  } finally {
    loading.value = false
  }
}

async function loadDay(index) {
  dayLoading.value = true
  currentDay.value = index
  quiz.value = null
  quizResult.value = null
  quizAnswers.value = []
  try {
    dayDetail.value = await api.examPrepDay(store.currentGoalId, index)
  } catch (e) {
    notify(e.message || '读取课表失败', true)
  } finally {
    dayLoading.value = false
  }
}

async function rebuild() {
  busy.value = true
  try {
    plan.value = await api.examPrepRebuild(store.currentGoalId)
    await loadDay(currentDay.value)
    notify('方案已按当前掌握度重新排布')
  } catch (e) {
    notify(e.message || '重建失败', true)
  } finally {
    busy.value = false
  }
}

// 封面：B 站图床按 Referer 防盗链，直接引用会 403（被浏览器 ORB 拦截），
// 所以优先走本站图片代理；代理不可用时回落到原图直链。
const coverFallback = new Set()

function coverOf(video) {
  if (!video) return ''
  const key = video.bvid || video.cover
  if (coverFallback.has(key)) return video.cover || ''
  if (video.cover_proxy) return apiUrl(video.cover_proxy)
  return video.cover || ''
}

// 来源摘要：优先用后端 sources 状态汇总（如「B站 4 条 · YouTube 未配置」），
// 旧响应没有 sources 时回退为来源名字符串。
function sourceSummary(video) {
  const states = Array.isArray(video.sources) ? video.sources : null
  if (states && states.length) {
    const parts = states
      .filter((s) => s.configured)
      .map((s) =>
        video.available && s.available && s.count
          ? `${s.label} ${s.count} 条`
          : `${s.label} 暂无匹配`
      )
    return parts.join(' · ') || '实时检索'
  }
  return video.source_label || video.source || '实时检索'
}

// 难度标签：出题按「概念→计算→综合→易错变式」层层递进，前端标出梯度
const DIFF_LABELS = { 1: '基础', 2: '进阶', 3: '综合', 4: '易错' }
function diffLabel(value) {
  return DIFF_LABELS[value] || ''
}

function onCoverError(event, video) {
  if (!video) return
  const key = video.bvid || video.cover
  if (coverFallback.has(key)) {
    // 原图也失败：留占位，不再反复重试
    event.target.style.visibility = 'hidden'
    return
  }
  coverFallback.add(key)
  event.target.src = video.cover || ''
}

async function startQuiz(kpIds) {
  examBusy.value = true
  quizResult.value = null
  try {
    const first = kpIds && kpIds.length ? kpIds[0] : null
    const res = await api.generateQuiz(store.currentGoalId, { kp_id: first, kp_ids: kpIds, count: 4 })
    const questions = res?.questions || []
    if (!questions.length) {
      notify('题库暂未返回题目，请稍后重试', true)
      return
    }
    quiz.value = res
    quizAnswers.value = new Array(questions.length).fill(-1)
    requestAnimationFrame(() => {
      const card = document.getElementById('ep-quiz-card')
      if (card) card.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  } catch (e) {
    notify(e.message || '出题失败', true)
  } finally {
    examBusy.value = false
  }
}

async function submitQuiz() {
  if (!quiz.value) return
  examBusy.value = true
  try {
    quizResult.value = await api.submitQuiz(store.currentGoalId, {
      quiz_id: quiz.value.quiz_id,
      answers: quizAnswers.value
    })
  } catch (e) {
    notify(e.message || '提交失败', true)
  } finally {
    examBusy.value = false
  }
}

async function startStageExam(stage) {
  const target = stage || currentStage.value
  if (!target) return
  examBusy.value = true
  quizResult.value = null
  try {
    const res = await api.examPrepStageExam(store.currentGoalId, target.id, 6)
    quiz.value = res
    quizAnswers.value = new Array(res.questions.length).fill(-1)
  } catch (e) {
    notify(e.message || '模考出卷失败', true)
  } finally {
    examBusy.value = false
  }
}

// —— 阶段卡交互：点击展开操作面板 ——
const expandedStageId = ref(null)

function toggleStage(stage) {
  expandedStageId.value = expandedStageId.value === stage.id ? null : stage.id
}

function gotoStageFirstDay(stage) {
  const days = plan.value?.days || []
  const day = days.find((d) => d.phase === stage.phase) || days.find((d) => d.day_date >= stage.start_date)
  if (!day) {
    notify('该阶段还没有安排日程', true)
    return
  }
  expandedStageId.value = null
  loadDay(day.day_index)
}

async function submitStageExam() {
  if (!quiz.value) return
  examBusy.value = true
  try {
    const res = await api.examPrepStageExamSubmit(store.currentGoalId, quiz.value.quiz_id, quizAnswers.value)
    quizResult.value = res
    // 阶段成绩回写到阶段轴
    const stage = stages.value.find((item) => item.id === res.stage_id)
    if (stage) {
      stage.exam_score = res.score
      stage.exam_total = res.total
      stage.exam_passed = res.passed
      stage.status = 'done'
    }
    notify(res.passed ? `模考通过：${res.score} / ${res.total}` : `模考未通过：${res.score} / ${res.total}，回炉补这一阶段`, !res.passed)
  } catch (e) {
    notify(e.message || '提交失败', true)
  } finally {
    examBusy.value = false
  }
}

watch(() => store.currentGoalId, load, { immediate: true })
</script>

<template>
  <div v-if="!store.currentGoalId" class="empty">
    还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建目标。
  </div>

  <div v-else-if="loading" class="empty">正在生成备考方案（阶段划分 + 每日课表）...</div>

  <div v-else-if="error" class="empty">
    {{ error }}
    <div class="small muted" style="margin-top: 8px">
      备考方案需要知识点。先到「目标与资料」导入学习资料，再回来生成。
    </div>
  </div>

  <div v-else class="stack">
    <!-- ===== 顶部：考试信息 + 阶段时间轴 ===== -->
    <div class="hero">
      <h1>备考方案 · {{ plan.exam_name }}</h1>
      <p>
        一整套从今天到考试的网课式计划：先按剩余天数切成阶段，再把每天拆成
        <b>上午学新课 / 下午练题 / 晚上复盘</b> 三段，每段都挂上对应知识点、真实视频课程和随堂测，
        每个阶段结束时还有一次模考。视频课来自 B 站等真实课程检索，按本课时知识点匹配；随堂测由题库即时出题。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ plan.days_left }}</strong>
          <span>距考试天数</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ plan.totals.days }}</strong>
          <span>学习天数</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ plan.totals.stages }}</strong>
          <span>备考阶段</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ Math.round(plan.totals.minutes / 60) }}</strong>
          <span>总时长(小时)</span>
        </div>
      </div>
      <div class="row-between" style="margin-top: 12px">
        <span class="small muted">考试日 {{ plan.exam_date }} · 每日投入 {{ plan.daily_minutes }} 分钟</span>
        <button class="btn btn-ghost btn-sm" :disabled="busy" @click="rebuild">
          {{ busy ? '重排中...' : '按当前掌握度重排' }}
        </button>
      </div>
    </div>

    <!-- ===== 阶段时间轴 ===== -->
    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">备考阶段</div>
          <div class="card-sub">按剩余天数自动切分，每阶段一次模考</div>
        </div>
      </div>
      <div class="ep-stages">
        <div
          v-for="stage in stages"
          :key="stage.id"
          class="ep-stage is-clickable"
          :class="{ expanded: expandedStageId === stage.id }"
          role="button"
          tabindex="0"
          @click="toggleStage(stage)"
          @keydown.enter.prevent="toggleStage(stage)"
        >
          <div class="ep-stage-top">
            <span class="tag" :class="phaseTone(stage.phase)">{{ stage.title.split(' · ')[0] }}</span>
            <span class="small muted">{{ stage.start_date }} ~ {{ stage.end_date }}</span>
          </div>
          <div class="ep-stage-title">{{ stage.title.split(' · ')[1] || stage.title }}</div>
          <div class="ep-stage-ratio">{{ stage.ratio }}</div>
          <div class="small muted">
            {{ stage.day_count }} 天 · 目标保持率 {{ Math.round(stage.target_retention * 100) }}%
          </div>
          <div v-if="stage.exam_score !== null && stage.exam_score !== undefined" class="ep-stage-exam" :class="{ passed: stage.exam_passed }">
            模考 {{ stage.exam_score }} / {{ stage.exam_total }} · {{ stage.exam_passed ? '通过' : '未通过' }}
          </div>
          <div v-else class="ep-stage-exam pending">模考未进行</div>
          <div v-if="expandedStageId === stage.id" class="ep-stage-more" @click.stop>
            <div class="small muted">阶段策略：{{ stage.title }}。点击下方进入该阶段学习，或先做一次阶段模考检验水平。</div>
            <div class="ep-stage-actions">
              <button class="btn btn-sm" :disabled="examBusy" @click="startStageExam(stage)">
                {{ stage.exam_passed !== null && stage.exam_passed !== undefined ? '再测一次' : '开始阶段模考' }}
              </button>
              <button class="btn btn-sm btn-ghost" @click="gotoStageFirstDay(stage)">进入阶段首日</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ===== 天数选择器 ===== -->
    <div class="row-between">
      <div class="chip-list">
        <button
          v-for="day in days.slice(0, 14)"
          :key="day.day_index"
          class="chip"
          :class="{ active: currentDay === day.day_index }"
          @click="loadDay(day.day_index)"
        >
          第 {{ day.day_index }} 天
          <span v-if="day.has_stage_exam" class="ep-chip-flag">模考</span>
        </button>
        <span v-if="days.length > 14" class="small muted">共 {{ days.length }} 天，完整方案可在下方按阶段查看</span>
      </div>
    </div>

    <!-- ===== 当天三段课 ===== -->
    <div v-if="dayLoading" class="empty">正在加载课表与视频课程...</div>

    <template v-else-if="dayDetail">
      <div class="card ep-day-head">
        <div>
          <div class="card-title">第 {{ dayDetail.day_index }} 天 · {{ dayDetail.day_date }}</div>
          <div class="card-sub">{{ currentStage ? currentStage.title : '' }}</div>
        </div>
        <div class="row-between" style="gap: 8px">
          <span v-if="dayDetail.has_stage_exam" class="tag tag-conc">今日含阶段模考</span>
          <button class="btn btn-sm" :disabled="examBusy" @click="startStageExam">
            {{ examBusy ? '出卷中...' : '开始阶段模考' }}
          </button>
        </div>
      </div>

      <div class="ep-slots">
        <div v-for="slot in dayDetail.slots" :key="slot.slot" class="card ep-slot">
          <div class="ep-slot-head">
            <div class="ep-slot-when">
              <span class="ep-slot-icon">{{ slot.icon }}</span>
              <div>
                <div class="ep-slot-label">{{ slot.label }}</div>
                <div class="small muted">{{ slot.range }}</div>
              </div>
            </div>
            <div class="row-between" style="gap: 6px">
              <span class="tag" :class="slot.role === 'new' ? 'tag-study' : slot.role === 'practice' ? 'tag-practice' : 'tag-review'">
                {{ slot.role_label }}
              </span>
              <span class="small muted">{{ slot.minutes }} 分钟</span>
            </div>
          </div>

          <div class="ep-slot-title">{{ slot.title }}</div>
          <div class="ep-slot-focus">{{ slot.focus }}</div>

          <!-- 学什么 -->
          <div class="ep-block">
            <div class="ep-block-title">
              本节学什么
              <span class="small muted">{{ slot.kp_names.length }} 个知识点</span>
            </div>
            <div class="ep-kps">
              <!-- key 必须带下标：同一时段里复盘可能重复出现同一知识点，纯名称做 key 会丢节点 -->
              <div v-for="(kp, index) in slot.kp_names" :key="`${kp}-${index}`" class="ep-kp">
                <span class="ep-kp-name">{{ kp }}</span>
                <!-- mastery 以 kp_id 为键（JSON 里是字符串），必须按 id 取，不能用下标 -->
                <span class="tag tag-sm" :class="masteryTone(masteryOf(slot, index))">
                  掌握 {{ masteryPercent(masteryOf(slot, index)) }}%
                </span>
              </div>
            </div>
          </div>

          <!-- 知识网络 -->
          <div v-if="slot.network && slot.network.nodes.length" class="ep-block">
            <div class="ep-block-title">
              知识网络
              <span class="small muted">{{ slot.network.nodes.length }} 节点 · {{ slot.network.edges.length }} 条关系</span>
            </div>
            <div class="ep-net">
              <div v-for="node in slot.network.nodes" :key="node.id" class="ep-net-node">
                <span class="ep-net-dot" :class="node.level"></span>
                <span class="ep-net-name">{{ node.name }}</span>
                <span class="small muted">{{ masteryPercent(node.mastery) }}%</span>
              </div>
              <div v-if="slot.network.edges.length" class="ep-net-edges">
                <span v-for="(edge, index) in slot.network.edges.slice(0, 5)" :key="index" class="ep-edge">
                  {{ edge.from_name }} <b>--{{ edge.label }}--></b> {{ edge.to_name }}
                </span>
              </div>
            </div>
          </div>

          <!-- 真实视频课程 -->
          <div class="ep-block">
            <div class="ep-block-title">
              视频课程
              <span v-if="slot.video && slot.video.engine" class="small muted">
                {{ sourceSummary(slot.video) }} · {{ slot.video.engine === 'cached' ? '缓存' : slot.video.engine === 'mixed' ? '缓存+实时' : '实时检索' }}
              </span>
            </div>
            <div v-if="!slot.video || !slot.video.available" class="ep-video-empty">
              {{ (slot.video && slot.video.detail) || '该时段暂未检索到匹配课程' }}
              <span v-if="slot.video && slot.video.query && slot.video.query.length" class="small muted">（检索词：{{ slot.video.query.slice(0, 3).join('、') }}）</span>
            </div>
            <div v-else class="ep-videos">
              <button
                v-for="video in slot.video.items"
                :key="video.bvid || video.id || video.url"
                type="button"
                class="ep-video"
                @click="openPlayer(video)"
              >
                <div class="ep-video-cover">
                  <img
                    :src="coverOf(video)"
                    :alt="video.title"
                    loading="lazy"
                    referrerpolicy="no-referrer"
                    @error="onCoverError($event, video)"
                  />
                  <span class="ep-video-src">{{ video.source_label || video.source }}</span>
                  <span class="ep-video-dur">{{ video.duration }}</span>
                  <span class="ep-video-play">课内播放</span>
                </div>
                <div class="ep-video-body">
                  <div class="ep-video-title">{{ video.title }}</div>
                  <div class="small muted">
                    {{ video.author }} · 播放 {{ video.play }}
                    <span v-if="video.matched_kp" class="ep-video-kp">对应：{{ video.matched_kp }}</span>
                  </div>
                </div>
              </button>
            </div>
          </div>

          <!-- 随堂测 -->
          <div class="ep-block">
            <div class="ep-block-title">随堂测</div>
            <div class="row-between">
              <span class="small muted">
                {{ slot.role === 'new' ? '看完视频做 4 题，确认真的懂了' : slot.role === 'practice' ? '本节重点练 4 题，错的当场进错题本' : '用随堂测检查今天是否真的记住' }}
              </span>
              <div class="row-between" style="gap: 8px">
                <router-link class="btn btn-sm btn-ghost" to="/today?tab=voice&mode=shadow&from=exam">口语跟读</router-link>
                <button class="btn btn-sm" :disabled="examBusy" @click="startQuiz(slot.kp_ids)">
                  {{ examBusy ? '出题中...' : '开始出题' }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ===== 试卷与判分 ===== -->
      <div v-if="quiz" id="ep-quiz-card" class="card">
        <div class="card-head">
          <div>
            <div class="card-title">
              {{ quizResult ? '判分结果' : (quiz.stage_title ? '阶段模考卷' : '随堂测卷') }}
            </div>
            <div class="card-sub">
              共 {{ quiz.questions.length }} 题
              <span v-if="quiz.target_retention"> · 目标保持率 {{ Math.round(quiz.target_retention * 100) }}%</span>
            </div>
          </div>
        </div>

        <div v-if="quizResult" class="ep-result">
          <div class="ep-result-score">{{ quizResult.score }} 分</div>
          <div class="small">
            答对 {{ quizResult.correct }} / {{ quizResult.total }}
            <span v-if="quizResult.passed !== undefined">
              · {{ quizResult.passed ? '通过' : '未通过（需要回炉补这一阶段）' }}
            </span>
          </div>
          <div v-if="(quizResult.materials || []).length" class="ep-result-materials">
            <div class="small muted">本次材料</div>
            <QuizMaterial
              v-for="(material, index) in quizResult.materials"
              :key="material.id || index"
              :material="material.kind === 'listening' ? { ...material, audio_script: material.transcript } : material"
              :order="index + 1"
              reveal
            />
          </div>
          <div v-if="quizResult.wrong && quizResult.wrong.length" class="ep-wrong">
            <div v-for="item in quizResult.wrong" :key="item.index" class="ep-wrong-item">
              <div class="small muted">
                {{ item.kp_name }} · {{ item.category_label }}
                <span v-if="diffLabel(item.difficulty)" class="ep-diff" :data-d="item.difficulty">{{ diffLabel(item.difficulty) }}</span>
              </div>
              <div>{{ item.question }}</div>
              <div class="small muted">你选：{{ item.chosen }} / 正确：{{ item.correct }}</div>
              <div v-if="item.solution_steps && item.solution_steps.length" class="ep-steps">
                <div class="small muted">解题步骤</div>
                <ol class="ep-steps-list">
                  <li v-for="(step, stepIndex) in item.solution_steps" :key="stepIndex">{{ step }}</li>
                </ol>
              </div>
              <div class="small ep-explain">{{ item.explanation || '暂无解析' }}</div>
              <div v-if="item.misconception" class="small ep-mis">干扰项诊断：{{ item.misconception }}</div>
            </div>
          </div>
        </div>

        <div v-else class="stack" style="margin-top: 10px">
          <div v-for="group in quizGroups" :key="group.key" class="ep-quiz-group">
            <QuizMaterial
              v-if="group.material"
              :material="group.material"
              :order="materialOrder.get(group.key) || 1"
            />
            <div
              v-for="entry in group.questions"
              :key="entry.index"
              class="ep-question"
              :class="{ 'ep-question-cont': group.material }"
            >
              <div class="ep-question-head">
                <span class="ep-question-index">{{ entry.index + 1 }}</span>
                <span class="small muted">{{ entry.question.kp_name }}</span>
                <span
                  v-if="diffLabel(entry.question.difficulty)"
                  class="ep-diff"
                  :data-d="entry.question.difficulty"
                >{{ diffLabel(entry.question.difficulty) }}</span>
              </div>
              <div class="ep-question-text">{{ entry.question.question }}</div>
              <div class="ep-options">
                <button
                  v-for="(option, optionIndex) in entry.question.options"
                  :key="optionIndex"
                  class="ep-option"
                  :class="{ picked: quizAnswers[entry.index] === optionIndex }"
                  @click="quizAnswers[entry.index] = optionIndex"
                >
                  <span class="ep-option-key">{{ 'ABCD'[optionIndex] }}</span>
                  <span>{{ option }}</span>
                </button>
              </div>
            </div>
          </div>
          <div class="row-between">
            <button class="btn" :disabled="examBusy" @click="quiz.stage_id ? submitStageExam() : submitQuiz()">
              {{ examBusy ? '判分中...' : '提交判分' }}
            </button>
          </div>
        </div>
      </div>
    </template>
    <div v-if="playing" class="ep-player-mask" @click.self="closePlayer">
      <div class="ep-player-box" role="dialog" aria-modal="true" @keydown.esc="closePlayer">
        <div class="ep-player-bar">
          <div class="ep-player-heading">{{ playing.title }}</div>
          <div class="ep-player-actions">
            <a class="btn btn-sm btn-ghost" :href="playing.url" target="_blank" rel="noopener">在源站打开</a>
            <button class="btn btn-sm" type="button" @click="closePlayer">关闭</button>
          </div>
        </div>
        <iframe
          v-if="playing.player_url"
          class="ep-player-frame"
          :src="playing.player_url"
          title="课程播放"
          allow="fullscreen; encrypted-media"
          allowfullscreen
        />
        <div v-else class="empty">无法内嵌播放，请在源站打开这节课。</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ep-stages {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
}

.ep-stage {
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px;
  background: var(--surface-2);
  display: flex;
  flex-direction: column;
  gap: 6px;
  cursor: pointer;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.ep-stage:hover {
  border-color: var(--blue, #2563eb);
  box-shadow: 0 6px 18px -10px rgba(37, 99, 235, 0.35);
  transform: translateY(-1px);
}

.ep-stage:focus-visible {
  outline: 2px solid var(--blue, #2563eb);
  outline-offset: 2px;
}

.ep-stage.expanded {
  border-color: var(--blue, #2563eb);
  box-shadow: 0 8px 22px -12px rgba(37, 99, 235, 0.4);
}

.ep-stage-more {
  margin-top: 6px;
  padding-top: 8px;
  border-top: 1px dashed var(--line);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ep-stage-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.ep-stage-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.ep-stage-title {
  font-weight: 600;
  font-size: 13px;
}

.ep-stage-ratio {
  font-size: 12px;
  color: var(--ink-2);
  background: var(--surface);
  border-radius: 8px;
  padding: 4px 8px;
}

.ep-stage-exam {
  margin-top: auto;
  font-size: 12px;
  padding: 5px 8px;
  border-radius: 8px;
  background: #fef3c7;
  color: #92400e;
}

.ep-stage-exam.passed {
  background: #dcfce7;
  color: #166534;
}

.ep-stage-exam.pending {
  background: var(--surface);
  color: var(--muted);
}

.ep-chip-flag {
  margin-left: 4px;
  font-size: 10px;
  color: #b45309;
}

.ep-day-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.ep-slots {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  align-items: start;
}

.ep-slot {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.ep-slot-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.ep-slot-when {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ep-slot-icon {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: #eff6ff;
  color: var(--brand-dark);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
}

.ep-slot-label {
  font-weight: 600;
  font-size: 14px;
}

.ep-slot-title {
  font-weight: 600;
  font-size: 13px;
}

.ep-slot-focus {
  font-size: 12px;
  color: var(--ink-2);
  line-height: 1.6;
}

.ep-block {
  border-top: 1px dashed var(--line);
  padding-top: 9px;
}

.ep-block-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-2);
  margin-bottom: 6px;
}

.ep-kps {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.ep-kp {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 8px;
  background: var(--surface-2);
}

.ep-kp-name {
  font-weight: 500;
}

.tag-sm {
  font-size: 11px;
  padding: 1px 7px;
}

.ep-net {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.ep-net-node {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
}

.ep-net-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #cbd5e1;
  flex: none;
}

.ep-net-dot.excellent { background: #22c55e; }
.ep-net-dot.good { background: #3b82f6; }
.ep-net-dot.risk { background: #f59e0b; }
.ep-net-dot.critical { background: #ef4444; }

.ep-net-edges {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-top: 4px;
  padding-top: 5px;
  border-top: 1px dashed var(--line);
}

.ep-edge {
  font-size: 11px;
  color: var(--muted);
}

.ep-edge b {
  color: var(--brand);
  font-weight: 600;
}

.ep-videos {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ep-video {
  display: flex;
  gap: 9px;
  text-decoration: none;
  color: inherit;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 7px;
  background: var(--surface);
  transition: border-color 0.15s ease;
}

.ep-video:hover {
  border-color: var(--brand);
}

.ep-video-cover {
  position: relative;
  width: 104px;
  height: 62px;
  border-radius: 7px;
  overflow: hidden;
  flex: none;
  background: #0f2a4a;
}

.ep-video-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.ep-video-src {
  position: absolute;
  left: 4px;
  top: 4px;
  font-size: 10px;
  background: rgba(12, 20, 46, 0.82);
  color: #cfe0ff;
  padding: 1px 6px;
  border-radius: 4px;
  letter-spacing: 0.5px;
}

.ep-video-dur {
  position: absolute;
  right: 4px;
  bottom: 4px;
  font-size: 10px;
  background: rgba(0, 0, 0, 0.72);
  color: #fff;
  padding: 1px 5px;
  border-radius: 4px;
}

.ep-video-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.ep-video-title {
  font-size: 12px;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.ep-video-empty {
  font-size: 12px;
  color: var(--muted);
  padding: 9px;
  border: 1px dashed var(--line);
  border-radius: 9px;
  line-height: 1.6;
}

.ep-quiz-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ep-question-cont {
  border-left: 2px solid var(--line);
  padding-left: 10px;
}

.ep-result-materials {
  margin: 12px 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ep-result {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
}

.ep-result-score {
  font-size: 28px;
  font-weight: 700;
  color: var(--brand-dark);
}

.ep-wrong {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 6px;
}

.ep-wrong-item {
  border-left: 3px solid #ef4444;
  padding: 6px 10px;
  background: var(--surface-2);
  border-radius: 0 8px 8px 0;
  font-size: 12px;
  line-height: 1.6;
}

.ep-question {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px 12px;
}

.ep-question-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 5px;
}

.ep-question-index {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  background: var(--brand);
  color: #fff;
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ep-question-text {
  font-size: 13px;
  line-height: 1.65;
  margin-bottom: 8px;
}

.ep-options {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.ep-option {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  text-align: left;
  padding: 7px 10px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: var(--surface);
  cursor: pointer;
  font-size: 12px;
  line-height: 1.55;
}

.ep-option:hover {
  border-color: var(--brand);
}

.ep-option.picked {
  border-color: var(--brand);
  background: #eff6ff;
}

.ep-option-key {
  font-weight: 700;
  color: var(--brand-dark);
  flex: none;
}

@media (max-width: 1100px) {
  .ep-stages {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .ep-slots {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .ep-stages {
    grid-template-columns: 1fr;
  }
  .ep-video {
    flex-direction: column;
  }
  .ep-video-cover {
    width: 100%;
    height: 132px;
  }
}

.ep-video {
  width: 100%;
  font: inherit;
  cursor: pointer;
  text-align: left;
}
.ep-video-play {
  position: absolute;
  left: 4px;
  bottom: 4px;
  font-size: 10px;
  background: rgba(37, 99, 235, 0.92);
  color: #fff;
  padding: 1px 6px;
  border-radius: 4px;
}
.ep-player-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.55);
  z-index: 40;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.ep-player-box {
  width: min(960px, 100%);
  background: var(--surface, #fff);
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 20px 50px -24px rgba(15, 23, 42, 0.55);
}
.ep-player-bar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 12px 14px;
  border-bottom: 1px solid var(--line);
}
.ep-player-heading {
  font-weight: 600;
  font-size: 14px;
  line-height: 1.4;
}
.ep-player-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.ep-player-frame {
  width: 100%;
  height: min(62vh, 540px);
  border: 0;
  background: #000;
}
</style>
