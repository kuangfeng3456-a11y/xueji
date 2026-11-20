<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { store, notify } from '../store'
import { confirmAction } from '../confirm'
import AppSelect from '../components/AppSelect.vue'
import { cloudSpeechReady, startRecorder } from '../voiceInput'

const router = useRouter()
const points = ref([])
const mistakes = ref([])
const mastery = ref([])
const summary = ref(null)
const loading = ref(true)
const submitting = ref(false)
const filter = ref('')
const result = ref(null)
const imageUrl = ref('')
const uploading = ref(false)
const dictating = ref(false)
const dictateNote = ref('可拍照、从相册选择，或用语音说出题干。文字识别或云端语音未开通时，请手动核对。')
let dictateCapture = null
const photoInput = ref(null)
const cameraOpen = ref(false)
const cameraBusy = ref(false)
const cameraVideo = ref(null)
const trace = ref(null)
const traceLoading = ref(false)
const traceMistake = ref(null)
let cameraStream = null

const form = reactive({
  question: '',
  user_answer: '',
  correct_answer: '',
  kp_id: ''
})

const categoryLabel = {
  concept: '概念不清',
  method: '方法不会',
  careless: '粗心',
  time: '时间不够'
}

const exporting = ref(false)

async function exportMistakes() {
  if (!store.currentGoalId) return
  exporting.value = true
  try {
    await api.exportMistakesFile(store.currentGoalId)
    notify('错题本已导出 Word（页眉含 AI 标识）')
  } catch (e) {
    notify(e.message, true)
  } finally {
    exporting.value = false
  }
}

function printMistakes() {
  const rows = filteredMistakes.value
    .map(
      (item) => `<tr>
        <td>${escapeHtml(item.question)}</td>
        <td>${escapeHtml(item.user_answer || '')}</td>
        <td>${escapeHtml(item.correct_answer || '')}</td>
        <td>${escapeHtml(item.category_label || '')}</td>
        <td>${escapeHtml(item.kp_name || '')}</td>
      </tr>`
    )
    .join('')
  const win = window.open('', '_blank', 'width=900,height=700')
  if (!win) {
    notify('浏览器拦截了打印窗口，请允许弹窗', true)
    return
  }
  win.document.write(`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8" />
    <title>错题本打印</title>
    <style>
      body { font-family: "Songti SC", "Microsoft YaHei", serif; padding: 24px; color: #1b1917; }
      h1 { font-size: 22px; margin: 0 0 6px; }
      .meta { color: #7c7568; font-size: 12px; margin-bottom: 14px; }
      table { width: 100%; border-collapse: collapse; font-size: 12px; }
      th, td { border: 1px solid #d8d2c4; padding: 6px 8px; text-align: left; vertical-align: top; }
      th { background: #f5f2ea; }
      .ai { margin-top: 16px; color: #7c7568; font-size: 11px; }
    </style></head><body>
    <h1>错题本</h1>
    <div class="meta">共 ${rows ? filteredMistakes.value.length : 0} 道 · 打印于 ${new Date().toLocaleString()}</div>
    <table><thead><tr><th>题目</th><th>我的答案</th><th>正确答案</th><th>错因</th><th>知识点</th></tr></thead>
    <tbody>${rows}</tbody></table>
    <div class="ai">AI 辅助生成 · 学迹 AI 学习教练 · 本文件包含 AI 辅助内容，仅供参考</div>
    </body></html>`)
  win.document.close()
  win.focus()
  win.print()
}

