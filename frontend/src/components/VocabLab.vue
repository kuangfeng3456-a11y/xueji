<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api'
import { notify } from '../store'

const props = defineProps({
  goalId: { type: Number, required: true },
  kpId: { type: Number, required: true },
  title: { type: String, default: '词汇' }
})

const emit = defineEmits(['close', 'finished'])

const loading = ref(true)
const words = ref([])
const index = ref(0)
const revealed = ref(false)
const summary = ref(null)
const saving = ref(false)
const meta = ref({ total: 0, learned: 0, known: 0, decks: [] })
const tally = ref({ known: 0, fuzzy: 0, unknown: 0 })
const speaking = ref(false)

const current = computed(() => words.value[index.value] || null)
const progress = computed(() => (words.value.length ? Math.round(((index.value) / words.value.length) * 100) : 0))
const accuracy = computed(() => {
  const total = tally.value.known + tally.value.fuzzy + tally.value.unknown
  return total ? Math.round((tally.value.known / total) * 100) : 0
})

async function load() {
  loading.value = true
  summary.value = null
  index.value = 0
  revealed.value = false
  tally.value = { known: 0, fuzzy: 0, unknown: 0 }
  try {
    const data = await api.vocabSession(props.goalId, props.kpId, 20)
    words.value = data.words || []
    meta.value = { total: data.total, learned: data.learned, known: data.known, decks: data.decks || [] }
    if (!words.value.length) notify('这个词表暂时没有更多单词', true)
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

function speak() {
  const word = current.value?.word
  if (!word) return
  if (!('speechSynthesis' in window)) {
    notify('当前浏览器不支持发音', true)
    return
  }
  window.speechSynthesis.cancel()
  const utter = new SpeechSynthesisUtterance(word)
  utter.lang = 'en-US'
  utter.rate = 0.92
  speaking.value = true
  utter.onend = () => { speaking.value = false }
  utter.onerror = () => { speaking.value = false }
  window.speechSynthesis.speak(utter)
}

async function mark(action) {
  const word = current.value
  if (!word) return
  tally.value[action] += 1
  // 首次标记的单词计入「已学」，避免顶部计数原地不动
  if (!word.state) {
    word.state = action
    meta.value.learned = Math.min(meta.value.total, meta.value.learned + 1)
    if (action === 'known') meta.value.known = Math.min(meta.value.total, meta.value.known + 1)
  } else if (word.state !== action) {
    word.state = action
  }
  api.vocabReview(props.goalId, { kp_id: props.kpId, word: word.word, action }).catch(() => {})
  if (index.value + 1 >= words.value.length) {
    await finish()
    return
  }
  index.value += 1
  revealed.value = false
}

async function finish() {
  saving.value = true
  try {
    const data = await api.vocabFinish(props.goalId, {
      kp_id: props.kpId,
      known: tally.value.known,
      fuzzy: tally.value.fuzzy,
      unknown: tally.value.unknown
    })
    summary.value = data
    emit('finished', data)
  } catch (e) {
    notify(e.message, true)
  } finally {
    saving.value = false
  }
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    emit('close')
    return
  }
  if (summary.value) {
    if (event.key === 'Enter') load()
    return
  }
  if (event.key === '1') mark('unknown')
  else if (event.key === '2') mark('fuzzy')
  else if (event.key === '3') mark('known')
  else if (event.key === ' ' || event.key === 'Enter') {
    event.preventDefault()
    if (!revealed.value) revealed.value = true
    else speak()
  }
}

onMounted(() => {
  load()
  document.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  if ('speechSynthesis' in window) window.speechSynthesis.cancel()
})
</script>

<template>
  <div class="modal-mask vocab-mask" @click.self="emit('close')">
    <div class="vocab-panel">
      <div class="vocab-head">
        <div>
          <div class="vocab-title">单词卡 · {{ meta.decks.join(' / ') || title }}</div>
          <div class="vocab-sub">
            词表 {{ meta.total }} 词 · 已学 {{ meta.learned }} 词
            <span v-if="words.length">· 本轮 {{ Math.min(index + 1, words.length) }} / {{ words.length }}</span>
          </div>
        </div>
        <button class="btn btn-ghost btn-sm" @click="emit('close')">关闭</button>
      </div>

      <div class="vocab-progress">
        <i :style="{ width: summary ? '100%' : progress + '%' }"></i>
      </div>

      <div v-if="loading" class="empty" style="padding: 40px 0">正在准备词表...</div>

      <template v-else-if="!words.length">
        <div class="empty" style="padding: 36px 0">这个词表暂时没有单词，先学其它知识点吧。</div>
      </template>

      <template v-else-if="summary">
        <div class="vocab-done">
          <div class="vocab-done-rate">{{ accuracy }}<small>%</small></div>
          <div class="vocab-done-caption">本轮认识率 · 共 {{ tally.known + tally.fuzzy + tally.unknown }} 词</div>
          <div class="vocab-done-stats">
            <div class="vocab-done-item is-known"><b>{{ tally.known }}</b><span>认识</span></div>
            <div class="vocab-done-item is-fuzzy"><b>{{ tally.fuzzy }}</b><span>模糊</span></div>
            <div class="vocab-done-item is-unknown"><b>{{ tally.unknown }}</b><span>不认识</span></div>
          </div>
          <div class="vocab-done-note">
            掌握度已更新为 {{ Math.round((summary.mastery || 0) * 100) }}%，
            下次复习 {{ summary.next_review_at || '明天' }}。
          </div>
          <div class="vocab-done-actions">
            <button class="btn btn-ghost" :disabled="saving" @click="load">再来一组</button>
            <button class="btn" @click="emit('close')">完成</button>
          </div>
        </div>
      </template>

      <template v-else>
        <div class="vocab-card" :class="{ 'is-revealed': revealed }">
          <div class="vocab-word-row">
            <span class="vocab-word">{{ current.word }}</span>
            <button class="vocab-speak" :class="{ 'is-speaking': speaking }" title="朗读" @click="speak">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M4 9v6h4l5 4V5L8 9H4z" fill="currentColor" />
                <path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
              </svg>
            </button>
          </div>
          <div class="vocab-phonetic">{{ current.phonetic }}</div>

          <button v-if="!revealed" class="vocab-reveal" @click="revealed = true">
            点击显示释义 <small>（空格）</small>
          </button>

          <div v-if="!revealed" class="vocab-recall">
            先在心里回忆它的中文意思，再点开核对；想不起来就直接点「不认识」。
          </div>

          <div v-else class="vocab-meaning">
            <div class="vocab-pos">{{ current.pos }}</div>
            <div class="vocab-cn">{{ current.meaning }}</div>
            <div class="vocab-example">
              <div class="vocab-example-en">{{ current.example }}</div>
              <div class="vocab-example-cn">{{ current.example_cn }}</div>
            </div>
          </div>
        </div>

        <div class="vocab-actions">
          <button class="vocab-btn is-unknown" @click="mark('unknown')"><b>不认识</b><small>1</small></button>
          <button class="vocab-btn is-fuzzy" @click="mark('fuzzy')"><b>模糊</b><small>2</small></button>
          <button class="vocab-btn is-known" @click="mark('known')"><b>认识</b><small>3</small></button>
        </div>
        <div class="vocab-hint">按 1 / 2 / 3 快速标记，空格显示释义，Esc 退出</div>
      </template>
    </div>
  </div>
</template>
