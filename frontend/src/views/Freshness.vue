<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'
import DetailModal from '../components/DetailModal.vue'

const loading = ref(true)
const scanning = ref(false)
const data = ref({ items: [], overall: 0, scanned_at: null })
const history = ref([])
const detail = ref(null)
const showHistory = ref(false)

function openItem(item) {
  detail.value = {
    title: item.filename,
    subtitle: `时效评分 ${item.score} / 100 · ${levelLabel[item.level] || '未知'}`,
    rows: [
      { label: '时效评分', value: `${item.score} / 100` },
      { label: '评估方式', value: item.engine === 'llm' ? 'DeepSeek 语义评估' : '规则扫描' },
      { label: '发现问题', value: item.issues.length ? item.issues.join('；') : '暂未发现明显过时问题' },
      { label: '补资料建议', value: item.suggestion || '暂无' },
      { label: '检查时间', value: item.checked_at || data.value.scanned_at || '—' }
    ],
    linkTo: '/goal',
    linkText: '去更新资料'
  }
}

function openHistoryItem(item) {
  detail.value = {
    title: item.filename,
    subtitle: `历史扫描 · ${item.checked_at || ''}`,
    rows: [
      { label: '时效评分', value: `${item.score} / 100` },
      { label: '评估方式', value: item.engine === 'llm' ? 'DeepSeek 语义评估' : '规则扫描' },
      { label: '发现问题', value: item.issues.length ? item.issues.join('；') : '暂未发现明显过时问题' },
      { label: '补资料建议', value: item.suggestion || '暂无' }
    ],
    linkTo: '/goal',
    linkText: '去更新资料'
  }
}

const levelLabel = { fresh: '时效良好', warning: '需要关注', stale: '可能过时', unknown: '未知' }
const levelClass = { fresh: 'tag-review', warning: 'tag-time', stale: 'tag-skipped', unknown: 'tag-pending' }
const staleCount = computed(() => data.value.items.filter((item) => item.level === 'stale').length)
const warningCount = computed(() => data.value.items.filter((item) => item.level === 'warning').length)
const freshCount = computed(() => data.value.items.filter((item) => item.level === 'fresh').length)
const avgScore = computed(() => {
  if (!data.value.items.length) return 0
  return Math.round(data.value.items.reduce((sum, item) => sum + item.score, 0) / data.value.items.length)
})

const scoreDistribution = computed(() => {
  const dist = { excellent: 0, good: 0, warning: 0, stale: 0 }
  for (const item of data.value.items) {
    if (item.score >= 80) dist.excellent += 1
    else if (item.score >= 60) dist.good += 1
    else if (item.score >= 40) dist.warning += 1
    else dist.stale += 1
  }
  return dist
})