function escapeHtml(text) {
  return String(text || '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]))
}

const filteredMistakes = computed(() => {
  if (!filter.value) return mistakes.value
  return mistakes.value.filter((item) => item.category === filter.value)
})

const kpSelectOptions = computed(() => [
  { value: '', label: '不关联（不更新掌握度）' },
  ...pointOptions.value.map((point) => ({ value: point.id, label: point.name }))
])

const pointOptions = computed(() => {
  const ids = new Set(points.value.map((p) => p.id))
  return points.value.filter((p) => p.parent_id === null || !ids.has(p.parent_id))
})

async function load() {
  if (!store.currentGoalId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const [kp, ms, ma, sm] = await Promise.all([
      api.knowledgePoints(store.currentGoalId),
      api.mistakes(store.currentGoalId),
      api.mastery(store.currentGoalId),
      api.mistakeSummary(store.currentGoalId).catch(() => null)
    ])
    points.value = kp
    mistakes.value = ms
    mastery.value = ma
    summary.value = sm
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function uploadPhoto(event) {
  const file = event.target.files?.[0]
  if (!file) return
  if (!store.currentGoalId) {
    notify('请先创建考试目标', true)
    return
  }
  uploading.value = true
  try {
    const data = new FormData()
    data.append('file', file)
    const uploaded = await api.uploadMistakePhoto(store.currentGoalId, data)
    imageUrl.value = uploaded.url
    // 文档 D3：错题拍照优先走华为云 OCR；未配置时如实降级为手动录入
    const ocrForm = new FormData()
    ocrForm.append('file', file)
    ocrForm.append('kind', 'general')
    try {
      const ocr = await api.ocrExtract(ocrForm)
      if (ocr && ocr.status === 'ok' && (ocr.text || '').trim()) {
        form.question = ocr.text.trim().slice(0, 2000)
        const regions = ocr.detection?.regions || []
        notify(regions.length ? '已按题目区域识别，请核对后提交' : '已识别题干，请核对后提交')
      } else if (ocr && (ocr.status === 'not_configured' || ocr.status === 'sdk_missing' || ocr.status === 'not_subscribed')) {
        notify('文字识别未开通，请手动填写题干')
      } else {
        notify('这次没有识别出文字，请手动填写题干')
      }
    } catch (e) {
      notify('文字识别暂不可用，请手动填写题干')
    }
  } catch (e) {
    notify(e.message, true)
  } finally {
    uploading.value = false
    if (photoInput.value) photoInput.value.value = ''
  }
}

function fillQuestion(text) {
  const clean = String(text || '').trim()
  if (!clean) return
  form.question = clean.slice(0, 2000)
}

async function dictateQuestion() {
  if (dictating.value && dictateCapture) {
    const pending = dictateCapture
    dictateCapture = null
    dictating.value = false
    const blob = await pending.stop()
    const formData = new FormData()
    formData.append('file', blob, 'speech.webm')
    formData.append('audio_format', (blob.type || '').includes('wav') ? 'wav' : 'webm')
    try {
      const heard = await api.sisRecognize(formData)
      if (heard.status === 'ok' && heard.text) {
        fillQuestion(heard.text)
        dictateNote.value = '已用云端语音填入题干，请核对。'
        return
      }
      dictateNote.value = heard.fallback_label || '云端语音识别不可用，请手动填写题干'
      notify(dictateNote.value, true)
    } catch (e) {
      notify('语音识别失败，请手动填写题干', true)
    }
    return
  }
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
  const cloudReady = await cloudSpeechReady(api)
  if (cloudReady) {
    try {
      dictateCapture = await startRecorder()
      dictateCapture.start()
      dictating.value = true
      dictateNote.value = '正在录音，再点一次结束并识别'
      return
    } catch (e) {
      dictateCapture = null
    }
  }
  if (!SpeechRecognition) {
    dictateNote.value = '当前环境不能语音输入，请手动填写题干'
    notify(dictateNote.value, true)
    return
  }
  const recognition = new SpeechRecognition()
  recognition.lang = 'zh-CN'
  recognition.interimResults = false
  recognition.onresult = (event) => {
    fillQuestion(event.results?.[0]?.[0]?.transcript || '')
    dictateNote.value = cloudReady ? '本机语音已填入题干，请核对' : '云端语音未开通，已改用本机识别，请核对题干'
    dictating.value = false
  }
  recognition.onerror = () => {
    dictating.value = false
    dictateNote.value = '语音识别失败，请手动填写题干'
  }
  recognition.onend = () => {
    dictating.value = false
  }
  dictating.value = true
  dictateNote.value = '正在聆听，请说出题干'
  recognition.start()
}

async function keepMistakeCard() {
  const kpId = result.value?.diagnosis?.kp_id
  if (!kpId) return
  try {
    const data = await api.enqueueFlashcard(store.currentGoalId, { kp_id: kpId })
    notify(data.detail || '已加入今天的复习')
  } catch (e) {
    notify(e.message, true)
  }
}

async function submit() {
  if (!form.question.trim()) {
    notify('请填写题目', true)
    return
  }
  submitting.value = true
  try {
    const payload = {
      question: form.question.trim(),
      user_answer: form.user_answer.trim(),
      correct_answer: form.correct_answer.trim(),
      kp_id: form.kp_id ? Number(form.kp_id) : null,
      source: imageUrl.value ? 'photo' : 'text',
      image_url: imageUrl.value || null
    }
    const data = await api.createMistake(store.currentGoalId, payload)
    result.value = data
    form.question = ''
    form.user_answer = ''
    form.correct_answer = ''
    imageUrl.value = ''
    notify(`已归因：${data.diagnosis.category_label}（${data.diagnosis.engine === 'llm' ? '大模型' : '规则引擎'}）`)
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    submitting.value = false
  }
}

async function answer(point, correct) {
  try {
    const data = await api.answer(store.currentGoalId, point.kp_id, correct)
    notify(`${point.kp_name} 掌握度更新为 ${Math.round(data.value * 100)}%`)
    await load()
  } catch (e) {
    notify(e.message, true)
  }
}

async function remove(item) {
  const ok = await confirmAction({
    title: '删除错题',
    message: '确定删除这道错题吗？',
    detail: '删除后该题不再参与错因归因与复习排期。',
    confirmText: '删除',
    danger: true
  })
  if (!ok) return
  try {
    await api.deleteMistake(store.currentGoalId, item.id)
    notify('已删除')
    await load()
  } catch (e) {
    notify(e.message, true)
  }
}

watch(() => store.currentGoalId, load, { immediate: true })

async function openCameraCapture() {
  if (!navigator.mediaDevices?.getUserMedia) {
    notify('当前浏览器不支持摄像头，请使用文件选择', true)
    return
  }
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 960 }, height: { ideal: 720 } },
      audio: false
    })
    cameraOpen.value = true
    await nextTick()
    if (cameraVideo.value) {
      cameraVideo.value.srcObject = cameraStream
      const playPromise = cameraVideo.value.play?.()
      if (playPromise && playPromise.catch) playPromise.catch(() => {})
    }
  } catch (e) {
    notify('摄像头开启失败：' + (e.message || '请检查浏览器权限'), true)
  }
}

