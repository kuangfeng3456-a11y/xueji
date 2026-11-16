<script setup>
/**
 * 材料块：阅读文章 / 听力音频。
 *
 * - 阅读：完整英文文章（保留段落），默认展开，长文可折叠。
 * - 听力：只给播放器，不给可读原文——"看原文"按题目要求默认锁住，
 *   交卷后由父组件传 reveal 打开，否则就成了阅读题。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  material: { type: Object, default: null },
  // 交卷后放开听力原文
  reveal: { type: Boolean, default: false },
  // 同一组第几份材料（用于「材料 1 / 材料 2」标注）
  order: { type: Number, default: 1 }
})

const speaking = ref(false)
const rate = ref(1)
const showTranscript = ref(false)
const noVoice = ref(false)
const collapsed = ref(false)

const kind = computed(() => props.material?.kind || '')
const title = computed(() => props.material?.title || (kind.value === 'listening' ? '听力材料' : '阅读文章'))
const paragraphs = computed(() => {
  const content = String(props.material?.content || '')
  return content.split(/\n{2,}|\r\n{2,}/).map((item) => item.trim()).filter(Boolean)
})
const canReveal = computed(() => props.reveal)
const supportsSpeech = computed(() => typeof window !== 'undefined' && 'speechSynthesis' in window)

let utterance = null

function pickVoice() {
  const voices = window.speechSynthesis.getVoices() || []
  const english = voices.filter((voice) => /^en/i.test(voice.lang || ''))
  if (!english.length) return null
  // 优先本地高质量英文语音
  return (
    english.find((voice) => /Google US English|Samantha|Microsoft Aria|Microsoft Zira|Microsoft Jenny/i.test(voice.name)) ||
    english.find((voice) => voice.localService) ||
    english[0]
  )
}

function stop() {
  if (!supportsSpeech.value) return
  window.speechSynthesis.cancel()
  speaking.value = false
}

function play() {
  if (!supportsSpeech.value || !props.material?.audio_script) return
  stop()
  const text = String(props.material.audio_script)
    .replace(/\b([WM]):/g, '. ')
    .replace(/\s+/g, ' ')
    .trim()
  utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = 'en-US'
  utterance.rate = rate.value
  const voice = pickVoice()
  if (voice) {
    utterance.voice = voice
  } else {
    noVoice.value = true
  }
  utterance.onend = () => {
    speaking.value = false
  }
  utterance.onerror = () => {
    speaking.value = false
    noVoice.value = true
  }
  speaking.value = true
  window.speechSynthesis.speak(utterance)
}

function replay() {
  play()
}

function setRate(value) {
  rate.value = value
  if (speaking.value) play()
}

watch(
  () => props.material,
  () => {
    stop()
    showTranscript.value = false
  }
)

onBeforeUnmount(stop)
</script>

<template>
  <div v-if="material" class="qm">
    <!-- 阅读：文章正文 -->
    <div v-if="kind === 'passage'" class="qm-passage">
      <div class="qm-head">
        <span class="qm-tag">Reading</span>
        <span class="qm-title">{{ title }}</span>
        <span class="qm-meta">{{ material.word_count }} 词</span>
        <button class="qm-mini" @click="collapsed = !collapsed">
          {{ collapsed ? '展开' : '收起' }}
        </button>
      </div>
      <div v-show="!collapsed" class="qm-body">
        <p v-for="(item, index) in paragraphs" :key="index">{{ item }}</p>
      </div>
    </div>

    <!-- 听力：播放器 + 锁定原文 -->
    <div v-else-if="kind === 'listening'" class="qm-listening">
      <div class="qm-head">
        <span class="qm-tag qm-tag-listen">Listening</span>
        <span class="qm-title">
          {{ order > 1 ? `材料 ${order} · ` : '' }}{{ title }}
        </span>
        <span class="qm-meta">{{ material.word_count }} 词</span>
      </div>
      <div class="qm-player">
        <button class="qm-play" :disabled="!supportsSpeech" @click="speaking ? stop() : play()">
          {{ speaking ? '暂停' : '播放' }}
        </button>
        <button class="qm-btn" :disabled="!supportsSpeech" @click="replay">重听</button>
        <div class="qm-rate">
          <button
            v-for="item in [0.8, 1, 1.2]"
            :key="item"
            class="qm-rate-btn"
            :class="{ active: rate === item }"
            @click="setRate(item)"
          >
            {{ item }}x
          </button>
        </div>
        <span v-if="speaking" class="qm-playing">正在播放…</span>
      </div>
      <div v-if="!supportsSpeech" class="qm-warn">
        当前浏览器不支持语音合成，无法播放听力音频。可先查看原文作答，或换用 Chrome / Edge。
      </div>
      <div v-else-if="noVoice" class="qm-warn">
        系统未安装英文语音包，朗读可能不准。可在系统「语音」设置里安装英文语音后重试。
      </div>
      <div class="qm-transcript">
        <button v-if="canReveal" class="qm-mini" @click="showTranscript = !showTranscript">
          {{ showTranscript ? '隐藏听力原文' : '查看听力原文' }}
        </button>
        <span v-else class="qm-lock">听力原文将在交卷后开放</span>
        <div v-if="canReveal && showTranscript" class="qm-body qm-transcript-body">
          {{ material.transcript || material.audio_script }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.qm {
  margin-bottom: 14px;
}
.qm-passage,
.qm-listening {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface-2, #f8fafc);
  padding: 12px 14px;
}
.qm-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.qm-tag {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: #1d4ed8;
  background: #e0ecff;
  border-radius: 5px;
  padding: 2px 6px;
}
.qm-tag-listen {
  color: #7c2d12;
  background: #ffedd5;
}
.qm-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.qm-meta {
  font-size: 11px;
  color: var(--muted);
}
.qm-mini {
  margin-left: auto;
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--muted);
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  cursor: pointer;
}
.qm-mini:hover {
  color: var(--brand);
  border-color: var(--brand);
}
.qm-body {
  font-size: 13px;
  line-height: 1.85;
  color: var(--text);
  max-height: 320px;
  overflow: auto;
}
.qm-body p {
  margin: 0 0 10px;
}
.qm-body p:last-child {
  margin-bottom: 0;
}
.qm-player {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.qm-play {
  border: none;
  background: var(--brand);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  padding: 7px 16px;
  border-radius: 8px;
  cursor: pointer;
}
.qm-play:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.qm-btn {
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--text);
  font-size: 12px;
  padding: 6px 12px;
  border-radius: 8px;
  cursor: pointer;
}
.qm-rate {
  display: flex;
  gap: 2px;
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
}
.qm-rate-btn {
  border: none;
  background: var(--surface);
  color: var(--muted);
  font-size: 11px;
  padding: 6px 8px;
  cursor: pointer;
}
.qm-rate-btn.active {
  background: #e0ecff;
  color: #1d4ed8;
  font-weight: 600;
}
.qm-playing {
  font-size: 11px;
  color: var(--brand);
}
.qm-warn {
  margin-top: 8px;
  font-size: 11px;
  color: #b45309;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 8px;
  padding: 6px 9px;
}
.qm-transcript {
  margin-top: 8px;
}
.qm-lock {
  font-size: 11px;
  color: var(--muted);
}
.qm-transcript-body {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--line);
  white-space: pre-wrap;
}
</style>
