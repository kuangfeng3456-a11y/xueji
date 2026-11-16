<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { store, notify } from '../store'
import VocabLab from '../components/VocabLab.vue'

const router = useRouter()
const route = useRoute()
const packages = ref([])
const loading = ref(true)
const applying = ref('')
const marking = ref(false)
const filterTag = ref('')
const expanded = ref([])
const detail = ref(null)
const practicing = ref(false)
const practiceMode = ref('')
const practiceProbe = ref(null)
const practiceSelected = ref(null)
const practiceResult = ref(null)
const quizData = ref(null)
const quizAnswers = ref([])
const quizResult = ref(null)
const modulePanel = ref(null)
const vocabTarget = ref(null)

const createOpen = ref(false)
const createStep = ref(1)
const creating = ref(false)
const createdPackage = ref(null)
const draft = reactive({
  name: '',
  subject: '通用',
  description: '',
  tags: '',
  tree: ''
})

const SAMPLE_TREE = `听力: 短对话(1.4), 长对话(1.5), 听力篇章(1.6)
阅读: 选词填空(1.4), 仔细阅读(1.9)
写作: 议论文结构(1.4), 常用句型(1.3)`

const draftPoints = computed(() => parseTree(draft.tree))
const draftModules = computed(() => draftPoints.value.filter((item) => !item.parent).length)
const draftLeaves = computed(() => draftPoints.value.filter((item) => item.parent).length)
const isVocabName = (name) => /词/.test(String(name || ''))

const goalName = computed(() => {
  const goal = store.goals.find((item) => item.id === store.currentGoalId)
  return goal ? goal.exam_name : null
})

const totalPoints = computed(() =>
  packages.value.reduce((sum, item) => sum + item.point_count, 0)
)

const allTags = computed(() => {
  const tags = new Set()
  packages.value.forEach((item) => item.tags.forEach((tag) => tags.add(tag)))
  return [...tags]
})

const visiblePackages = computed(() => {
  if (!filterTag.value) return packages.value
  return packages.value.filter((item) => item.tags.includes(filterTag.value))
})

const recommendation = computed(() => {
  const point = detail.value?.point
  if (!point) return ''
  if (point.mastery === null || point.mastery === undefined) {
    return '导入后系统会按「权重 × 未掌握 × 临近系数」安排学习任务，并自动生成复习节点。'
  }
  if (point.mastery < 0.35) {
    return '掌握度偏低：先补基础概念，做 2 道基础题确认理解，再进入练习阶段。'
  }
  if (point.mastery < 0.7) {
    return '已懂但不够稳：用同类题加深，按 1 / 2 / 4 / 7 / 15 天的间隔复习。'
  }
  return '掌握较好：保持手感，优先完成到期复习任务，把时间留给更薄弱的知识点。'
})

