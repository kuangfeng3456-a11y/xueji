<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { store, notify, setGoal, syncGoalSelection, currentGoal } from '../store'
import { confirmAction } from '../confirm'
import DetailModal from '../components/DetailModal.vue'

const router = useRouter()
const detail = ref(null)

function openPoint(point) {
  detail.value = {
    title: point.name,
    subtitle: point.depth === 0 ? '一级模块' : '子知识点',
    rows: [
      { label: '权重', value: String(point.weight) },
      { label: '当前掌握度', value: `${Math.round((point.mastery || 0) * 100)}%` },
      { label: '层级', value: point.depth === 0 ? '模块' : `第 ${point.depth + 1} 层` }
    ],
    linkTo: '/knowledge-map',
    linkText: '查看知识漏洞地图'
  }
}

function openMaterial(item) {
  detail.value = {
    title: item.filename,
    subtitle: '已导入资料',
    rows: [
      { label: '导入时间', value: item.created_at.slice(0, 10) },
      { label: '用途', value: '用于抽取知识点、生成计划与时效检查。' }
    ],
    linkTo: '/freshness',
    linkText: '检查资料时效'
  }
}
const points = ref([])
const materials = ref([])
const loading = ref(false)
const saving = ref(false)
const importing = ref(false)
const editingId = ref(null)
const fileInput = ref(null)
const today = new Date().toISOString().slice(0, 10)

const form = reactive({
  exam_name: '',
  exam_date: '',
  daily_minutes: 90,
  force_mode: false,
  min_daily_minutes: 30,
  camera_required: false
})

const material = reactive({
  filename: '我的学习资料',
  content: ''
})

const orderedPoints = computed(() => {
  const parents = points.value.filter((p) => !p.parent_id)
  const result = []
  const used = new Set()
  for (const parent of parents) {
    result.push({ ...parent, depth: 0 })
    used.add(parent.id)
    for (const child of points.value.filter((p) => p.parent_id === parent.id)) {
      result.push({ ...child, depth: 1 })
      used.add(child.id)
    }
  }
  for (const item of points.value) {
    if (!used.has(item.id)) result.push({ ...item, depth: 0 })
  }
  return result
})

function resetForm() {
  form.exam_name = ''
  form.exam_date = ''
  form.daily_minutes = 90
  form.force_mode = false
  form.min_daily_minutes = 30
  form.camera_required = false
  editingId.value = null
}

async function refreshGoals() {
  store.goals = await api.goals()
  syncGoalSelection()
}