function closeCameraCapture() {
  if (cameraStream) {
    cameraStream.getTracks().forEach((track) => track.stop())
    cameraStream = null
  }
  cameraOpen.value = false
}

async function capturePhoto() {
  const video = cameraVideo.value
  if (!video?.videoWidth) {
    notify('摄像头尚未就绪，请稍候再拍', true)
    return
  }
  cameraBusy.value = true
  try {
    const width = 960
    const height = Math.round((width * video.videoHeight) / video.videoWidth)
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    canvas.getContext('2d').drawImage(video, 0, 0, width, height)
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.85))
    if (!blob) throw new Error('拍照失败，请重试')
    const formData = new FormData()
    formData.append('file', new File([blob], 'mistake.jpg', { type: 'image/jpeg' }))
    const uploaded = await api.uploadMistakePhoto(store.currentGoalId, formData)
    imageUrl.value = uploaded.url
    notify('已拍照并上传，可继续补充题干')
    closeCameraCapture()
  } catch (e) {
    notify(e.message, true)
  } finally {
    cameraBusy.value = false
  }
}

async function openTrace(item) {
  traceMistake.value = item
  trace.value = null
  traceLoading.value = true
  try {
    trace.value = await api.createTrace(item.id)
  } catch (e) {
    notify(e.message, true)
  } finally {
    traceLoading.value = false
  }
}

function closeTrace() {
  traceMistake.value = null
  trace.value = null
}