async function load() {
  if (!store.currentGoalId) return
  if (!store.currentGoalId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const [freshnessData, historyData] = await Promise.all([
      api.freshness(store.currentGoalId),
      api.freshnessHistory(store.currentGoalId)
    ])
    data.value = freshnessData
    history.value = historyData.history || []
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function scan() {
  scanning.value = true
  try {
    data.value = await api.freshnessScan(store.currentGoalId)
    notify(`时效扫描完成：${data.value.items.length} 份资料，发现 ${staleCount.value} 份可能过时`)
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    scanning.value = false
  }
}

watch(() => store.currentGoalId, load, { immediate: true })
onMounted(() => {})
</script>

<template>
  <div v-if="!store.currentGoalId" class="empty">
    还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建目标。
  </div>

  <div v-else class="stack">
    <div class="hero">
      <h1>学习内容时效雷达</h1>
      <p>
        学错内容比不学更危险。系统读取你导入的资料，由 DeepSeek 对照当前年份与考试名称评估时效，
        标出可能缺少的新题型、大纲变化与内容缺口，并给出补资料建议。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ data.overall }}</strong>
          <span>总体时效分</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ data.items.length }}</strong>
          <span>已扫描资料</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ staleCount }}</strong>
          <span>可能过时</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ warningCount }}</strong>
          <span>需要关注</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ freshCount }}</strong>
          <span>时效良好</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ data.scanned_at ? data.scanned_at.slice(0, 10) : '—' }}</strong>
          <span>最近扫描</span>
        </div>
      </div>
    </div>

    <div class="row-between">
      <div class="small muted">
        评估维度：资料年份、考纲对照、内容完整度与近期题型覆盖。
      </div>
      <div class="row">
        <button class="btn btn-ghost btn-sm" :aria-pressed="!showHistory" @click="showHistory = false">当前扫描</button>
        <button class="btn btn-ghost btn-sm" :aria-pressed="showHistory" @click="showHistory = true">历史记录</button>
        <button class="btn" :disabled="scanning" @click="scan">
          {{ scanning ? 'AI 扫描中...' : '扫描全部资料' }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="empty">正在读取时效报告...</div>

    <div v-else-if="showHistory" class="stack">
      <div v-if="!history.length" class="card">
        <div class="empty">还没有历史扫描记录。点击「扫描全部资料」开始第一次扫描。</div>
      </div>
      <div v-else class="stack">
        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">扫描历史</div>
              <div class="card-sub">共 {{ history.length }} 条历史记录，按时间倒序排列</div>
            </div>
          </div>
          <div v-if="!history.length" class="empty">暂无历史记录。</div>
          <div v-else class="stack" style="margin-top: 10px">
            <div
              v-for="(item, index) in history"
              :key="index"
              class="freshness-card click-card"
              role="button"
              tabindex="0"
              @click="openHistoryItem(item)"
              @keydown.enter.prevent="openHistoryItem(item)"
              @keydown.space.prevent="openHistoryItem(item)"
            >
              <div class="row-between">
                <div>
                  <div class="card-title" style="font-size: 14px">{{ item.filename }}</div>
                  <div class="small muted">{{ item.checked_at || '—' }}</div>
                </div>
                <span class="tag" :class="levelClass[item.level]">{{ levelLabel[item.level] }}</span>
              </div>
              <div class="row-between" style="margin-top: 8px">
                <span class="small">评分 {{ item.score }} / 100</span>
                <span class="small muted">{{ item.engine === 'llm' ? 'DeepSeek' : '规则扫描' }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="!data.items.length" class="card">
      <div class="empty">
        还没有资料或尚未扫描。先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 导入资料，
        再点击右上角「扫描全部资料」。
      </div>
    </div>

    <div v-else class="split">
      <div class="stack">
        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">时效评分分布</div>
              <div class="card-sub">按分数段统计资料时效状态</div>
            </div>
          </div>
          <div class="grid grid-2" style="gap: 10px; margin-top: 10px">
            <div class="stat" style="background: #ecfdf5">
              <div class="stat-label">优秀 (≥80)</div>
              <div class="stat-value" style="color: #059669">{{ scoreDistribution.excellent }}</div>
              <div class="bar" style="margin-top: 6px"><i :style="{ width: data.items.length ? (scoreDistribution.excellent / data.items.length * 100) + '%' : '0%' }" style="background: #059669"></i></div>
            </div>
            <div class="stat" style="background: #eff6ff">
              <div class="stat-label">良好 (60-79)</div>
              <div class="stat-value" style="color: #2563eb">{{ scoreDistribution.good }}</div>
              <div class="bar" style="margin-top: 6px"><i :style="{ width: data.items.length ? (scoreDistribution.good / data.items.length * 100) + '%' : '0%' }" style="background: #2563eb"></i></div>
            </div>
            <div class="stat" style="background: #fffbeb">
              <div class="stat-label">警告 (40-59)</div>
              <div class="stat-value" style="color: #d97706">{{ scoreDistribution.warning }}</div>
              <div class="bar" style="margin-top: 6px"><i :style="{ width: data.items.length ? (scoreDistribution.warning / data.items.length * 100) + '%' : '0%' }" style="background: #d97706"></i></div>
            </div>
            <div class="stat" style="background: #fef2f2">
              <div class="stat-label">过时 (&lt;40)</div>
              <div class="stat-value" style="color: #dc2626">{{ scoreDistribution.stale }}</div>
              <div class="bar" style="margin-top: 6px"><i :style="{ width: data.items.length ? (scoreDistribution.stale / data.items.length * 100) + '%' : '0%' }" style="background: #dc2626"></i></div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">平均时效分</div>
              <div class="card-sub">所有资料评分的算术平均</div>
            </div>
            <span class="tag" :class="avgScore >= 80 ? 'tag-review' : avgScore >= 60 ? 'tag-time' : 'tag-skipped'">{{ avgScore }} 分</span>
          </div>
          <div class="bar" style="margin-top: 10px; height: 24px"><i :style="{ width: avgScore + '%' }"></i></div>
          <div class="small muted" style="margin-top: 6px">
            {{ avgScore >= 80 ? '资料整体时效良好，继续保持。' : avgScore >= 60 ? '部分资料需要关注，建议补充最新内容。' : '资料时效风险较高，建议尽快更新。' }}
          </div>
        </div>
      </div>

      <div class="stack">
        <div
          v-for="item in data.items"
          :key="item.material_id"
          class="card freshness-card click-card"
          role="button"
          tabindex="0"
          @click="openItem(item)"
          @keydown.enter.prevent="openItem(item)"
          @keydown.space.prevent="openItem(item)"
        >
          <div class="card-head">
            <div>
              <div class="card-title">{{ item.filename }}</div>
              <div class="card-sub">时效评分 {{ item.score }} / 100 · 由 {{ item.engine === 'llm' ? 'DeepSeek' : '规则扫描' }} 评估</div>
            </div>
            <span class="tag" :class="levelClass[item.level]">{{ levelLabel[item.level] }}</span>
          </div>
          <div class="bar" style="margin-bottom: 12px"><i :style="{ width: item.score + '%' }"></i></div>
          <div v-if="item.issues.length" class="stack" style="gap: 6px">
            <div v-for="(issue, index) in item.issues" :key="index" class="freshness-issue">
              · {{ issue }}
            </div>
          </div>
          <div v-else class="small muted">暂未发现明显过时问题。</div>
          <div class="task-reason" style="margin-top: 10px">{{ item.suggestion }}</div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">时效判断怎么来的</div>
      <div class="stack" style="margin-top: 10px">
        <div class="kv"><span>年份</span><strong>识别资料中的版本年份，距当前越久分数越低</strong></div>
        <div class="kv"><span>考纲</span><strong>检查是否包含最新考试大纲 / 题型说明</strong></div>
        <div class="kv"><span>内容</span><strong>内容过少或缺少近年真题会提示补充</strong></div>
        <div class="kv"><span>建议</span><strong>由 DeepSeek 生成具体补资料方向，失败时用规则建议</strong></div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">补资料优先级建议</div>
      <div class="stack" style="margin-top: 10px">
        <div class="kv"><span>第一优先</span><strong>评分低于 40 分的资料，可能缺少最新考纲与题型</strong></div>
        <div class="kv"><span>第二优先</span><strong>评分 40-60 分的资料，内容年份较旧，建议补充近年真题</strong></div>
        <div class="kv"><span>第三优先</span><strong>评分 60-80 分的资料，内容基本可用，但建议核对考纲变化</strong></div>
        <div class="kv"><span>保持关注</span><strong>评分 80 分以上的资料，时效良好，按常规复习即可</strong></div>
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