async function loadPoints() {
  if (!store.currentGoalId) return
  if (!store.currentGoalId) {
    points.value = []
    materials.value = []
    return
  }
  loading.value = true
  try {
    const [kp, mats] = await Promise.all([
      api.knowledgePoints(store.currentGoalId),
      api.materials(store.currentGoalId)
    ])
    points.value = kp
    materials.value = mats
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function saveGoal() {
  if (!form.exam_name.trim() || !form.exam_date) {
    notify('请填写考试名称和考试日期', true)
    return
  }
  saving.value = true
  try {
    const payload = {
      exam_name: form.exam_name.trim(),
      exam_date: form.exam_date,
      daily_minutes: Number(form.daily_minutes),
      force_mode: Boolean(form.force_mode),
      min_daily_minutes: Number(form.min_daily_minutes),
      camera_required: Boolean(form.camera_required)
    }
    if (editingId.value) {
      await api.updateGoal(editingId.value, payload)
      notify('目标已更新')
    } else {
      const goal = await api.createGoal(payload)
      setGoal(goal.id)
      notify('目标已创建。下一步导入资料或选择学科包，才能排出今天的课。')
    }
    await refreshGoals()
    resetForm()
    await loadPoints()
  } catch (e) {
    notify(e.message, true)
  } finally {
    saving.value = false
  }
}

function editGoal(goal) {
  editingId.value = goal.id
  form.exam_name = goal.exam_name
  form.exam_date = goal.exam_date
  form.daily_minutes = goal.daily_minutes
  form.force_mode = Boolean(goal.force_mode)
  form.min_daily_minutes = goal.min_daily_minutes || 30
  form.camera_required = Boolean(goal.camera_required)
}

async function removeGoal(goal) {
  const ok = await confirmAction({
    title: '删除考试目标',
    message: `删除「${goal.exam_name}」？`,
    detail: '该目标下的知识点、任务、错题与周报会一并删除，且不可恢复。',
    confirmText: '删除目标',
    danger: true
  })
  if (!ok) return
  try {
    await api.deleteGoal(goal.id)
    notify('目标已删除')
    await refreshGoals()
    await loadPoints()
  } catch (e) {
    notify(e.message, true)
  }
}

async function importText() {
  if (!store.currentGoalId) {
    notify('请先创建目标', true)
    return
  }
  if (!material.content.trim()) {
    notify('请先粘贴资料内容', true)
    return
  }
  importing.value = true
  try {
    const created = await api.importText(store.currentGoalId, {
      filename: material.filename || '粘贴的资料',
      content: material.content
    })
    notify(`已抽取 ${created.length} 个知识点`)
    material.content = ''
    await loadPoints()
    await refreshGoals()
  } catch (e) {
    notify(e.message, true)
  } finally {
    importing.value = false
  }
}

async function importFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  if (!store.currentGoalId) {
    notify('请先创建目标', true)
    return
  }
  importing.value = true
  try {
    const data = new FormData()
    data.append('file', file)
    const created = await api.importFile(store.currentGoalId, data)
    notify(`已从 ${file.name} 抽取 ${created.length} 个知识点`)
    await loadPoints()
    await refreshGoals()
  } catch (e) {
    notify(e.message, true)
  } finally {
    importing.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

async function removePoint(point) {
  const ok = await confirmAction({
    title: '删除知识点',
    message: `删除知识点「${point.name}」？`,
    detail: '该知识点的掌握度、关联任务与错题记录会一并清理。',
    confirmText: '删除',
    danger: true
  })
  if (!ok) return
  try {
    await api.deleteKnowledgePoint(store.currentGoalId, point.id)
    notify('知识点已删除')
    await loadPoints()
  } catch (e) {
    notify(e.message, true)
  }
}

watch(() => store.currentGoalId, loadPoints, { immediate: true })

const setupStats = computed(() => {
  const current = store.goals.find((item) => item.id === store.currentGoalId)
  const daysLeft =
    current && current.exam_date
      ? Math.max(0, Math.round((new Date(current.exam_date) - Date.now()) / 86400000))
      : 0
  return {
    goals: store.goals.length,
    points: points.value.length,
    materials: materials.value.length,
    daysLeft
  }
})
</script>

<template>
  <div class="stack">
    <div v-if="!store.goals.length" class="card goal-promise">
      <div class="card-sub">开始使用</div>
      <h2>先告诉学迹，你在为哪一场考试准备</h2>
      <p>只需考试名称、日期和每天能学多久。之后导入资料或选学科包，就能生成今天的课和练习。</p>
    </div>
    <div class="split">
      <div class="stack">
        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">{{ editingId ? '编辑考试目标' : '新建考试目标' }}</div>
              <div class="card-sub">这三项就够开始：考什么、何时考、每天能投入多久</div>
            </div>
            <button v-if="editingId" class="btn btn-ghost btn-sm" @click="resetForm">取消编辑</button>
          </div>

          <div class="field">
            <label>考试名称</label>
            <input v-model.trim="form.exam_name" class="input" placeholder="例如：大学英语四级、考研数学、HCIA-Datacom" />
          </div>
          <div class="grid grid-2" style="gap: 12px">
            <div class="field">
              <label>考试日期</label>
              <input v-model="form.exam_date" class="input" type="date" :min="today" />
            </div>
            <div class="field">
              <label>每日可用分钟</label>
              <input v-model.number="form.daily_minutes" class="input" type="number" min="20" max="600" step="10" />
            </div>
          </div>

          <div class="policy-box">
            <div class="policy-title">强制学习策略</div>
            <label class="switch-row">
              <input v-model="form.force_mode" type="checkbox" />
              <span>
                <b>强制模式</b>
                <small>任务不可跳过；离开专注页面、专注不足 60% 都会记违约</small>
              </span>
            </label>
            <label class="switch-row">
              <input v-model="form.camera_required" type="checkbox" />
              <span>
                <b>摄像头监督</b>
                <small>开始强制学习前必须开启摄像头，每 60 秒抓拍一次学习见证</small>
              </span>
            </label>
            <div v-if="form.force_mode" class="field" style="margin: 10px 0 0">
              <label>每日最低专注分钟</label>
              <input v-model.number="form.min_daily_minutes" class="input" type="number" min="10" max="300" step="5" />
            </div>
          </div>

          <button class="btn btn-block" :disabled="saving" @click="saveGoal">
            {{ saving ? '保存中...' : editingId ? '保存修改' : '创建目标' }}
          </button>
        </div>

        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">已有目标</div>
              <div class="card-sub">切换目标后，其他页面会同步刷新</div>
            </div>
          </div>
          <div v-if="!store.goals.length" class="empty">还没有目标，先创建一个。</div>
          <div v-else class="stack">
            <div
              v-for="goal in store.goals"
              :key="goal.id"
              class="task"
              :style="{ borderColor: goal.id === store.currentGoalId ? '#93c5fd' : '' }"
            >
              <div class="task-main">
                <div class="task-title">
                  {{ goal.exam_name }}
                  <span v-if="goal.id === store.currentGoalId" class="tag tag-review">当前</span>
                </div>
                <div class="task-meta small muted">
                  考试 {{ goal.exam_date }} · 剩 {{ goal.days_left }} 天 · 每天 {{ goal.daily_minutes }} 分钟 ·
                  {{ goal.knowledge_count }} 个知识点
                </div>
              </div>
              <div class="task-actions">
                <button v-if="goal.id !== store.currentGoalId" class="btn btn-ghost btn-sm" @click="setGoal(goal.id)">
                  切换
                </button>
                <button class="btn btn-ghost btn-sm" @click="editGoal(goal)">编辑</button>
                <button class="btn btn-danger btn-sm" @click="removeGoal(goal)">删除</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="stack">
        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">导入学习资料</div>
              <div class="card-sub">支持 txt / md / csv / docx / pdf</div>
            </div>
          </div>

          <div class="field">
            <label>资料名称</label>
            <input v-model.trim="material.filename" class="input" placeholder="例如：四级高频词汇" />
          </div>
          <div class="field">
            <label>粘贴资料内容</label>
            <textarea
              v-model="material.content"
              class="textarea"
              style="min-height: 150px"
              placeholder="# 听力&#10;- 短对话&#10;- 长对话&#10;- 听力篇章&#10;&#10;# 阅读&#10;- 选词填空&#10;- 仔细阅读"
            ></textarea>
          </div>
          <button class="btn btn-teal btn-block" :disabled="importing || !store.currentGoalId" @click="importText">
            {{ importing ? '抽取知识点中...' : '解析并生成知识点树' }}
          </button>

          <div style="margin-top: 12px; border-top: 1px dashed var(--line); padding-top: 12px">
            <label class="small" style="font-weight: 600">或上传文件</label>
            <input ref="fileInput" type="file" accept=".txt,.md,.csv,.docx,.pdf" style="margin-top: 8px; font-size: 12px" @change="importFile" />
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">知识点树</div>
              <div class="card-sub">共 {{ points.length }} 个，父节点用于组织，任务只排到叶子节点</div>
            </div>
          </div>
          <div v-if="loading" class="empty">加载中...</div>
          <div v-else-if="!points.length" class="empty">还没有知识点。粘贴带层级的大纲，或上传资料。</div>
          <div v-else class="stack">
            <div
              v-for="point in orderedPoints"
              :key="point.id"
              class="row-between click-line"
              style="border-radius: 10px"
              :style="{ paddingLeft: (point.depth * 18 + 8) + 'px', paddingRight: '8px' }"
              role="button"
              tabindex="0"
              @click="openPoint(point)"
              @keydown.enter.prevent="openPoint(point)"
              @keydown.space.prevent="openPoint(point)"
            >
              <div style="min-width: 0">
                <div class="small" style="font-weight: point.depth === 0 ? 700 : 400">
                  {{ point.depth === 0 ? '▸ ' : '· ' }}{{ point.name }}
                </div>
                <div class="small muted">权重 {{ point.weight }} · 掌握度 {{ Math.round(point.mastery * 100) }}%</div>
              </div>
              <button class="btn btn-ghost btn-sm" @click="removePoint(point)">删除</button>
            </div>
          </div>
        </div>

        <div class="card" v-if="materials.length">
          <div class="card-title">已导入资料</div>
          <div class="stack" style="margin-top: 10px">
            <div v-for="item in materials" :key="item.id" class="kv click-line" style="padding: 6px; border-radius: 8px" role="button" tabindex="0" @click="openMaterial(item)" @keydown.enter.prevent="openMaterial(item)" @keydown.space.prevent="openMaterial(item)">
              <span>{{ item.filename }}</span>
              <strong>{{ item.created_at.slice(0, 10) }}</strong>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">数据与隐私</div>
          <div class="card-sub">只收集必要的学习数据，随时可导出或删除</div>
        </div>
      </div>
      <div class="row-between">
        <div class="small muted">只收集必要的学习数据，随时可导出或删除。</div>
        <router-link class="btn btn-ghost btn-sm" to="/settings?tab=account">去账号与安全</router-link>
      </div>
    </div>

    <div class="card">
      <div class="row-between">
        <div class="small muted">
          完成目标与知识点设置后，前往「学习计划」生成每日任务。
        </div>
        <button class="btn" @click="router.push('/plan')">去生成计划</button>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">目标与资料概览</div>
          <div class="card-sub">多目标、知识点与资料的整体状态</div>
        </div>
      </div>
      <div class="grid grid-4" style="margin-top: 10px">
        <div class="stat">
          <div class="stat-label">目标数</div>
          <div class="stat-value">{{ setupStats.goals }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">知识点</div>
          <div class="stat-value">{{ setupStats.points }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">资料数</div>
          <div class="stat-value">{{ setupStats.materials }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">距考试</div>
          <div class="stat-value">{{ setupStats.daysLeft }}<span style="font-size: 13px"> 天</span></div>
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