<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'
import DetailModal from '../components/DetailModal.vue'

const kinds = ref([])
const contents = ref({})
const loading = ref(true)
const refreshing = ref('')
const refreshingAll = ref(false)
const detail = ref(null)
const showHistory = ref(false)
const recovery = ref(null)

async function loadRecovery() {
  if (!store.currentGoalId) return
  try {
    recovery.value = await api.fatigueInfo(store.currentGoalId)
  } catch (e) {
    recovery.value = null
  }
}

const icons = {
  hitokoto: '❝',
  poem: '❀',
  quote: '✦',
  joke: '☺',
  fact: '◎',
  wallpaper: '◧'
}

const sourceInfo = {
  hitokoto: { name: '一言', url: 'hitokoto.cn', desc: '随机一句话，来自动漫、文学、电影' },
  poem: { name: '今日诗词', url: 'jinrishici.com', desc: '每日一首古诗词，附带赏析' },
  quote: { name: '名言', url: 'zenquotes.io', desc: '英文名言，附带作者与出处' },
  joke: { name: '笑话', url: 'jokeapi.dev', desc: '中英文笑话，支持分类筛选' },
  fact: { name: '冷知识', url: 'uselessfacts.jsph.pl', desc: '有趣的冷知识，拓宽视野' },
  wallpaper: { name: '每日壁纸', url: 'bing.com', desc: 'Bing 每日高清壁纸' }
}

async function loadOne(kind) {
  try {
    contents.value = { ...contents.value, [kind]: await api.entertainmentContent(kind) }
  } catch (e) {
    contents.value = { ...contents.value, [kind]: { kind, status: 'error', error: e.message } }
  }
}

