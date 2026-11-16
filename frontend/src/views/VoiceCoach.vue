<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { cloudSpeechReady, startRecorder } from '../voiceInput'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { store, notify } from '../store'

function nowTime() {
  const d = new Date()
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const messages = ref([
  {
    role: 'coach',
    text: '你好，我是学迹教练。你可以直接问我「今天学什么」「我的薄弱点」「还剩几天」，也可以点击麦克风说话。',
    source: 'rule',
    suggestions: ['今天学什么', '我的薄弱点', '还剩几天', '怎么复习'],
    time: nowTime()
  }
])
const question = ref('')
const listening = ref(false)
const busy = ref(false)
const speaking = ref(false)
const showQuick = ref(false)
const showEmoji = ref(false)
const listRef = ref(null)
const textInput = ref(null)

const emojis = ['😀', '😂', '🤔', '👍', '💪', '🎯', '📚', '✏️', '⏰', '🔥', '💡', '❤️', '😎', '🤗', '🙌', '✨', '📌', '🏆', '⭐', '📝', '🧠', '😊', '🤝', '💯']

let recognition = null

const SpeechRecognition =
  typeof window !== 'undefined' ? window.SpeechRecognition || window.webkitSpeechRecognition : null
const speechSupported = Boolean(SpeechRecognition)
const synthesisSupported =
  typeof window !== 'undefined' && 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window

const route = useRoute()
const router = useRouter()
const mode = ref(route.query.mode === 'shadow' ? 'shadow' : 'chat')
const sessionId = ref(0)
const inputChannel = ref('语音输入可用文字代替')
const outputChannel = ref('朗读会优先尝试云端语音，未开通时改用本机')
let capture = null

const SHADOW_BANK = [
  { id: 'p1', topic: '发音', text: 'The features of English pronunciation take practice every day.', tip: '注意 features 和 pronunciation 的重音落在第二音节。' },
  { id: 'p2', topic: '学习方法', text: 'A good method is to review new words before you go to sleep.', tip: 'method 与 review 不要读成弱化的含混音。' },
  { id: 'p3', topic: '火星殖民', text: 'Some scientists discuss the culture of a future Mars colony.', tip: 'colony 的重音在第一音节，culture 不要吞掉第一个元音。' },
  { id: 'p4', topic: '观点表达', text: 'I would like to share my opinion on this topic.', tip: 'would like to 可以自然连读。' },
  { id: 'p5', topic: '听力口语', text: 'Clear pronunciation helps the listener understand your idea.', tip: 'pronunciation 较长，建议按音节慢慢跟读一遍再加速。' }
]

const shadowIndex = ref(0)
const shadowHeard = ref('')
const shadowResult = ref(null)
const shadowListening = ref(false)
const shadowLines = ref(SHADOW_BANK.map((item) => ({ ...item, source: '通用练习' })))
const spokenWord = ref(-1)
const currentShadow = computed(() => shadowLines.value[shadowIndex.value] || shadowLines.value[0] || SHADOW_BANK[0])
const shadowWords = computed(() => splitShadowWords(currentShadow.value?.text || ''))

function splitShadowWords(text) {
  const words = []
  const re = /[A-Za-z']+|[\u4e00-\u9fff]|[^A-Za-z'\u4e00-\u9fff]+/g
  const raw = String(text || '')
  let match
  while ((match = re.exec(raw))) {
    const token = match[0]
    const spoken = /[A-Za-z'\u4e00-\u9fff]/.test(token)
    words.push({ raw: token, spoken, start: match.index })
  }
  return words
}

function wordIndexFromChar(charIndex) {
  const words = shadowWords.value
  let current = -1
  for (let i = 0; i < words.length; i += 1) {
    if (!words[i].spoken) continue
    if (charIndex >= words[i].start) current = i
  }
  return current
}

function sentenceFromTopic(name, source) {
  const topic = String(name || '').replace(/\s+/g, ' ').trim()
  if (!topic || topic.length < 2) return null
  if (/^[A-Za-z]/.test(topic) && topic.split(/\s+/).length >= 6) {
    const text = /[.!?]$/.test(topic) ? topic : `${topic}.`
    return {
      id: `live-${source}-${topic.slice(0, 24)}`,
      topic: source,
      text,
      tip: '这句来自今天的学习内容，请按意群跟读。',
      source
    }
  }
  return {
    id: `live-${source}-${topic}`,
    topic,
    text: `Let's review this topic: ${topic}.`,
    tip: `这句对应「${topic}」，跟读时把关键词读清楚。`,
    source
  }
}

function collectTopics(payload, bag) {
  if (!payload) return
  if (Array.isArray(payload)) {
    payload.forEach((item) => collectTopics(item, bag))
    return
  }
  if (typeof payload !== 'object') return
  for (const key of ['kp_name', 'name', 'title', 'question', 'stem', 'content', 'text']) {
    const value = payload[key]
    if (typeof value === 'string' && value.trim()) bag.push(value.trim())
  }
  for (const key of ['kps', 'knowledge_points', 'points', 'slots', 'items', 'videos', 'questions', 'days', 'quiz']) {
    if (payload[key]) collectTopics(payload[key], bag)
  }
}

function uniqueLines(items) {
  const seen = new Set()
  const result = []
  for (const item of items) {
    if (!item || !item.text) continue
    const key = item.text.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    result.push(item)
  }
  return result
}

async function loadShadowMaterial() {
  const fallback = SHADOW_BANK.map((item) => ({ ...item, source: '通用练习' }))
  const goalId = store.currentGoalId
  if (!goalId) {
    shadowLines.value = fallback
    return
  }
  const collected = []
  try {
    const plan = await api.examPrepPlan(goalId)
    const days = plan.days || plan.plan?.days || []
    const todayIndex = Number(plan.today_index ?? plan.current_day ?? plan.today ?? 0) || 0
    let day = days[todayIndex] || days[0] || plan
    const dayIndex = Number(day?.day_index ?? day?.index ?? todayIndex)
    if (Number.isFinite(dayIndex)) {
      try {
        const detail = await api.examPrepDay(goalId, dayIndex)
        day = detail.day || detail || day
      } catch {
        /* 有总方案也可以先抽出知识点 */
      }
    }
    const topics = []
    collectTopics(day, topics)
    for (const topic of topics) {
      const line = sentenceFromTopic(topic, '今日课程')
      if (line) collected.push(line)
      if (collected.length >= 4) break
    }
  } catch {
    /* 没有备考方案时用错题和通用句 */
  }
  try {
    const mistakes = await api.mistakes(goalId)
    const items = Array.isArray(mistakes) ? mistakes : mistakes.items || mistakes.mistakes || []
    for (const item of items) {
      const topic = item.question || item.stem || item.content || item.title || item.kp_name
      const line = sentenceFromTopic(topic, '近期错题')
      if (line) collected.push(line)
      if (collected.filter((row) => row.source === '近期错题').length >= 2) break
    }
  } catch {
    /* 错题接口失败不影响跟读 */
  }
  const merged = uniqueLines([...collected, ...fallback])
  shadowLines.value = merged.slice(0, 8)
  if (shadowIndex.value >= shadowLines.value.length) shadowIndex.value = 0
}

watch(
  () => [store.currentGoalId, mode.value],
  () => {
    if (mode.value === 'shadow') loadShadowMaterial()
  },
  { immediate: true }
)

function setMode(next) {
  mode.value = next
  const query = { tab: 'voice' }
  if (next === 'shadow') query.mode = 'shadow'
  router.replace({ path: '/today', query })
}

watch(
  () => route.query.mode,
  (value) => {
    mode.value = value === 'shadow' ? 'shadow' : 'chat'
  }
)

function normalizeWords(text) {
  return String(text || '')
    .toLowerCase()
    .replace(/[^a-z'\s]/g, ' ')
    .split(/\s+/)
    .filter(Boolean)
}

function scoreShadow(target, heard) {
  const expected = normalizeWords(target)
  const actual = normalizeWords(heard)
  if (!expected.length) {
    return { score: 0, matched: [], missed: [], extra: actual, detail: '没有可对的标准句' }
  }
  const remain = actual.slice()
  const matched = []
  const missed = []
  for (const word of expected) {
    const at = remain.indexOf(word)
    if (at >= 0) {
      matched.push(word)
      remain.splice(at, 1)
    } else {
      missed.push(word)
    }
  }
  const recall = matched.length / expected.length
  const precision = actual.length ? matched.length / actual.length : 0
  const score = Math.round(((recall * 0.7) + (precision * 0.3)) * 100)
  let detail = '很接近标准音，可以再练一遍语调。'
  if (score >= 90) detail = '跟读很完整，词汇都对上了。'
  else if (score >= 70) detail = '大体正确，把未命中的词再跟读一次。'
  else if (score >= 40) detail = '先听标准音，再按意群慢慢跟读。'
  else detail = '识别结果和原句差距较大，建议先听两遍再开口。'
  return { score, matched, missed, extra: remain, detail }
}

const goalName = computed(() => {
  const goal = store.goals.find((item) => item.id === store.currentGoalId)
  return goal ? goal.exam_name : '未设置目标'
})

async function scrollToBottom() {
  await nextTick()
  if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
}

function addMessage(role, text, source = 'rule', suggestions = []) {
  messages.value.push({ role, text, source, suggestions, time: nowTime() })
}

function showTime(index) {
  if (index === 0) return true
  const prev = messages.value[index - 1]
  const curr = messages.value[index]
  if (!prev.time || !curr.time) return false
  const [ph, pm] = prev.time.split(':').map(Number)
  const [ch, cm] = curr.time.split(':').map(Number)
  return ch * 60 + cm - (ph * 60 + pm) >= 3
}

function clockFrom(value) {
  if (!value) return nowTime()
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return nowTime()
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

async function ensureSession() {
  if (sessionId.value) return sessionId.value
  const created = await api.createCoachSession({ goal_id: store.currentGoalId || null, title: '语音教练' })
  sessionId.value = created.id
  return created.id
}

async function loadHistory() {
  try {
    const listed = await api.coachSessions()
    const latest = (listed.items || [])[0]
    if (!latest) return
    sessionId.value = latest.id
    const detail = await api.coachSession(latest.id)
    if (!detail.messages?.length) return
    messages.value = detail.messages.map((item) => ({
      role: item.role === 'user' ? 'user' : 'coach',
      text: item.text,
      source: item.source || 'rule',
      suggestions: [],
      time: clockFrom(item.created_at)
    }))
    await scrollToBottom()
  } catch (e) {
    /* 没有历史时保留开场白 */
  }
}

function useWebSpeech(onText) {
  if (!speechSupported) {
    notify('当前环境不能识别语音，请直接输入文字', true)
    inputChannel.value = '请改用文字输入'
    return
  }
  recognition = new SpeechRecognition()
  recognition.lang = 'zh-CN'
  recognition.interimResults = false
  recognition.maxAlternatives = 1
  recognition.onresult = (event) => {
    const said = event.results?.[0]?.[0]?.transcript || ''
    listening.value = false
    if (said) onText(said)
  }
  recognition.onerror = () => {
    listening.value = false
    notify('本机语音识别失败，请改用文字', true)
  }
  recognition.onend = () => {
    listening.value = false
  }
  listening.value = true
  inputChannel.value = '本机语音识别'
  recognition.start()
}

async function startListening() {
  if (mode.value === 'shadow') {
    if (!speechSupported) {
      notify('当前浏览器不支持跟读识别，请先听标准音', true)
      return
    }
    startShadowListening()
    return
  }
  if (listening.value) {
    if (capture) {
      const pending = capture
      capture = null
      listening.value = false
      const blob = await pending.stop()
      await sendCloudAudio(blob)
    } else {
      recognition?.stop()
    }
    return
  }
  const cloudReady = await cloudSpeechReady(api)
  if (cloudReady) {
    try {
      capture = await startRecorder()
      capture.start()
      listening.value = true
      inputChannel.value = '云端语音识别'
      return
    } catch (e) {
      capture = null
      inputChannel.value = '本机语音识别'
    }
  } else {
    inputChannel.value = '本机语音识别（云端未开通）'
  }
  useWebSpeech((said) => {
    question.value = said
    ask()
  })
}

async function sendCloudAudio(blob) {
  if (!blob || !blob.size) {
    notify('没有录到声音，请再试一次', true)
    return
  }
  busy.value = true
  try {
    const id = await ensureSession()
    const form = new FormData()
    form.append('file', blob, 'speech.webm')
    form.append('audio_format', (blob.type || '').includes('wav') ? 'wav' : 'webm')
    if (store.currentGoalId) form.append('goal_id', String(store.currentGoalId))
    const data = await api.coachVoice(id, form)
    if (data.status === 'ok' && data.transcript) {
      inputChannel.value = '云端语音识别'
      applySessionReply(data.transcript, data)
      return
    }
    inputChannel.value = data.fallback_label || '请改用文字输入'
    notify(data.fallback_label || '云端语音识别不可用，请改用文字', true)
  } catch (e) {
    notify(e.message || '语音发送失败，请改用文字', true)
  } finally {
    busy.value = false
  }
}

function startShadowListening() {
  if (shadowListening.value) {
    recognition?.stop()
    return
  }
  shadowHeard.value = ''
  shadowResult.value = null
  recognition = new SpeechRecognition()
  recognition.lang = 'en-US'
  recognition.interimResults = false
  recognition.maxAlternatives = 1
  recognition.onresult = (event) => {
    const said = event.results?.[0]?.[0]?.transcript || ''
    shadowListening.value = false
    listening.value = false
    if (!said) {
      notify('没有识别到英文，请靠近麦克风再试一次', true)
      return
    }
    shadowHeard.value = said
    shadowResult.value = scoreShadow(currentShadow.value.text, said)
  }
  recognition.onerror = () => {
    shadowListening.value = false
    listening.value = false
    notify('跟读识别失败，请检查麦克风权限后重试', true)
  }
  recognition.onend = () => {
    shadowListening.value = false
    listening.value = false
  }
  shadowListening.value = true
  listening.value = true
  recognition.start()
}

function nextShadow() {
  const total = shadowLines.value.length || 1
  shadowIndex.value = (shadowIndex.value + 1) % total
  shadowHeard.value = ''
  shadowResult.value = null
  spokenWord.value = -1
}

async function playShadow() {
  await speak(currentShadow.value.text, 'en-US')
}

function applySessionReply(transcript, data) {
  addMessage('user', transcript, 'user')
  question.value = ''
  showQuick.value = false
  showEmoji.value = false
  addMessage('coach', data.answer, data.source || 'rule', data.suggestions || [])
  speak(data.answer)
}

async function ask(text) {
  const content = (text ?? question.value).trim()
  if (!content || busy.value) return
  question.value = ''
  showQuick.value = false
  showEmoji.value = false
  busy.value = true
  await scrollToBottom()
  try {
    const id = await ensureSession()
    const saved = await api.coachMessage(id, { text: content, goal_id: store.currentGoalId || null })
    addMessage('user', content, 'user')
    addMessage('coach', saved.answer, saved.source || 'rule', saved.suggestions || [])
    speak(saved.answer)
  } catch (e) {
    addMessage('coach', `抱歉，暂时没能回答：${e.message}`, 'error', ['今天学什么', '我的薄弱点'])
  } finally {
    busy.value = false
    await scrollToBottom()
  }
}

let cloudAudio = null

async function speak(text, lang = 'zh-CN') {
  // 优先华为云 SIS 语音合成；未开通/失败时回退浏览器 Web Speech
  try {
    const form = new FormData()
    form.append('text', String(text).slice(0, 500))
    const data = await api.sisSynthesize(form)
    if (data && data.status === 'ok' && data.audio_b64) {
      outputChannel.value = '云端语音合成'
      if (cloudAudio) {
        cloudAudio.pause()
        cloudAudio = null
      }
      cloudAudio = new Audio(`data:audio/${data.format || 'mp3'};base64,${data.audio_b64}`)
      speaking.value = true
      cloudAudio.onended = () => {
        speaking.value = false
      }
      cloudAudio.onerror = () => {
        speaking.value = false
        browserSpeak(text, lang)
      }
      await cloudAudio.play()
      return
    }
    if (data && data.status && data.status !== 'ok') {
      outputChannel.value = data.fallback_label || '本机朗读'
    }
  } catch (e) {
    outputChannel.value = '本机朗读'
  }
  browserSpeak(text, lang)
}

function browserSpeak(text, lang = 'zh-CN') {
  if (!synthesisSupported) {
    notify('当前浏览器不支持语音播报，请阅读文字回复', true)
    return
  }
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = lang || 'zh-CN'
  utterance.rate = 1.02
  spokenWord.value = -1
  utterance.onboundary = (event) => {
    if (event.name && event.name.toLowerCase() !== 'word') return
    spokenWord.value = wordIndexFromChar(event.charIndex || 0)
  }
  utterance.onstart = () => {
    speaking.value = true
  }
  utterance.onend = () => {
    speaking.value = false
    spokenWord.value = -1
  }
  utterance.onerror = () => {
    speaking.value = false
    spokenWord.value = -1
  }
  window.speechSynthesis.speak(utterance)
}

function stopSpeaking() {
  if (synthesisSupported) window.speechSynthesis.cancel()
  speaking.value = false
}

function addEmoji(emoji) {
  question.value += emoji
  showEmoji.value = false
  textInput.value?.focus()
}

function closePanels() {
  showQuick.value = false
  showEmoji.value = false
}

onMounted(() => {
  loadHistory()
  cloudSpeechReady(api).then((ready) => {
    inputChannel.value = ready ? '可使用云端语音识别' : '云端语音识别未开通，将使用本机或文字'
    outputChannel.value = ready ? '朗读优先使用云端语音' : '云端语音合成未开通，将使用本机朗读'
  })
})

onBeforeUnmount(() => {
  if (recognition) recognition.stop()
  if (capture) capture.stop().catch(() => {})
  if (synthesisSupported) window.speechSynthesis.cancel()
})
</script>

<template>
  <div class="wx-chat">
    <div class="wx-header">
      <div class="wx-header-info">
        <div class="wx-header-avatar">迹</div>
        <div>
          <div class="wx-header-name">学迹教练</div>
          <div class="wx-header-status">
            <span class="wx-online-dot"></span>
            {{ mode === 'shadow' ? '跟读评测 · ' + goalName : (busy ? '正在思考...' : '连续对话 · ' + goalName) }}
          </div>
        </div>
      </div>
      <div class="wx-mode-switch">
        <button type="button" :class="{ on: mode === 'chat' }" @click="setMode('chat')">问答</button>
        <button type="button" :class="{ on: mode === 'shadow' }" @click="setMode('shadow')">跟读评测</button>
      </div>
      <button v-if="speaking" class="wx-header-btn" @click="stopSpeaking">停止朗读</button>
    </div>
    <p v-if="mode === 'chat'" class="wx-note">会记住这次对话里的追问。{{ inputChannel }}。{{ outputChannel }}。</p>

    <div v-if="mode === 'shadow'" class="shadow-lab">
      <p class="shadow-lead">先听标准音，再开口跟读。句子优先取自今天的课程和错题。</p>
      <div class="shadow-kicker">{{ currentShadow.source || '通用练习' }} · {{ currentShadow.topic }}</div>
      <div class="shadow-text">
        <span
          v-for="(word, index) in shadowWords"
          :key="index"
          :class="{ on: spokenWord === index && word.spoken }"
        >{{ word.raw }}</span>
      </div>
      <div class="shadow-tip">{{ currentShadow.tip }}</div>
      <div class="shadow-actions">
        <button class="btn" type="button" @click="playShadow">听标准音</button>
        <button class="btn btn-solid" type="button" :class="{ active: shadowListening }" @click="startShadowListening">
          {{ shadowListening ? '正在听你说...' : '开始跟读' }}
        </button>
        <button class="btn btn-ghost" type="button" @click="nextShadow">下一句</button>
      </div>
      <div v-if="shadowHeard" class="shadow-heard">识别结果：{{ shadowHeard }}</div>
      <div v-if="shadowResult" class="shadow-result">
        <div class="shadow-score">{{ shadowResult.score }}<span>分</span></div>
        <p>{{ shadowResult.detail }}</p>
        <p v-if="shadowResult.missed.length" class="shadow-miss">未命中：{{ shadowResult.missed.join(', ') }}</p>
      </div>
      <p v-if="!speechSupported" class="wx-note">当前浏览器不支持语音识别，可先听标准音，再用支持麦克风的浏览器完成本环节。</p>
    </div>

    <div v-show="mode === 'chat'" ref="listRef" class="wx-messages">
      <template v-for="(message, index) in messages" :key="index">
        <div v-if="showTime(index)" class="wx-time">{{ message.time }}</div>
        <div class="wx-msg" :class="message.role">
          <div class="wx-avatar" :class="message.role">{{ message.role === 'user' ? '我' : '迹' }}</div>
          <div class="wx-bubble-wrap">
            <div class="wx-bubble">{{ message.text }}</div>
            <div v-if="message.role === 'coach'" class="wx-msg-meta">
              <span v-if="message.source === 'llm'" class="wx-tag wx-tag-llm">AI</span>
              <span v-else-if="message.source === 'rule'" class="wx-tag wx-tag-rule">学习记录</span>
              <button v-if="synthesisSupported" class="wx-read-btn" @click="speak(message.text)">朗读</button>
            </div>
            <div v-if="message.suggestions?.length" class="wx-suggestions">
              <button
                v-for="s in message.suggestions"
                :key="s"
                class="wx-suggestion"
                @click="ask(s)"
              >
                {{ s }}
              </button>
            </div>
          </div>
        </div>
      </template>
      <div v-if="busy" class="wx-msg coach">
        <div class="wx-avatar coach">迹</div>
        <div class="wx-bubble wx-typing">
          <span class="wx-typing-dot"></span>
          <span class="wx-typing-dot"></span>
          <span class="wx-typing-dot"></span>
        </div>
      </div>
    </div>

    <div v-if="mode === 'chat' && showQuick" class="wx-quick-panel">
      <div class="wx-quick-grid">
        <button class="wx-quick-item" @click="ask('今天学什么')">
          <span class="wx-quick-icon">📋</span>
          <span>今天学什么</span>
        </button>
        <button class="wx-quick-item" @click="ask('我的薄弱点是什么')">
          <span class="wx-quick-icon">🎯</span>
          <span>我的薄弱点</span>
        </button>
        <button class="wx-quick-item" @click="ask('考试还剩几天')">
          <span class="wx-quick-icon">⏰</span>
          <span>还剩几天</span>
        </button>
        <button class="wx-quick-item" @click="ask('复习应该怎么安排')">
          <span class="wx-quick-icon">📚</span>
          <span>复习安排</span>
        </button>
        <button class="wx-quick-item" @click="ask('我的错题情况怎么样')">
          <span class="wx-quick-icon">📝</span>
          <span>错题情况</span>
        </button>
        <button class="wx-quick-item" @click="ask('怎么提高学习效率')">
          <span class="wx-quick-icon">💡</span>
          <span>提高效率</span>
        </button>
      </div>
    </div>

    <div v-if="mode === 'chat' && showEmoji" class="wx-emoji-panel">
      <button v-for="e in emojis" :key="e" class="wx-emoji" @click="addEmoji(e)">{{ e }}</button>
    </div>

    <div v-if="mode === 'chat' && !speechSupported" class="wx-note">
      当前浏览器不支持语音识别，可直接输入文字提问；回复仍可朗读。
    </div>

    <div v-if="mode === 'chat'" class="wx-input-bar">
      <button
        class="wx-input-btn"
        :class="{ active: listening }"
        @click="startListening"
        :title="speechSupported ? '语音输入' : '不支持语音'"
      >
        {{ listening ? '■' : '🎙' }}
      </button>
      <input
        ref="textInput"
        v-model="question"
        class="wx-input"
        placeholder="输入消息..."
        @keyup.enter="ask()"
        @focus="closePanels"
      />
      <button class="wx-input-btn" @click="showEmoji = !showEmoji; showQuick = false">😀</button>
      <button class="wx-input-btn" @click="showQuick = !showQuick; showEmoji = false">+</button>
      <button v-if="question.trim()" class="wx-send-btn" :disabled="busy" @click="ask()">发送</button>
    </div>
  </div>
</template>

<style scoped>
.wx-mode-switch {
  display: flex;
  gap: 0;
  margin-left: auto;
  border: 1px solid var(--line, #e5e7eb);
  border-radius: 999px;
  overflow: hidden;
}
.wx-mode-switch button {
  border: 0;
  background: transparent;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
  color: #6b7280;
}
.wx-mode-switch button.on {
  background: #111827;
  color: #fff;
}
.shadow-lab {
  padding: 16px 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.shadow-lead {
  margin: 0;
  font-size: 13px;
  color: #6b7280;
  line-height: 1.55;
}
.shadow-kicker {
  font-size: 12px;
  color: #2563eb;
  font-weight: 600;
}
.shadow-text {
  font-size: 20px;
  line-height: 1.5;
  font-weight: 600;
}
.shadow-tip {
  font-size: 13px;
  color: #4b5563;
}
.shadow-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
}
.shadow-heard,
.shadow-result p,
.shadow-miss {
  font-size: 13px;
  line-height: 1.55;
}
.shadow-result {
  margin-top: 8px;
  padding: 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
}
.shadow-score {
  font-size: 28px;
  font-weight: 700;
  color: #0f766e;
}
.shadow-score span {
  font-size: 13px;
  margin-left: 4px;
  font-weight: 500;
}

.shadow-text span.on {
  background: rgba(47, 111, 85, 0.18);
  border-radius: 4px;
  box-decoration-break: clone;
}
</style>
