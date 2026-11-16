<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'
import DetailModal from '../components/DetailModal.vue'

const loading = ref(true)
const deck = ref({ cards: [], total: 0, due_count: 0 })
const index = ref(0)
const flipped = ref(false)
const reviewing = ref(false)
const stats = ref({ remembered: 0, forgot: 0 })
const finished = ref(false)
const explainLoading = ref(false)
const explainMap = ref({})
const showStats = ref(false)
const knowledgeOpen = ref(false)

const current = computed(() => deck.value.cards[index.value] || null)
const explain = computed(() => (current.value ? explainMap.value[current.value.kp_id] : null))
const progress = computed(() =>
  deck.value.cards.length ? Math.round((index.value / deck.value.cards.length) * 100) : 0
)
const accuracy = computed(() => {
  const total = stats.value.remembered + stats.value.forgot
  return total ? Math.round((stats.value.remembered / total) * 100) : 0
})

const knowledgeRows = computed(() => {
  const card = current.value
  if (!card) return []
  const info = explain.value || {}
  return [
    { label: '所属模块', value: card.parent || '独立知识点' },
    { label: '释义', value: info.explanation || '正在生成…' },
    { label: '记忆要点', value: info.memory_tip || '—' },
    { label: '常见误区', value: info.misconception || '—' },
    { label: '掌握度', value: `${Math.round((card.mastery || 0) * 100)}%` },
    { label: '权重', value: card.weight },
    { label: '下次复习', value: card.next_review_at || '尚未安排' },
    { label: '记忆保持率', value: `${Math.round((card.retention_now || 0) * 100)}%（稳定度 ${card.stability_days} 天）` },
    { label: '复习间隔', value: card.reason || '—' }
  ]
})

const dueRate = computed(() => {
  if (!deck.value.total) return 0
  return Math.round((deck.value.due_count / deck.value.total) * 100)
})