async function load() {
  loading.value = true
  try {
    const data = await api.entertainmentKinds()
    kinds.value = data.kinds
    for (const kind of kinds.value) {
      await loadOne(kind.key)
    }
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function refresh(kind) {
  refreshing.value = kind
  try {
    contents.value = { ...contents.value, [kind]: await api.entertainmentContent(kind, true) }
    notify('已从外部接口刷新')
  } catch (e) {
    notify(e.message, true)
  } finally {
    refreshing.value = ''
  }
}

async function refreshAll() {
  refreshingAll.value = true
  try {
    for (const kind of kinds.value) {
      await loadOne(kind.key)
    }
    notify('全部内容已从真实接口刷新')
  } finally {
    refreshingAll.value = false
  }
}

function openItem(item) {
  const info = sourceInfo[item.kind] || {}
  const extra = item.image
    ? [{ label: '图片地址', value: item.image }]
    : []
  detail.value = {
    title: item.name || info.name || '内容详情',
    subtitle: `${info.name || item.kind} · ${item.source || info.name || '外部接口'} · ${item.fetched_at || ''}`,
    rows: [
      { label: '内容', value: item.content || '—' },
      ...(item.author ? [{ label: '作者', value: item.author }] : []),
      { label: '数据来源', value: `${info.name}（${info.url}）` },
      { label: '获取方式', value: '真实外部网络接口' },
      { label: '接口说明', value: info.desc },
      ...extra
    ]
  }
}

const availableCount = computed(() => {
  return Object.values(contents.value).filter(c => c && c.status !== 'error').length
})

const errorCount = computed(() => {
  return Object.values(contents.value).filter(c => c && c.status === 'error').length
})

onMounted(() => {
  load()
  loadRecovery()
})
</script>

<template>
  <div class="stack">
    <div class="hero">
      <h1>娱乐放松 · 真实联网内容</h1>
      <p>
        学习间隙也需要喘口气。这里的一言、诗词、名言、笑话、冷知识和每日壁纸来自公开内容源，点击卡片即可查看完整内容与来源。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ kinds.length }}</strong>
          <span>内容源</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ availableCount }}</strong>
          <span>当前可用</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ errorCount }}</strong>
          <span>暂时不可用</span>
        </div>
        <div class="hero-meta-item">
          <strong>6</strong>
          <span>真实外部接口</span>
        </div>
        <div class="hero-meta-item">
          <strong>5min</strong>
          <span>内容缓存</span>
        </div>
      </div>
    </div>

    <div class="row-between">
      <div class="small muted">
        内容来自 hitokoto.cn、jinrishici.com、zenquotes.io、jokeapi.dev、uselessfacts.jsph.pl、bing.com
      </div>
      <button class="btn" :disabled="refreshingAll" @click="refreshAll">
        {{ refreshingAll ? '正在逐个刷新...' : '全部刷新' }}
      </button>
    </div>

    <div v-if="loading" class="empty">正在并发请求外部内容源...</div>

    <div v-else class="grid grid-3">
      <div
        v-for="kind in kinds"
        :key="kind.key"
        class="card click-card fun-card"
        role="button"
        tabindex="0"
        @click="contents[kind.key]?.status !== 'error' && openItem(contents[kind.key])"
        @keydown.enter.prevent="contents[kind.key]?.status !== 'error' && openItem(contents[kind.key])"
        @keydown.space.prevent="contents[kind.key]?.status !== 'error' && openItem(contents[kind.key])"
      >
        <div class="row-between">
          <div class="fun-icon">{{ icons[kind.key] || '·' }}</div>
          <span class="tag tag-study">{{ kind.source }}</span>
        </div>
        <div class="card-title" style="margin-top: 10px">{{ kind.name }}</div>
        <div class="card-sub">{{ kind.desc }}</div>

        <div v-if="contents[kind.key]?.status === 'error'" class="fun-error">
          外部接口暂不可用：{{ contents[kind.key].error }}
        </div>
        <template v-else-if="contents[kind.key]">
          <img
            v-if="contents[kind.key].image"
            :src="contents[kind.key].image"
            alt="每日壁纸"
            class="fun-wallpaper"
          />
          <div class="fun-content">{{ contents[kind.key].content || '—' }}</div>
          <div v-if="contents[kind.key].author" class="small muted">— {{ contents[kind.key].author }}</div>
        </template>
        <div v-else class="empty" style="padding: 12px">加载中...</div>

        <div class="row" style="margin-top: 12px">
          <button class="btn btn-ghost btn-sm" :disabled="refreshing === kind.key" @click.stop="refresh(kind.key)">
            {{ refreshing === kind.key ? '刷新中...' : '换一条' }}
          </button>
          <span class="small muted">{{ contents[kind.key]?.cached ? '来自缓存' : '实时获取' }}</span>
        </div>
        <div class="click-hint"><span>查看完整内容与来源</span><span>→</span></div>
      </div>
    </div>

    <div v-if="recovery && recovery.fatigue.index >= 60" class="card">
      <div class="card-head">
        <div>
          <div class="card-title">恢复站（疲劳触发）</div>
          <div class="card-sub">疲劳指数 {{ recovery.fatigue.index }}（{{ recovery.fatigue.level }}）· 建议先恢复再学习</div>
        </div>
        <span class="tag tag-time">5 分钟恢复</span>
      </div>
      <div class="stack" style="margin-top: 10px">
        <div class="task-reason">{{ recovery.fatigue.suggestion }}</div>
        <div class="grid grid-3" style="gap: 10px">
          <div class="stat">
            <div class="stat-label">呼吸</div>
            <div class="stat-value" style="font-size: 14px">4-7-8 呼吸 3 轮</div>
          </div>
          <div class="stat">
            <div class="stat-label">拉伸</div>
            <div class="stat-value" style="font-size: 14px">肩颈 2 分钟</div>
          </div>
          <div class="stat">
            <div class="stat-label">一句诗词</div>
            <div class="stat-value" style="font-size: 14px">看下方诗词放松</div>
          </div>
        </div>
      </div>
    </div>
    <div v-else-if="recovery" class="card">
      <div class="card-head">
        <div>
          <div class="card-title">恢复站</div>
          <div class="card-sub">疲劳指数 {{ recovery.fatigue.index }}（{{ recovery.fatigue.level }}）· 当前无需强制恢复</div>
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