async function load() {
  loading.value = true
  try {
    packages.value = await api.skillPackages(store.currentGoalId || 0)
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

function isExpanded(slug) {
  return expanded.value.includes(slug)
}

function toggleExpand(slug) {
  expanded.value = isExpanded(slug)
    ? expanded.value.filter((item) => item !== slug)
    : [...expanded.value, slug]
}

function toggleTag(tag) {
  filterTag.value = filterTag.value === tag ? '' : tag
}

function openPoint(packageItem, point) {
  detail.value = { packageItem, point: { ...point } }
}

function grouped(packageItem) {
  const groups = new Map()
  for (const point of packageItem.point_details) {
    const key = point.parent || '核心知识点'
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(point)
  }
  return [...groups.entries()]
}

function shortPoints(packageItem) {
  return packageItem.point_details.slice(0, 6)
}

function openModule(packageItem, parentName) {
  const points = packageItem.point_details.filter(
    (point) => (point.parent || '核心知识点') === parentName
  )
  const self = packageItem.point_details.find(
    (point) => point.name === parentName && !point.parent
  )
  const scored = points.filter((point) => point.mastery !== null && point.mastery !== undefined)
  const mastery = scored.length
    ? scored.reduce((sum, point) => sum + point.mastery, 0) / scored.length
    : null
  modulePanel.value = {
    packageItem,
    name: parentName,
    kp_id: self ? self.kp_id : null,
    points,
    mastery
  }
}

function openVocab(kpId, title) {
  if (!kpId) {
    notify('先应用学科包，导入词汇知识点后即可背单词', true)
    return
  }
  vocabTarget.value = { kpId, title }
}

function startModuleQuiz() {
  const panel = modulePanel.value
  if (!panel?.kp_id) {
    notify('先应用学科包，导入知识点后即可练习', true)
    return
  }
  detail.value = {
    packageItem: panel.packageItem,
    point: {
      name: panel.name,
      parent: null,
      weight: 1,
      kp_id: panel.kp_id,
      mastery: panel.mastery,
      next_review_at: null
    }
  }
  modulePanel.value = null
  startQuiz()
}

function parseTree(text) {
  const points = []
  const seen = new Set()
  const push = (name, parent, weight) => {
    const clean = String(name || '').trim()
    if (!clean || seen.has(clean)) return
    seen.add(clean)
    points.push({ name: clean, parent, weight })
  }
  for (const raw of String(text || '').split('\n')) {
    const line = raw.trim()
    if (!line) continue
    const match = line.split(/[:：]/)
    const moduleName = (match[0] || '').trim()
    if (!moduleName) continue
    push(moduleName, null, 1.5)
    const rest = match.slice(1).join(':')
    if (!rest.trim()) continue
    for (const segment of rest.split(/[,，、]/)) {
      const piece = segment.trim()
      if (!piece) continue
      const weighted = piece.match(/^(.+?)[（(]\s*([\d.]+)\s*[)）]$/)
      if (weighted) push(weighted[1], moduleName, Number(weighted[2]) || 1.2)
      else push(piece, moduleName, 1.2)
    }
  }
  return points
}

function openCreate() {
  createOpen.value = true
  createStep.value = 1
  createdPackage.value = null
}

function fillSample() {
  draft.tree = SAMPLE_TREE
}

function nextStep() {
  if (createStep.value === 1) {
    if (draft.name.trim().length < 2) {
      notify('学科包名称至少 2 个字', true)
      return
    }
    createStep.value = 2
    return
  }
  if (createStep.value === 2) {
    if (!draftPoints.value.length) {
      notify('至少填写一个模块或知识点', true)
      return
    }
    createStep.value = 3
  }
}

async function submitPackage() {
  creating.value = true
  try {
    const result = await api.createSkillPackage({
      name: draft.name.trim(),
      subject: draft.subject.trim() || '通用',
      description: draft.description.trim(),
      tags: draft.tags
        .split(/[,，、\s]+/)
        .map((tag) => tag.trim())
        .filter(Boolean),
      points: draftPoints.value
    })
    createdPackage.value = result
    createStep.value = 4
    notify(`已注册「${result.name}」，共 ${result.point_count} 个知识点`)
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    creating.value = false
  }
}

async function applyCreated() {
  if (!createdPackage.value) return
  await apply({ slug: createdPackage.value.slug, name: createdPackage.value.name })
  createOpen.value = false
}

async function apply(packageItem) {
  if (!store.currentGoalId) {
    notify('请先在「目标与资料」创建一个考试目标', true)
    return
  }
  applying.value = packageItem.slug
  try {
    const result = await api.applySkillPackage(packageItem.slug, store.currentGoalId)
    notify(`已从「${result.package}」导入 ${result.created} 个知识点`)
    detail.value = null
    await load()
    store.goals = await api.goals()
  } catch (e) {
    notify(e.message, true)
  } finally {
    applying.value = ''
  }
}

async function mark(correct) {
  const point = detail.value?.point
  if (!point?.kp_id) return
  marking.value = true
  try {
    const data = await api.answer(store.currentGoalId, point.kp_id, correct)
    point.mastery = data.value
    point.next_review_at = data.next_review_at
    notify(`「${point.name}」掌握度更新为 ${Math.round(data.value * 100)}%`)
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    marking.value = false
  }
}

async function startPractice() {
  const point = detail.value?.point
  if (!point?.kp_id) return
  practicing.value = true
  practiceMode.value = 'probe'
  practiceProbe.value = null
  practiceSelected.value = null
  practiceResult.value = null
  try {
    const items = await api.generateProbes(store.currentGoalId, {
      kind: 'probe',
      kp_id: point.kp_id,
      count: 1
    })
    practiceProbe.value = items[0]
  } catch (e) {
    notify(e.message, true)
    practicing.value = false
  }
}

async function submitPractice() {
  if (practiceSelected.value === null) {
    notify('请先选择一个答案', true)
    return
  }
  try {
    const data = await api.submitProbe(practiceProbe.value.id, practiceSelected.value)
    practiceResult.value = data
    if (data.mastery !== null && data.mastery !== undefined) {
      detail.value.point.mastery = data.mastery
    }
    await load()
  } catch (e) {
    notify(e.message, true)
  }
}

async function startQuiz() {
  const point = detail.value?.point
  if (!point?.kp_id) return
  practicing.value = true
  practiceMode.value = 'quiz'
  quizData.value = null
  quizAnswers.value = []
  quizResult.value = null
  try {
    const data = await api.generateQuiz(store.currentGoalId, {
      kp_id: point.kp_id,
      count: 3
    })
    quizData.value = data
    quizAnswers.value = new Array(data.questions.length).fill(null)
  } catch (e) {
    notify(e.message, true)
    practicing.value = false
  }
}

async function submitQuizPractice() {
  if (quizAnswers.value.some((item) => item === null)) {
    notify('请完成所有题目后再提交', true)
    return
  }
  try {
    const data = await api.submitQuiz(store.currentGoalId, {
      quiz_id: quizData.value.quiz_id,
      answers: quizAnswers.value
    })
    quizResult.value = data
    await load()
  } catch (e) {
    notify(e.message, true)
  }
}

function resetPractice() {
  practicing.value = false
  practiceMode.value = ''
  practiceProbe.value = null
  practiceSelected.value = null
  practiceResult.value = null
  quizData.value = null
  quizAnswers.value = []
  quizResult.value = null
}

function go(path) {
  detail.value = null
  router.push(path)
}

onMounted(async () => {
  await load()
  if (route.query.create === '1' && store.user?.campus_access) {
    router.replace({ path: '/collab', query: { tab: 'packages' } })
  }
})

const marketStats = computed(() => ({
  total: packages.value.length,
  points: totalPoints.value,
  tags: allTags.value.length,
  shown: visiblePackages.value.length
}))
</script>

<template>
  <div class="stack">
    <div class="hero">
      <h1>多学科 Skill 包市场</h1>
      <p>
        学科包把知识点树、权重和推荐练习封装成可替换的 Skill。换一个学科，只需要换一个包，
        计划的排程、错题归因、复习排期和周报能力全部复用。点击卡片、标签或任意知识点都能查看详情。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ packages.length }}</strong>
          <span>可用学科包</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ goalName || '未选择' }}</strong>
          <span>当前应用目标</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ totalPoints }}</strong>
          <span>知识点总数</span>
        </div>
      </div>
    </div>

    <div class="row-between" style="gap: 12px; flex-wrap: wrap">
      <div class="chip-list">
        <button class="chip" :class="{ active: !filterTag }" @click="filterTag = ''">全部学科</button>
        <button
          v-for="tag in allTags"
          :key="tag"
          class="chip"
          :class="{ active: filterTag === tag }"
          @click="toggleTag(tag)"
        >
          {{ tag }}
        </button>
      </div>
      <span class="small muted">点击卡片展开全部知识点，点击知识点查看掌握度与操作</span>
    </div>

    <div v-if="loading" class="empty">正在加载学科包...</div>

    <div v-else class="market-grid">
      <div
        v-for="item in visiblePackages"
        :key="item.slug"
        class="market-card"
        :class="{ expanded: isExpanded(item.slug) }"
        @click="toggleExpand(item.slug)"
      >
        <div class="row-between">
          <div>
            <div class="market-title">{{ item.name }}</div>
            <div class="small muted">{{ item.subject }} · 官方 Skill 包</div>
          </div>
          <div class="row" style="gap: 6px">
            <span class="tag" :class="item.applied ? 'tag-review' : 'tag-study'">
              {{ item.applied ? '已应用' : `${item.point_count} 个知识点` }}
            </span>
            <span class="market-chevron">{{ isExpanded(item.slug) ? '▴' : '▾' }}</span>
          </div>
        </div>

        <div class="skill-line">{{ item.description }}</div>

        <div class="chip-list" style="margin-top: 10px">
          <button
            v-for="tag in item.tags"
            :key="tag"
            class="market-tag"
            :class="{ active: filterTag === tag }"
            @click.stop="toggleTag(tag)"
          >
            {{ tag }}
          </button>
        </div>

        <div v-if="!isExpanded(item.slug)" class="market-points">
          <button
            v-for="point in shortPoints(item)"
            :key="point.name"
            class="market-point"
            :class="{ owned: point.kp_id }"
            @click.stop="openPoint(item, point)"
          >
            {{ point.name }}
            <small v-if="point.mastery !== null">{{ Math.round(point.mastery * 100) }}%</small>
          </button>
          <button
            v-if="item.point_details.length > 6"
            class="market-point more"
            @click.stop="toggleExpand(item.slug)"
          >
            等 {{ item.point_count }} 个
          </button>
        </div>

        <div v-else class="stack" style="margin-top: 12px; gap: 10px">
          <div v-for="[parent, items] in grouped(item)" :key="parent" class="market-group">
            <button class="market-group-title" @click.stop="openModule(item, parent)">
              <span class="market-group-name">{{ parent }}</span>
              <span class="market-group-meta">
                {{ items.length }} 个知识点<template v-if="isVocabName(parent)"> · 单词卡</template>
                <span class="market-group-go">进入 ›</span>
              </span>
            </button>
            <div class="chip-list">
              <button
                v-for="point in items"
                :key="point.name"
                class="market-point"
                :class="{ owned: point.kp_id }"
                @click.stop="openPoint(item, point)"
              >
                {{ point.name }}
                <small v-if="point.mastery !== null">{{ Math.round(point.mastery * 100) }}%</small>
              </button>
            </div>
          </div>
        </div>

        <div class="row-between" style="margin-top: 14px">
          <button class="market-progress" @click.stop="toggleExpand(item.slug)">
            已覆盖 {{ item.applied_count }} / {{ item.point_count }}
            <span class="market-progress-arrow">{{ isExpanded(item.slug) ? '收起' : '展开' }}</span>
          </button>
          <button
            class="btn btn-sm"
            :class="{ 'btn-ghost': item.applied }"
            :disabled="applying === item.slug || item.applied"
            @click.stop="apply(item)"
          >
            {{ applying === item.slug ? '导入中...' : item.applied ? '已全部应用' : item.applied_count ? '补齐剩余' : '应用到当前目标' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="!loading && !visiblePackages.length" class="empty">
      当前筛选下没有学科包，点击「全部学科」查看所有包。
    </div>

    <div class="split">
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">学科包从哪里来</div>
            <div class="card-sub">这里只展示已通过审核、可以导入的学科包</div>
          </div>
          <button v-if="store.user?.campus_access" class="btn btn-sm" @click="router.push({ path: '/collab', query: { tab: 'packages' } })">
            去审核与上传
          </button>
        </div>
        <p class="small muted" style="margin-top: 12px; line-height: 1.8">
          常见课程已经整理好，可以直接应用到当前目标。教师提交的自定义包，需要审核通过并分享后才会出现在这里。
        </p>
      </div>

      <div class="card">
        <div class="card-title">导入之后会怎样</div>
        <div class="small muted" style="margin-top: 10px; line-height: 1.9">
          学科包提供知识结构。导入后，今日任务、随堂测和错题复盘都会按这些知识点安排。
        </div>
      </div>
    </div>

    <div v-if="detail" class="modal-mask" @click.self="detail = null">
      <div class="modal knowledge-modal">
        <div class="card-head">
          <div>
            <div class="card-title">{{ detail.point.name }}</div>
            <div class="card-sub">
              {{ detail.packageItem.name }} ·
              {{ detail.point.parent || '独立知识点' }} · 权重 {{ detail.point.weight }}
            </div>
          </div>
          <button class="btn btn-ghost btn-sm" @click="detail = null">关闭</button>
        </div>

        <template v-if="detail.point.kp_id">
          <div v-if="!practicing" class="stack">
            <div>
              <div class="row-between small">
                <span>当前掌握度</span>
                <b>{{ Math.round((detail.point.mastery || 0) * 100) }}%</b>
              </div>
              <div class="bar" style="margin-top: 6px">
                <i :style="{ width: Math.max((detail.point.mastery || 0) * 100, 2) + '%' }"></i>
              </div>
            </div>
            <div class="kv">
              <span>下次复习</span>
              <strong>{{ detail.point.next_review_at || '尚未安排' }}</strong>
            </div>
            <div class="kv">
              <span>复习规则</span>
              <strong>答对进入 1 / 2 / 4 / 7 / 15 天，答错回到 1 天</strong>
            </div>

            <div class="task-reason" style="margin-top: 14px">{{ recommendation }}</div>

            <div class="row" style="margin-top: 14px; flex-wrap: wrap; gap: 8px">
              <button v-if="isVocabName(detail.point.name)" class="btn btn-teal btn-sm" @click="openVocab(detail.point.kp_id, detail.point.name)">背单词</button>
              <button class="btn btn-teal btn-sm" @click="startPractice">出题练习</button>
              <button class="btn btn-sm" @click="startQuiz">随堂测 3 题</button>
              <button class="btn btn-ghost btn-sm" :disabled="marking" @click="mark(true)">我答对了</button>
              <button class="btn btn-ghost btn-sm" :disabled="marking" @click="mark(false)">我答错了</button>
              <button class="btn btn-ghost btn-sm" @click="go('/mistakes')">去错题本</button>
              <button class="btn btn-ghost btn-sm" @click="go('/plan')">看学习计划</button>
            </div>
          </div>

          <div v-else-if="practiceMode === 'probe'" class="stack">
            <div v-if="!practiceProbe" class="empty">AI 正在出题...</div>
            <div v-else-if="!practiceResult" class="stack">
              <div class="row-between">
                <span class="tag tag-study">主动探针</span>
                <span class="small muted">{{ practiceProbe.kp_name || detail.point.name }}</span>
              </div>
              <div class="probe-question">{{ practiceProbe.question }}</div>
              <div class="quiz-options">
                <button
                  v-for="(option, index) in practiceProbe.options"
                  :key="index"
                  class="quiz-option"
                  :class="{ active: practiceSelected === index }"
                  @click="practiceSelected = index"
                >
                  <span class="quiz-option-key">{{ String.fromCharCode(65 + index) }}</span>
                  <span>{{ option }}</span>
                </button>
              </div>
              <div class="row" style="margin-top: 10px">
                <button class="btn btn-sm" @click="submitPractice">提交答案</button>
                <button class="btn btn-ghost btn-sm" @click="resetPractice">返回</button>
              </div>
            </div>
            <div v-else class="stack">
              <div class="card-title">{{ practiceResult.correct ? '回答正确' : '发现一个盲区' }}</div>
              <div class="task-reason">{{ practiceResult.explanation || '暂无解析' }}</div>
              <div class="row" style="gap: 12px">
                <span v-if="practiceResult.mastery !== null && practiceResult.mastery !== undefined" class="small muted">掌握度 {{ Math.round(practiceResult.mastery * 100) }}%</span>
                <span class="small muted">韧性值 {{ practiceResult.resilience }}</span>
                <span class="small muted">{{ practiceResult.evidence }}</span>
              </div>
              <div class="row" style="margin-top: 10px">
                <button class="btn btn-teal btn-sm" @click="startPractice">再来一题</button>
                <button class="btn btn-ghost btn-sm" @click="resetPractice">返回详情</button>
              </div>
            </div>
          </div>

          <div v-else-if="practiceMode === 'quiz'" class="stack">
            <div v-if="!quizData" class="empty">AI 正在出题...</div>
            <div v-else-if="!quizResult" class="stack">
              <div class="small muted" style="margin-bottom: 4px">共 {{ quizData.questions.length }} 题，逐题作答后统一提交</div>
              <div v-for="(q, qi) in quizData.questions" :key="qi" class="probe-card">
                <div class="row-between">
                  <span class="tag tag-study">第 {{ qi + 1 }} 题</span>
                  <span class="small muted">{{ q.kp_name || detail.point.name }}</span>
                </div>
                <div class="probe-question">{{ q.question }}</div>
                <div v-if="q.source" class="small muted" style="margin-top: 6px">
                  题目来源：{{ q.source }}
                </div>
                <div class="quiz-options">
                  <button
                    v-for="(option, index) in q.options"
                    :key="index"
                    class="quiz-option"
                    :class="{ active: quizAnswers[qi] === index }"
                    @click="quizAnswers[qi] = index"
                  >
                    <span class="quiz-option-key">{{ String.fromCharCode(65 + index) }}</span>
                    <span>{{ option }}</span>
                  </button>
                </div>
              </div>
              <div class="row" style="margin-top: 10px">
                <button class="btn btn-sm" @click="submitQuizPractice">提交全部答案</button>
                <button class="btn btn-ghost btn-sm" @click="resetPractice">返回</button>
              </div>
            </div>
            <div v-else class="stack">
              <div class="card-title">随堂测完成：{{ quizResult.correct }} / {{ quizResult.total }} 正确</div>
              <div class="task-reason">得分 {{ quizResult.score }} 分 · 引擎 {{ quizResult.engine }}</div>
              <div v-if="quizResult.wrong.length" class="stack" style="margin-top: 10px">
                <div class="small muted">错题解析</div>
                <div v-for="(w, wi) in quizResult.wrong" :key="wi" class="probe-card">
                  <div class="row-between">
                    <span class="tag tag-skipped">第 {{ w.index + 1 }} 题</span>
                    <span class="small muted">{{ w.category_label }}</span>
                  </div>
                  <div class="probe-question">{{ w.question }}</div>
                  <div class="kv"><span>你的答案</span><strong style="color: #dc2626">{{ w.chosen }}</strong></div>
                  <div class="kv"><span>正确答案</span><strong style="color: #0d9488">{{ w.correct }}</strong></div>
                  <div class="task-reason">{{ w.explanation }}</div>
                </div>
              </div>
              <div v-else class="task-reason" style="margin-top: 10px">全部正确，掌握度已更新。</div>
              <div class="row" style="margin-top: 10px">
                <button class="btn btn-teal btn-sm" @click="startQuiz">再来一组</button>
                <button class="btn btn-ghost btn-sm" @click="resetPractice">返回详情</button>
              </div>
            </div>
          </div>
        </template>

        <template v-else>
          <div class="task-reason" style="margin-top: 14px">
            这个知识点还没有导入当前目标。应用整个学科包后，Planner 会按权重与临近系数把它排进每日任务。
          </div>
          <button
            class="btn btn-block"
            style="margin-top: 14px"
            :disabled="applying === detail.packageItem.slug"
            @click="apply(detail.packageItem)"
          >
            {{ applying === detail.packageItem.slug ? '导入中...' : `应用「${detail.packageItem.name}」` }}
          </button>
        </template>
      </div>
    </div>
    <div v-if="modulePanel" class="modal-mask" @click.self="modulePanel = null">
      <div class="modal module-modal">
        <div class="card-head">
          <div>
            <div class="card-title">{{ modulePanel.name }}</div>
            <div class="card-sub">
              {{ modulePanel.packageItem.name }} · {{ modulePanel.points.length }} 个知识点 ·
              平均掌握度
              {{ modulePanel.mastery === null || modulePanel.mastery === undefined ? '未导入' : Math.round(modulePanel.mastery * 100) + '%' }}
            </div>
          </div>
          <button class="btn btn-ghost btn-sm" @click="modulePanel = null">关闭</button>
        </div>

        <div class="module-points">
          <button
            v-for="point in modulePanel.points"
            :key="point.name"
            class="module-point"
            @click="openPoint(modulePanel.packageItem, point); modulePanel = null"
          >
            <span class="module-point-name">{{ point.name }}</span>
            <span class="module-point-meta">
              <template v-if="point.mastery !== null && point.mastery !== undefined">
                {{ Math.round(point.mastery * 100) }}%
              </template>
              <template v-else>未导入</template>
              <span class="module-point-go">›</span>
            </span>
          </button>
        </div>

        <div class="row" style="margin-top: 16px; gap: 8px; flex-wrap: wrap">
          <button
            v-if="isVocabName(modulePanel.name)"
            class="btn btn-teal btn-sm"
            @click="openVocab(modulePanel.kp_id, modulePanel.name)"
          >
            背单词
          </button>
          <button class="btn btn-sm" @click="startModuleQuiz">按模块出 3 题</button>
          <button class="btn btn-ghost btn-sm" @click="modulePanel = null">返回</button>
        </div>
        <div v-if="!modulePanel.kp_id" class="task-reason" style="margin-top: 12px">
          该模块还没有导入当前目标。先点「应用到当前目标」导入知识点，之后即可在这里出题或背单词。
        </div>
      </div>
    </div>

    <div v-if="createOpen" class="modal-mask" @click.self="createOpen = false">
      <div class="modal wizard-modal">
        <div class="card-head">
          <div>
            <div class="card-title">新增学科 Skill 包</div>
            <div class="card-sub">第 {{ createStep }} / 4 步 · 注册后即可在市场中一键应用</div>
          </div>
          <button class="btn btn-ghost btn-sm" @click="createOpen = false">关闭</button>
        </div>

        <div class="wizard-steps">
          <span v-for="step in 4" :key="step" class="wizard-step" :class="{ active: createStep === step, done: createStep > step }">
            {{ step }}
          </span>
        </div>

        <div v-if="createStep === 1" class="stack" style="margin-top: 6px">
          <div class="field">
            <label>学科包名称</label>
            <input v-model="draft.name" class="input" placeholder="例如：考研英语冲刺包" />
          </div>
          <div class="grid grid-2" style="gap: 12px">
            <div class="field">
              <label>学科</label>
              <input v-model="draft.subject" class="input" placeholder="英语 / 数学 / 网络" />
            </div>
            <div class="field">
              <label>标签（逗号分隔）</label>
              <input v-model="draft.tags" class="input" placeholder="考研, 英语一" />
            </div>
          </div>
          <div class="field">
            <label>简介</label>
            <textarea v-model="draft.description" class="textarea" placeholder="一句话说明这个包覆盖什么内容"></textarea>
          </div>
        </div>

        <div v-else-if="createStep === 2" class="stack" style="margin-top: 6px">
          <div class="row-between">
            <span class="small muted">每行一个模块，格式：模块: 知识点(权重), 知识点(权重)</span>
            <button class="btn btn-ghost btn-sm" @click="fillSample">插入示例</button>
          </div>
          <textarea
            v-model="draft.tree"
            class="textarea wizard-tree"
            placeholder="听力: 短对话(1.4), 长对话(1.5)&#10;阅读: 选词填空(1.4), 仔细阅读(1.9)"
          ></textarea>
          <div class="small muted">
            已识别 {{ draftModules }} 个模块、{{ draftLeaves }} 个子知识点（重复名称会自动去重）
          </div>
        </div>

        <div v-else-if="createStep === 3" class="stack" style="margin-top: 6px">
          <div class="wizard-summary">
            <div><b>{{ draft.name || '未命名' }}</b> · {{ draft.subject || '通用' }}</div>
            <div class="small muted">{{ draft.description || '暂无简介' }}</div>
            <div class="small muted">共 {{ draftPoints.length }} 个知识点，{{ draftModules }} 个模块</div>
          </div>
          <div class="module-points" style="max-height: 260px">
            <div v-for="module in draftPoints.filter((item) => !item.parent)" :key="module.name" class="wizard-preview">
              <div class="wizard-preview-title">{{ module.name }}</div>
              <div class="chip-list">
                <span
                  v-for="leaf in draftPoints.filter((item) => item.parent === module.name)"
                  :key="leaf.name"
                  class="market-point"
                >
                  {{ leaf.name }} <small>{{ leaf.weight }}</small>
                </span>
                <span v-if="!draftPoints.some((item) => item.parent === module.name)" class="small muted">
                  暂无子知识点
                </span>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="stack" style="margin-top: 6px">
          <div class="wizard-done">
            <div class="wizard-done-title">已注册「{{ createdPackage?.name }}」</div>
            <div class="small muted">
              slug {{ createdPackage?.slug }} · {{ createdPackage?.point_count }} 个知识点 ·
              已出现在市场列表，可直接应用到当前目标
            </div>
          </div>
          <div class="row" style="gap: 8px; flex-wrap: wrap">
            <button class="btn" :disabled="!createdPackage" @click="applyCreated">应用到当前目标</button>
            <button class="btn btn-ghost" @click="createOpen = false">稍后再用</button>
          </div>
        </div>

        <div class="row" style="justify-content: flex-end; gap: 8px; margin-top: 16px">
          <button v-if="createStep > 1 && createStep < 4" class="btn btn-ghost btn-sm" @click="createStep -= 1">
            上一步
          </button>
          <button v-if="createStep === 1" class="btn btn-sm" @click="nextStep">下一步</button>
          <button v-else-if="createStep === 2" class="btn btn-sm" @click="nextStep">预览</button>
          <button v-else-if="createStep === 3" class="btn btn-sm" :disabled="creating" @click="submitPackage">
            {{ creating ? '注册中...' : '注册学科包' }}
          </button>
        </div>
      </div>
    </div>

    <VocabLab
      v-if="vocabTarget"
      :goal-id="store.currentGoalId"
      :kp-id="vocabTarget.kpId"
      :title="vocabTarget.title"
      @close="vocabTarget = null"
      @finished="load"
    />

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">技能市场概览</div>
          <div class="card-sub">学科包、知识点规模与筛选结果</div>
        </div>
      </div>
      <div class="grid grid-4" style="margin-top: 10px">
        <div class="stat">
          <div class="stat-label">学科包</div>
          <div class="stat-value">{{ marketStats.total }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">知识点规模</div>
          <div class="stat-value">{{ marketStats.points }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">标签数</div>
          <div class="stat-value">{{ marketStats.tags }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">当前筛选</div>
          <div class="stat-value">{{ marketStats.shown }}</div>
          <div class="stat-note">{{ filterTag || '全部' }}</div>
        </div>
      </div>
    </div>
  </div>
</template>