const masteryDistribution = computed(() => {
  const dist = { excellent: 0, good: 0, warning: 0, stale: 0 }
  for (const card of deck.value.cards) {
    if (card.mastery >= 0.8) dist.excellent += 1
    else if (card.mastery >= 0.6) dist.good += 1
    else if (card.mastery >= 0.4) dist.warning += 1
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
    deck.value = await api.flashcards(store.currentGoalId, 20)
    index.value = 0
    flipped.value = false
    stats.value = { remembered: 0, forgot: 0 }
    finished.value = deck.value.cards.length === 0
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function evaluate(remembered) {
  if (!current.value || reviewing.value) return
  reviewing.value = true
  try {
    const result = await api.reviewFlashcard(
      store.currentGoalId,
      current.value.kp_id,
      remembered
    )
    if (remembered) stats.value.remembered += 1
    else stats.value.forgot += 1
    current.value.mastery = result.mastery
    current.value.next_review_at = result.next_review_at
    index.value += 1
    flipped.value = false
    if (index.value >= deck.value.cards.length) {
      finished.value = true
      notify(`本组完成：记住 ${stats.value.remembered} 张，忘记 ${stats.value.forgot} 张`)
    }
  } catch (e) {
    notify(e.message, true)
  } finally {
    reviewing.value = false
  }
}

async function toggleFlip() {
  flipped.value = !flipped.value
  if (flipped.value) await loadExplain()
}

async function loadExplain() {
  const card = current.value
  if (!card || explainMap.value[card.kp_id] || explainLoading.value) return
  explainLoading.value = true
  try {
    const data = await api.flashcardExplain(store.currentGoalId, card.kp_id)
    explainMap.value = { ...explainMap.value, [card.kp_id]: data }
  } catch (e) {
    notify(e.message, true)
  } finally {
    explainLoading.value = false
  }
}

function onKey(event) {
  if (finished.value || !current.value) return
  if (event.code === 'Space') {
    event.preventDefault()
    toggleFlip()
  }
  if (event.key === '1') evaluate(true)
  if (event.key === '2') evaluate(false)
}

watch(() => store.currentGoalId, load, { immediate: true })
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div v-if="!store.currentGoalId" class="empty">
    还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建目标。
  </div>

  <div v-else-if="loading" class="empty">正在整理闪卡队列...</div>

  <div v-else class="stack">
    <div class="hero">
      <h1>闪卡复习 · 用间隔重复对抗遗忘</h1>
      <p>
        每张卡对应一个知识点。翻面回忆，记得就进入 1 / 2 / 4 / 7 / 15 天的间隔，忘记就回到 1 天。
        比重复看书更省时间，也更接近真实记忆规律。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ deck.total }}</strong>
          <span>可复习知识点</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ deck.due_count }}</strong>
          <span>今日到期</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ dueRate }}%</strong>
          <span>到期率</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ stats.remembered }}</strong>
          <span>本组记住</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ stats.forgot }}</strong>
          <span>本组忘记</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ accuracy }}%</strong>
          <span>记忆正确率</span>
        </div>
      </div>
    </div>

    <div class="row-between">
      <div class="small muted">
        键盘：空格翻面，按 1 记得，按 2 忘记
      </div>
      <button class="btn btn-ghost btn-sm" :aria-pressed="!showStats" @click="showStats = false">复习界面</button>
      <button class="btn btn-ghost btn-sm" :aria-pressed="showStats" @click="showStats = true">统计面板</button>
    </div>

    <div v-if="showStats" class="split">
      <div class="stack">
        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">本组进度</div>
              <div class="card-sub">{{ Math.min(index + 1, deck.cards.length) }} / {{ deck.cards.length }}</div>
            </div>
            <button class="btn btn-ghost btn-sm" @click="load">重新抽卡</button>
          </div>
          <div class="bar" style="margin-bottom: 18px"><i :style="{ width: progress + '%' }"></i></div>

          <div v-if="finished" class="flash-finish">
            <div class="flash-finish-icon">✓</div>
            <div class="card-title">本组完成</div>
            <div class="stat-value" style="margin: 10px 0">{{ accuracy }}%</div>
            <div class="small muted">
              记住 {{ stats.remembered }} 张，忘记 {{ stats.forgot }} 张。忘记的知识点已重置复习间隔，
              会自动进入后续计划。
            </div>
            <div class="row" style="margin-top: 18px; justify-content: center">
              <button class="btn" @click="load">再来一组</button>
              <router-link class="btn btn-ghost" to="/plan">查看计划</router-link>
            </div>
          </div>

          <div v-else-if="current" class="flashcard" :class="{ flipped }" @click="toggleFlip">
            <div class="flashcard-inner">
              <div class="flashcard-face front">
                <div class="small muted">{{ current.parent || '知识点' }}</div>
                <div class="flash-name">{{ current.kp_name }}</div>
                <div class="flash-hint">点击卡片或按空格查看背面</div>
                <span class="tag" :class="current.due ? 'tag-review' : 'tag-pending'">{{ current.reason }}</span>
              </div>
              <div class="flashcard-face back" @click.stop>
                <div class="row-between">
                  <div class="small muted">知识点</div>
                  <button class="btn btn-ghost btn-sm" @click="knowledgeOpen = true">查看知识详情</button>
                </div>
                <div class="flash-name" style="font-size: 20px; margin-bottom: 8px">{{ current.kp_name }}</div>
                <div class="small muted">掌握度</div>
                <div class="flash-mastery">{{ Math.round(current.mastery * 100) }}%</div>
                <div class="bar" style="margin: 8px 0 12px">
                  <i :style="{ width: Math.max(current.mastery * 100, 2) + '%' }"></i>
                </div>
                <div class="kv"><span>所属模块</span><strong>{{ current.parent || '独立知识点' }}</strong></div>
                <div class="kv"><span>权重</span><strong>{{ current.weight }}</strong></div>
                <div class="kv"><span>下次复习</span><strong>{{ current.next_review_at || '尚未安排' }}</strong></div>
                <div class="kv"><span>记忆保持率</span><strong>{{ Math.round((current.retention_now || 0) * 100) }}% · 稳定度 {{ current.stability_days }} 天</strong></div>
                <div class="kv"><span>目标保持率 {{ Math.round((current.target_retention || 0.9) * 100) }}%{{ current.phase_label ? " · " + current.phase_label : "" }}</span><strong>预计 {{ current.days_to_target }} 天后降到 {{ Math.round((current.target_retention || 0.9) * 100) }}%</strong></div>
                <div class="flash-ai">
                  <div class="row-between">
                    <b class="small">AI 释义</b>
                    <span
                      v-if="explain"
                      class="tag"
                      :class="explain.engine === 'llm' ? 'tag-practice' : 'tag-study'"
                    >
                      {{ explain.engine === 'llm' ? '智能讲解' : '备用讲解' }}
                    </span>
                  </div>
                  <div v-if="explainLoading" class="small muted" style="margin-top: 6px">
                    AI 正在生成释义...
                  </div>
                  <template v-else-if="explain">
                    <div class="small" style="margin-top: 6px">{{ explain.explanation }}</div>
                    <div class="small muted" style="margin-top: 4px">记忆：{{ explain.memory_tip }}</div>
                    <div class="small muted" style="margin-top: 2px">误区：{{ explain.misconception }}</div>
                    <div v-if="explain.external?.available" class="flash-external">
                      <div class="small muted">外部知识库</div>
                      <div v-for="src in explain.external.sources" :key="src.name" class="small">
                        <b>{{ src.name }}</b>：{{ src.summary }}
                      </div>
                    </div>
                  </template>
                </div>
              </div>
            </div>
          </div>

          <div v-else class="empty">没有可复习的知识点，先去导入资料。</div>
        </div>

      </div>

      <div class="stack">
        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">本组状态</div>
              <div class="card-sub">实时统计本组复习数据</div>
            </div>
          </div>
          <div class="grid grid-2" style="gap: 10px; margin-top: 10px">
            <div class="stat" style="background: #ecfdf5">
              <div class="stat-label">记住</div>
              <div class="stat-value" style="color: #059669">{{ stats.remembered }}</div>
              <div class="bar" style="margin-top: 6px"><i :style="{ width: (stats.remembered / (stats.remembered + stats.forgot || 1)) * 100 + '%' }" style="background: #059669"></i></div>
            </div>
            <div class="stat" style="background: #fef2f2">
              <div class="stat-label">忘记</div>
              <div class="stat-value" style="color: #dc2626">{{ stats.forgot }}</div>
              <div class="bar" style="margin-top: 6px"><i :style="{ width: (stats.forgot / (stats.remembered + stats.forgot || 1)) * 100 + '%' }" style="background: #dc2626"></i></div>
            </div>
          </div>
          <div class="kv" style="margin-top: 10px">
            <span>记忆正确率</span>
            <strong>{{ accuracy }}%</strong>
          </div>
          <div class="bar" style="margin-top: 6px"><i :style="{ width: accuracy + '%' }"></i></div>
        </div>

        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">掌握度分布</div>
              <div class="card-sub">本组卡片的掌握度分布</div>
            </div>
          </div>
          <div class="grid grid-2" style="gap: 10px; margin-top: 10px">
            <div class="stat" style="background: #ecfdf5">
              <div class="stat-label">优秀 (≥80%)</div>
              <div class="stat-value" style="color: #059669">{{ masteryDistribution.excellent }}</div>
            </div>
            <div class="stat" style="background: #eff6ff">
              <div class="stat-label">良好 (60-79%)</div>
              <div class="stat-value" style="color: #2563eb">{{ masteryDistribution.good }}</div>
            </div>
            <div class="stat" style="background: #fffbeb">
              <div class="stat-label">警告 (40-59%)</div>
              <div class="stat-value" style="color: #d97706">{{ masteryDistribution.warning }}</div>
            </div>
            <div class="stat" style="background: #fef2f2">
              <div class="stat-label">过时 (&lt;40%)</div>
              <div class="stat-value" style="color: #dc2626">{{ masteryDistribution.stale }}</div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-title">为什么有效</div>
          <div class="small muted" style="margin-top: 10px; line-height: 1.9">
            闪卡把「重读」变成「主动回忆」。忘记的卡片会立即回到最短间隔，
            系统还会同步降低掌握度，后续计划会自动为它安排补救任务。
          </div>
        </div>

        <div class="card">
          <div class="card-title">复习建议</div>
          <div class="stack" style="margin-top: 10px">
            <div class="kv"><span>到期复习</span><strong>优先复习到期卡片，避免遗忘</strong></div>
            <div class="kv"><span>薄弱卡片</span><strong>掌握度低于 60% 的卡片建议重点复习</strong></div>
            <div class="kv"><span>间隔复习</span><strong>记得的卡片按间隔复习，巩固长期记忆</strong></div>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="flashcard-layout">
      <div class="card flashcard-panel">
        <div class="card-head">
          <div>
            <div class="card-title">本组进度</div>
            <div class="card-sub">{{ Math.min(index + 1, deck.cards.length) }} / {{ deck.cards.length }}</div>
          </div>
          <button class="btn btn-ghost btn-sm" @click="load">重新抽卡</button>
        </div>
        <div class="bar" style="margin-bottom: 18px"><i :style="{ width: progress + '%' }"></i></div>

        <div v-if="finished" class="flash-finish">
          <div class="flash-finish-icon">✓</div>
          <div class="card-title">本组完成</div>
          <div class="stat-value" style="margin: 10px 0">{{ accuracy }}%</div>
          <div class="small muted">
            记住 {{ stats.remembered }} 张，忘记 {{ stats.forgot }} 张。忘记的知识点已重置复习间隔，
            会自动进入后续计划。
          </div>
          <div class="row" style="margin-top: 18px; justify-content: center">
            <button class="btn" @click="load">再来一组</button>
            <router-link class="btn btn-ghost" to="/plan">查看计划</router-link>
          </div>
        </div>

        <template v-else-if="current">
          <div class="flashcard" :class="{ flipped }" @click="toggleFlip">
            <div class="flashcard-inner">
              <div class="flashcard-face front">
                <div class="small muted">{{ current.parent || '知识点' }}</div>
                <div class="flash-name">{{ current.kp_name }}</div>
                <div class="flash-hint">点击卡片或按空格查看背面</div>
                <span class="tag" :class="current.due ? 'tag-review' : 'tag-pending'">{{ current.reason }}</span>
              </div>
              <div class="flashcard-face back" @click.stop>
                <div class="row-between">
                  <div class="small muted">知识点</div>
                  <button class="btn btn-ghost btn-sm" @click="knowledgeOpen = true">查看知识详情</button>
                </div>
                <div class="flash-name" style="font-size: 20px; margin-bottom: 8px">{{ current.kp_name }}</div>
                <div class="small muted">掌握度</div>
                <div class="flash-mastery">{{ Math.round(current.mastery * 100) }}%</div>
                <div class="bar" style="margin: 8px 0 12px">
                  <i :style="{ width: Math.max(current.mastery * 100, 2) + '%' }"></i>
                </div>
                <div class="kv"><span>所属模块</span><strong>{{ current.parent || '独立知识点' }}</strong></div>
                <div class="kv"><span>权重</span><strong>{{ current.weight }}</strong></div>
                <div class="kv"><span>下次复习</span><strong>{{ current.next_review_at || '尚未安排' }}</strong></div>
                <div class="kv"><span>记忆保持率</span><strong>{{ Math.round((current.retention_now || 0) * 100) }}% · 稳定度 {{ current.stability_days }} 天</strong></div>
                <div class="kv"><span>目标保持率 {{ Math.round((current.target_retention || 0.9) * 100) }}%{{ current.phase_label ? " · " + current.phase_label : "" }}</span><strong>预计 {{ current.days_to_target }} 天后降到 {{ Math.round((current.target_retention || 0.9) * 100) }}%</strong></div>
                <div class="flash-ai">
                  <div class="row-between">
                    <b class="small">AI 释义</b>
                    <span
                      v-if="explain"
                      class="tag"
                      :class="explain.engine === 'llm' ? 'tag-practice' : 'tag-study'"
                    >
                      {{ explain.engine === 'llm' ? '智能讲解' : '备用讲解' }}
                    </span>
                  </div>
                  <div v-if="explainLoading" class="small muted" style="margin-top: 6px">
                    AI 正在生成释义...
                  </div>
                  <template v-else-if="explain">
                    <div class="small" style="margin-top: 6px">{{ explain.explanation }}</div>
                    <div class="small muted" style="margin-top: 4px">记忆：{{ explain.memory_tip }}</div>
                    <div class="small muted" style="margin-top: 2px">误区：{{ explain.misconception }}</div>
                    <div v-if="explain.external?.available" class="flash-external">
                      <div class="small muted">外部知识库</div>
                      <div v-for="src in explain.external.sources" :key="src.name" class="small">
                        <b>{{ src.name }}</b>：{{ src.summary }}
                      </div>
                    </div>
                  </template>
                </div>
              </div>
            </div>
          </div>

          <div class="row" style="margin-top: 18px; justify-content: center">
            <button class="btn btn-ghost" :disabled="reviewing" @click="toggleFlip">
              {{ flipped ? '看正面' : '翻面' }}
            </button>
            <button class="btn btn-teal" :disabled="reviewing" @click="evaluate(true)">记得（1）</button>
            <button class="btn btn-danger" :disabled="reviewing" @click="evaluate(false)">忘记（2）</button>
          </div>
          <div class="small muted" style="text-align: center; margin-top: 10px">
            键盘：空格翻面，按 1 记得，按 2 忘记
          </div>
        </template>

        <div v-else class="empty">没有可复习的知识点，先去导入资料。</div>
      </div>

      <div class="stack">
        <div class="card">
          <div class="card-title">间隔重复规则</div>
          <div class="stack" style="margin-top: 10px">
            <div class="kv"><span>记得</span><strong>进入下一档：1 → 2 → 4 → 7 → 15 天</strong></div>
            <div class="kv"><span>忘记</span><strong>回到 1 天后重新复习</strong></div>
            <div class="kv"><span>掌握度</span><strong>记得 +30% 向 1 靠近，忘记向 0 靠近</strong></div>
          </div>
        </div>

        <div class="card">
          <div class="card-title">本组状态</div>
          <div class="stack" style="margin-top: 10px">
            <div class="kv"><span>记住</span><strong>{{ stats.remembered }} 张</strong></div>
            <div class="kv"><span>忘记</span><strong>{{ stats.forgot }} 张</strong></div>
            <div class="kv"><span>记忆正确率</span><strong>{{ accuracy }}%</strong></div>
          </div>
        </div>

        <div class="card">
          <div class="card-title">为什么有效</div>
          <div class="small muted" style="margin-top: 10px; line-height: 1.9">
            闪卡把「重读」变成「主动回忆」。忘记的卡片会立即回到最短间隔，
            系统还会同步降低掌握度，后续计划会自动为它安排补救任务。
          </div>
        </div>
      </div>
    </div>

    <DetailModal
      :open="knowledgeOpen"
      :title="current?.kp_name || '知识点'"
      :subtitle="current?.parent || ''"
      :rows="knowledgeRows"
      @close="knowledgeOpen = false"
    />

  </div>
</template>