onBeforeUnmount(() => {
  closeCameraCapture()
  if (dictateCapture) dictateCapture.stop().catch(() => {})
})
const mistakeStats = computed(() => {
  const localCats = { concept: 0, method: 0, careless: 0, time: 0 }
  for (const item of mistakes.value) {
    if (localCats[item.category] !== undefined) localCats[item.category] += 1
  }
  const values = mastery.value.map((item) => item.value)
  const localAvg = values.length
    ? Math.round((values.reduce((sum, value) => sum + value, 0) / values.length) * 100)
    : 0

  const s = summary.value
  if (s) {
    // 全量口径来自接口；列表只是最近若干条，不能当总数用
    return {
      total: s.total ?? localCats.concept + localCats.method + localCats.careless + localCats.time,
      cats: { ...localCats, ...(s.by_category || {}) },
      avgMastery: s.avg_mastery == null ? 0 : Math.round(s.avg_mastery * 100),
      weak: s.weak_points ?? values.filter((value) => value < 0.5).length,
      points: s.point_total ?? points.value.length,
      last7: s.last_7_days ?? 0,
      listed: mistakes.value.length,
      complete: true
    }
  }
  return {
    total: mistakes.value.length,
    cats: localCats,
    avgMastery: localAvg,
    weak: values.filter((value) => value < 0.5).length,
    points: points.value.length,
    last7: 0,
    listed: mistakes.value.length,
    complete: false
  }
})
</script>

