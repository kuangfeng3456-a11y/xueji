<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'

const loading = ref(true)
const materials = ref([])
const query = ref('')
const results = ref([])
const searching = ref(false)
const reindexing = ref(false)
const lastMessage = ref('')

const totalChars = computed(() =>
  materials.value.reduce((sum, item) => sum + (item.content ? item.content.length : 0), 0)
)

async function load() {
  if (!store.currentGoalId) return
  if (!store.currentGoalId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    materials.value = await api.materials(store.currentGoalId)
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function search() {
  const term = query.value.trim()
  if (!term) {
    notify('请输入检索关键词', true)
    return
  }
  searching.value = true
  results.value = []
  try {
    const data = await api.ragSearch(store.currentGoalId, term, 5)
    results.value = data.results || []
    lastMessage.value = data.found ? '' : '未检索到可靠来源，不编造引用。'
    if (!data.found) notify(lastMessage.value, true)
  } catch (e) {
    notify(e.message, true)
  } finally {
    searching.value = false
  }
}

async function reindex() {
  reindexing.value = true
  try {
    const data = await api.ragReindex(store.currentGoalId)
    notify(`已重建索引：${data.materials} 份资料、${data.chunks} 个片段`)
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    reindexing.value = false
  }
}

watch(() => store.currentGoalId, load, { immediate: true })
onMounted(load)
</script>

<template>
  <div v-if="!store.currentGoalId" class="empty">
    还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建目标。
  </div>

  <div v-else class="stack">
    <div class="hero">
      <h1>可信资料库（RAG）</h1>
      <p>
        对你有权使用的资料切块建索引，回答时给出文件名与段落定位；检索不到可靠来源时明确说明证据不足，
        不编造引用。上传资料后会自动切块，也可手动重建索引。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ materials.length }}</strong>
          <span>已导入资料</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ totalChars }}</strong>
          <span>资料字符数</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ results.length }}</strong>
          <span>本次命中片段</span>
        </div>
        <div class="hero-meta-item">
          <strong>段落</strong>
          <span>引用定位单位</span>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">资料检索</div>
          <div class="card-sub">输入关键词，返回文件名、段落序号与相关度</div>
        </div>
        <button class="btn btn-ghost btn-sm" :disabled="reindexing" @click="reindex">
          {{ reindexing ? '重建中...' : '重建索引' }}
        </button>
      </div>
      <div class="row" style="gap: 8px; margin-top: 10px">
        <input v-model="query" class="input" placeholder="例如：听力主旨、导数定义、404" style="flex: 1" @keyup.enter="search" />
        <button class="btn" :disabled="searching" @click="search">{{ searching ? '检索中...' : '检索' }}</button>
      </div>
      <div v-if="results.length" class="stack" style="margin-top: 12px">
        <div v-for="(item, index) in results" :key="index" class="gap-row">
          <div>
            <b>{{ item.filename }}</b>
            <div class="small muted">第 {{ item.chunk_index + 1 }} 段 · 相关度 {{ Math.round(item.score * 100) }}%</div>
            <div class="small" style="margin-top: 4px">{{ item.snippet }}</div>
          </div>
          <span class="tag tag-study">{{ item.page_no ? 'P' + item.page_no : '段落' }}</span>
        </div>
      </div>
      <div v-else-if="lastMessage" class="empty" style="margin-top: 12px">{{ lastMessage }}</div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">已导入资料</div>
          <div class="card-sub">上传入口在「目标与资料」，支持 txt / md / csv / docx / pdf</div>
        </div>
        <router-link class="btn btn-ghost btn-sm" to="/goal">去导入资料</router-link>
      </div>
      <div v-if="loading" class="empty" style="margin-top: 10px">加载中...</div>
      <div v-else-if="!materials.length" class="empty" style="margin-top: 10px">还没有资料。</div>
      <div v-else class="stack" style="margin-top: 10px">
        <div v-for="item in materials" :key="item.id" class="kv">
          <span>{{ item.filename }}</span>
          <strong>{{ item.created_at ? item.created_at.slice(0, 16).replace('T', ' ') : '—' }}</strong>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">引用规则</div>
      <div class="stack" style="margin-top: 10px">
        <div class="kv"><span>切块</span><strong>按段落与长度切块，每块保留段落序号</strong></div>
        <div class="kv"><span>检索</span><strong>词面 2-gram 匹配，返回相关度与片段</strong></div>
        <div class="kv"><span>可信</span><strong>检索不到可靠来源时明确说明，不编造引用</strong></div>
        <div class="kv"><span>隐私</span><strong>仅检索当前用户、当前目标下的资料</strong></div>
      </div>
    </div>

  </div>
</template>