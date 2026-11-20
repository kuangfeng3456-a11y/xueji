<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { notify } from '../store'

const loading = ref(true)
const items = ref([])
const mineOnly = ref(false)
const creating = ref(false)
const shareCode = ref('')
const draft = reactive({
  name: '',
  subject: '通用',
  description: '',
  tags: '',
  tree: ''
})

const SAMPLE = `线性表: 顺序表(1.2), 链表(1.4)
查找: 二分查找(1.3)`

function parseTree(text) {
  const points = []
  const seen = new Set()
  function push(name, parent, weight) {
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

const draftCount = computed(() => parseTree(draft.tree).length)

async function load() {
  loading.value = true
  try {
    const data = await api.reviewSkillPackages(mineOnly.value)
    items.value = data.items || []
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function submitPackage() {
  const points = parseTree(draft.tree)
  if (draft.name.trim().length < 2 || !points.length) {
    notify('请填写名称，并至少写一个知识点', true)
    return
  }
  creating.value = true
  try {
    const created = await api.createSkillPackage({
      name: draft.name.trim(),
      subject: draft.subject.trim() || '通用',
      description: draft.description.trim(),
      tags: draft.tags.split(/[,，]/).map((item) => item.trim()).filter(Boolean),
      points
    })
    notify(`已提交「${created.name}」，等待审核`)
    draft.name = ''
    draft.description = ''
    draft.tags = ''
    draft.tree = ''
    mineOnly.value = false
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    creating.value = false
  }
}

async function review(item, action) {
  const note = action === 'approve' ? '审核通过，可以分享给学生' : '请补充知识点后再提交'
  try {
    await api.reviewSkillPackage(item.slug, { action, note })
    notify(action === 'approve' ? '已通过' : '已退回')
    await load()
  } catch (e) {
    notify(e.message, true)
  }
}

async function share(item) {
  try {
    const data = await api.shareSkillPackage(item.slug)
    shareCode.value = data.share_code
    notify(`已分享，学生可使用分享码 ${data.share_code}`)
    await load()
  } catch (e) {
    notify(e.message, true)
  }
}

function statusLabel(item) {
  if (item.status === 'rejected') return '已退回'
  if (item.status === 'approved' && item.shared) return '已分享，学生可导入'
  if (item.status === 'approved') return '已通过，尚未分享'
  return '待审核'
}

onMounted(load)
</script>

<template>
  <div class="stack">
    <div class="hero">
      <h1>学科包审核</h1>
      <p>教师可以提交自定义学科包。另一位教师或教务审核通过并分享后，学生才能在学科包里导入。学生主页不会出现审核操作。</p>
    </div>

    <div class="card">
      <div class="card-title">提交自定义包</div>
      <div class="stack" style="margin-top: 12px">
        <input v-model="draft.name" class="input" placeholder="名称，例如：课堂线性表" />
        <input v-model="draft.subject" class="input" placeholder="学科" />
        <input v-model="draft.description" class="input" placeholder="简要说明" />
        <input v-model="draft.tags" class="input" placeholder="标签，用逗号分开" />
        <textarea v-model="draft.tree" class="textarea" placeholder="每行一个模块：模块名: 知识点(权重), 知识点"></textarea>
        <div class="row">
          <button class="btn btn-ghost btn-sm" type="button" @click="draft.tree = SAMPLE">填入示例</button>
          <span class="small muted">已识别 {{ draftCount }} 个知识点</span>
          <button class="btn btn-sm" :disabled="creating" @click="submitPackage">
            {{ creating ? '提交中...' : '提交审核' }}
          </button>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div class="card-title">审核列表</div>
        <button class="btn btn-ghost btn-sm" @click="mineOnly = !mineOnly; load()">
          {{ mineOnly ? '查看全部' : '只看我提交的' }}
        </button>
      </div>
      <p v-if="shareCode" class="small">最近分享码：{{ shareCode }}。学生在学科包页面导入后即可使用。</p>
      <div v-if="loading" class="empty">正在读取...</div>
      <div v-else-if="!items.length" class="empty">还没有待处理的自定义包。</div>
      <div v-else class="stack" style="margin-top: 12px">
        <div v-for="item in items" :key="item.slug" class="card">
          <div class="row-between">
            <strong>{{ item.name }}</strong>
            <span class="tag">{{ statusLabel(item) }}</span>
          </div>
          <p class="small muted">{{ item.subject }} · {{ item.point_count }} 个知识点 · {{ item.author_name || '教师' }}</p>
          <p v-if="item.review_note" class="small">审核说明：{{ item.review_note }}</p>
          <p v-if="item.share_code" class="small">分享码 {{ item.share_code }}</p>
          <div class="row" style="margin-top: 8px">
            <button v-if="item.status === 'pending'" class="btn btn-sm" @click="review(item, 'approve')">通过</button>
            <button v-if="item.status === 'pending'" class="btn btn-ghost btn-sm" @click="review(item, 'reject')">退回</button>
            <button v-if="item.status === 'approved' && !item.shared" class="btn btn-sm" @click="share(item)">分享给学生</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