<template>
  <div v-if="!store.currentGoalId" class="empty">
    还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建目标与知识点。
  </div>

  <div v-else class="split">
    <div class="stack">
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">录入错题</div>
            <div class="card-sub">提交后自动归因、更新掌握度，并触发一次动态重排</div>
          </div>
        </div>

        <div class="field">
          <label>题目</label>
          <textarea v-model="form.question" class="textarea" placeholder="粘贴题干，或拍照、语音输入后核对"></textarea>
          <div class="row" style="margin-top: 8px">
            <button type="button" class="btn btn-ghost btn-sm" @click="dictateQuestion">
              {{ dictating ? '结束并识别' : '语音输入题干' }}
            </button>
          </div>
          <div class="small muted" style="margin-top: 4px">{{ dictateNote }}</div>
        </div>

        <div class="photo-upload">
          <div v-if="imageUrl" class="photo-preview">
            <img :src="imageUrl" alt="错题图片预览" />
            <button class="btn btn-ghost btn-sm" @click="imageUrl = ''">移除图片</button>
          </div>
          <div class="row">
            <button class="btn btn-ghost btn-sm" @click="openCameraCapture">用摄像头拍照</button>
            <label class="photo-pick" style="flex: 1">
              <input ref="photoInput" type="file" accept="image/jpeg,image/png,image/webp" @change="uploadPhoto" />
              <span class="photo-pick-icon">＋</span>
              <span>{{ uploading ? '上传中...' : '从相册选择' }}</span>
            </label>
          </div>
          <div class="small muted" style="margin-top: 4px">
            拍照或从相册选择后，已开通文字识别时会填入题干；未开通时请手动填写。图片会留在错题记录里。
          </div>
        </div>

        <div v-if="cameraOpen" class="modal-mask" @click.self="closeCameraCapture">
          <div class="modal camera-modal">
            <div class="card-head">
              <div>
                <div class="card-title">用摄像头拍错题</div>
                <div class="card-sub">对准题目，拍下后自动上传</div>
              </div>
              <button class="btn btn-ghost btn-sm" @click="closeCameraCapture">关闭</button>
            </div>
            <video ref="cameraVideo" class="camera-video" autoplay muted playsinline></video>
            <button class="btn btn-block" :disabled="cameraBusy" style="margin-top: 14px" @click="capturePhoto">
              {{ cameraBusy ? '上传中...' : '拍下这道题' }}
            </button>
          </div>
        </div>
        <div class="grid grid-2" style="gap: 12px">
          <div class="field">
            <label>我的答案</label>
            <input v-model="form.user_answer" class="input" placeholder="写错也没关系，留空代表没时间作答" />
          </div>
          <div class="field">
            <label>正确答案</label>
            <input v-model="form.correct_answer" class="input" placeholder="便于判断粗心还是方法不会" />
          </div>
        </div>
        <div class="field">
          <label>关联知识点</label>
          <AppSelect v-model="form.kp_id" :options="kpSelectOptions" placeholder="不关联（不更新掌握度）" />
        </div>

        <button class="btn btn-block" :disabled="submitting" @click="submit">
          {{ submitting ? '归因与重排中...' : '提交并智能归因' }}
        </button>
      </div>

      <div v-if="result" class="card">
        <div class="card-head">
          <div>
            <div class="card-title">本次归因结果</div>
            <div class="card-sub">根据这道题的作答给出错因和补法</div>
          </div>
          <span class="tag" :class="`tag-${result.diagnosis.category}`">{{ result.diagnosis.category_label }}</span>
        </div>
        <div class="task-reason" style="margin-top: 0">{{ result.diagnosis.suggestion }}</div>
        <div class="row" style="gap: 8px; margin-top: 10px; flex-wrap: wrap">
          <button class="btn btn-sm" type="button" @click="router.push({ path: '/today', query: { tab: 'voice', q: `这道错题怎么补：${form.question}` } })">追问教练</button>
          <button v-if="result.diagnosis.kp_id" class="btn btn-ghost btn-sm" type="button" @click="keepMistakeCard">加入今日复习</button>
          <button class="btn btn-ghost btn-sm" type="button" @click="router.push('/today')">回到今日</button>
        </div>
        <div v-if="result.diagnosis.mastery !== null" class="small muted" style="margin-top: 10px">
          该知识点掌握度已更新为 {{ Math.round(result.diagnosis.mastery * 100) }}%
        </div>

        <div v-if="result.replan" style="margin-top: 14px">
          <div class="small muted" style="margin-bottom: 8px">自动重排</div>
          <div class="stack">
            <div v-for="(change, index) in result.replan.changes" :key="index" class="task-reason" style="margin-top: 0">
              {{ change.detail }}
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">错题本</div>
            <div class="card-sub">按错因归纳，共 {{ mistakes.length }} 道</div>
          </div>
          <div class="row" style="gap: 8px">
            <button class="btn btn-ghost btn-sm" :disabled="!mistakes.length" @click="printMistakes">打印</button>
            <button class="btn btn-ghost btn-sm" :disabled="!mistakes.length || exporting" @click="exportMistakes">
              {{ exporting ? '导出中…' : '导出 Word' }}
            </button>
          </div>
        </div>
        <div class="chip-list" style="margin-bottom: 14px">
          <button class="chip" :class="{ active: filter === '' }" @click="filter = ''">全部</button>
          <button
            v-for="(label, key) in categoryLabel"
            :key="key"
            class="chip"
            :class="{ active: filter === key }"
            @click="filter = key"
          >
            {{ label }}
          </button>
        </div>

        <div v-if="!filteredMistakes.length" class="empty">这个分类下还没有错题。</div>
        <div v-else class="stack">
          <div v-for="item in filteredMistakes" :key="item.id" class="task">
            <div class="task-main">
              <div class="task-title" style="font-weight: 500">{{ item.question }}</div>
              <div class="task-meta">
                <span class="tag" :class="`tag-${item.category}`">{{ item.category_label }}</span>
                <span class="small muted">{{ item.kp_name || '未关联知识点' }}</span>
                <span class="small muted">{{ item.created_at.slice(0, 10) }}</span>
              </div>
              <div class="small muted" style="margin-top: 6px">
                我的答案：{{ item.user_answer || '未作答' }}　正确答案：{{ item.correct_answer || '未提供' }}
              </div>
              <img v-if="item.image_url" :src="item.image_url" class="mistake-thumb" alt="错题图片" />
              <div class="task-reason">{{ item.suggestion }}</div>
            </div>
            <div class="task-actions">
              <button class="btn btn-ghost btn-sm" @click="openTrace(item)">回放思维路径</button>
              <button class="btn btn-danger btn-sm" @click="remove(item)">删除</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="stack">
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">掌握度</div>
            <div class="card-sub">答对 +30% 向 1 靠近，答错向 0 靠近，并重置复习间隔</div>
          </div>
        </div>
        <div v-if="!mastery.length" class="empty">导入资料后这里会出现知识点。</div>
        <div v-else class="stack">
          <div v-for="point in mastery" :key="point.kp_id">
            <div class="row-between small">
              <span>{{ point.kp_name }}</span>
              <b>{{ Math.round(point.value * 100) }}%</b>
            </div>
            <div class="bar" style="margin: 5px 0 7px">
              <i :style="{ width: Math.max(point.value * 100, 2) + '%' }"></i>
            </div>
            <div class="row-between">
              <span class="small muted">
                {{ point.next_review_at ? '下次复习 ' + point.next_review_at : '尚未安排复习' }}
                <span v-if="point.delta_7d"> · 7 天 {{ point.delta_7d > 0 ? '+' : '' }}{{ point.delta_7d }}</span>
              </span>
              <span class="row" style="gap: 4px">
                <button class="btn btn-teal btn-sm" @click="answer(point, true)">答对</button>
                <button class="btn btn-ghost btn-sm" @click="answer(point, false)">答错</button>
              </span>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">错题与掌握度概览</div>
          <div class="card-sub">
            错题总量、四类错因分布与掌握度状况
            <template v-if="mistakeStats.complete"> · 最近 7 天新增 {{ mistakeStats.last7 }} 道</template>
          </div>
        </div>
      </div>
      <div class="grid grid-4" style="margin-top: 10px">
        <div class="stat">
          <div class="stat-label">错题总数</div>
          <div class="stat-value">{{ mistakeStats.total }}</div>
          <div class="stat-note">关联 {{ mistakeStats.points }} 个知识点</div>
        </div>
        <div class="stat">
          <div class="stat-label">平均掌握度</div>
          <div class="stat-value">{{ mistakeStats.avgMastery }}%</div>
          <div class="stat-note">薄弱 {{ mistakeStats.weak }} 个</div>
        </div>
        <div class="stat">
          <div class="stat-label">概念 / 方法</div>
          <div class="stat-value" style="font-size: 18px">{{ mistakeStats.cats.concept }} / {{ mistakeStats.cats.method }}</div>
          <div class="stat-note">概念不清 / 方法不会</div>
        </div>
        <div class="stat">
          <div class="stat-label">粗心 / 时间</div>
          <div class="stat-value" style="font-size: 18px">{{ mistakeStats.cats.careless }} / {{ mistakeStats.cats.time }}</div>
          <div class="stat-note">粗心 / 时间不够</div>
        </div>
      </div>
      <div
        v-if="mistakeStats.complete && mistakeStats.total > mistakeStats.listed"
        class="small muted"
        style="margin-top: 8px"
      >
        列表仅显示最近 {{ mistakeStats.listed }} 道，以上四项统计为全量口径。
      </div>
      </div>
    </div>

    <div v-if="traceMistake" class="modal-mask" @click.self="closeTrace">
      <div class="modal knowledge-modal">
        <div class="card-head">
          <div>
            <div class="card-title">思维路径回放</div>
            <div class="card-sub">{{ traceMistake.question.slice(0, 48) }}</div>
          </div>
          <button class="btn btn-ghost btn-sm" @click="closeTrace">关闭</button>
        </div>

        <div v-if="traceLoading" class="empty">AI 正在拆解这道题的思维步骤...</div>

        <template v-else-if="trace">
          <div class="trace-summary">{{ trace.summary }}</div>
          <div class="trace-steps">
            <div
              v-for="(step, index) in trace.steps"
              :key="index"
              class="trace-step"
              :class="{ error: index === trace.error_step }"
            >
              <div class="trace-index">{{ index + 1 }}</div>
              <div style="flex: 1">
                <b>{{ step.thought }}</b>
                <div class="small muted">{{ step.issue || step.verdict }}</div>
              </div>
              <span class="tag" :class="step.verdict === '正确' ? 'tag-review' : step.verdict === '缺失' ? 'tag-pending' : 'tag-skipped'">
                {{ step.verdict }}
              </span>
            </div>
          </div>
          <div class="small muted" style="margin-top: 10px">
            来源：{{ trace.engine === 'llm' ? 'DeepSeek 思维回放' : '规则思维回放' }} · 已写入学习证据链
          </div>
        </template>
      </div>
    </div>
  </div>
</template>