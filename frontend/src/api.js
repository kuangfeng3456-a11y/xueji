const API_BASE =
  (typeof window !== 'undefined' && window.__XUEJI_API_BASE__) || '/api'

/** 常规请求超时；出题/方案生成这类长任务在调用处单独放宽。 */
const DEFAULT_TIMEOUT = 30000
/** 长任务（模考、方案重建、多智能体评审）默认超时。 */
export const LONG_TIMEOUT = 180000

/** 在途请求控制器：退出登录时统一取消，避免上一个账号的数据回写到新会话。 */
const inflight = new Set()

export function cancelPendingRequests() {
  for (const controller of inflight) {
    try {
      controller.abort()
    } catch (e) {
      /* 已结束的请求忽略 */
    }
  }
  inflight.clear()
}

function authToken() {
  const raw = localStorage.getItem('xueji_session') || sessionStorage.getItem('xueji_session')
  if (!raw) return ''
  try {
    return JSON.parse(raw).token || ''
  } catch (e) {
    return ''
  }
}

function clearExpiredSession() {
  localStorage.removeItem('xueji_session')
  sessionStorage.removeItem('xueji_session')
  if (!location.hash.includes('/login')) location.hash = '#/login'
}

export function apiUrl(path) {
  const route = String(path || '')
  if (/^https?:\/\//i.test(route)) return route
  const base = String(API_BASE).replace(/\/+$/, '')
  const normalizedRoute = route.startsWith('/api/') ? route.slice(4) : route
  return `${base}${normalizedRoute.startsWith('/') ? normalizedRoute : `/${normalizedRoute}`}`
}

export async function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {})
  const token = authToken()
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
    // 部分网关会改写 Authorization 头，附带一个自定义头作双保险
    if (!headers.has('X-Auth-Token')) headers.set('X-Auth-Token', token)
  }

  const { timeout = DEFAULT_TIMEOUT, signal: externalSignal, ...rest } = options
  const controller = new AbortController()
  inflight.add(controller)

  let timedOut = false
  const timer =
    timeout > 0
      ? setTimeout(() => {
          timedOut = true
          controller.abort()
        }, timeout)
      : null

  const forwardAbort = () => controller.abort()
  if (externalSignal) {
    if (externalSignal.aborted) controller.abort()
    else externalSignal.addEventListener('abort', forwardAbort, { once: true })
  }

  let response
  try {
    response = await fetch(apiUrl(path), { ...rest, headers, signal: controller.signal })
  } catch (error) {
    if (error?.name === 'AbortError') {
      if (timedOut) {
        throw new Error(`请求超时（${Math.round(timeout / 1000)} 秒），请检查网络后重试`)
      }
      throw new Error('请求已取消')
    }
    throw new Error('无法连接后端服务，请确认已启动 API')
  } finally {
    if (timer) clearTimeout(timer)
    if (externalSignal) externalSignal.removeEventListener('abort', forwardAbort)
    inflight.delete(controller)
  }

  if (response.status === 401) {
    clearExpiredSession()
    throw new Error('登录状态已失效，请重新登录')
  }
  return response
}

async function responseError(response, fallback) {
  let message = fallback
  try {
    const data = await response.json()
    if (typeof data.detail === 'string') message = data.detail
    else if (Array.isArray(data.detail) && data.detail.length) {
      message = data.detail.map((item) => item.msg).join('；')
    }
  } catch (e) {
    /* ignore non-JSON error bodies */
  }
  return message
}

async function request(path, options = {}) {
  const opts = { method: options.method || 'GET', headers: { ...(options.headers || {}) } }
  if (options.timeout) opts.timeout = options.timeout
  if (options.signal) opts.signal = options.signal
  if (options.body instanceof FormData) {
    opts.body = options.body
  } else if (options.body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(options.body)
  }

  const resp = await apiFetch(path, opts)

  if (!resp.ok) {
    throw new Error(await responseError(resp, `请求失败（${resp.status}）`))
  }

  if (resp.status === 204) return null
  const text = await resp.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch (error) {
    throw new Error('服务返回了无法识别的数据，请稍后重试')
  }
}

async function downloadFile(path, filename) {
  const resp = await apiFetch(path, { timeout: LONG_TIMEOUT })
  if (!resp.ok) {
    throw new Error(await responseError(resp, `导出失败（${resp.status}）`))
  }
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  return true
}

export const api = {
  register: (body) => request('/auth/register', { method: 'POST', body }),
  login: (body) => request('/auth/login', { method: 'POST', body }),
  logout: () => request('/auth/logout', { method: 'POST' }),
  me: () => request('/auth/me'),
  updateProfile: (body) => request('/auth/me', { method: 'PATCH', body }),
  changePassword: (body) => request('/auth/me/password', { method: 'POST', body }),
  exportData: () => request('/auth/me/export'),
  deleteAccount: () => request('/auth/me', { method: 'DELETE' }),

  // C3 实施意图微承诺
  commitmentsToday: (goalId, day) =>
    request(`/commitments/today?goal_id=${goalId}${day ? `&day=${day}` : ''}`),
  commitmentSuggestions: (goalId) => request(`/commitments/suggestions?goal_id=${goalId}`),
  createCommitment: (body) => request('/commitments', { method: 'POST', body }),
  fulfillCommitment: (id, note = '') =>
    request(`/commitments/${id}/fulfill`, { method: 'POST', body: { note } }),
  cancelCommitment: (id) => request(`/commitments/${id}/cancel`, { method: 'POST', body: {} }),
  commitmentStats: (goalId) => request(`/commitments/stats?goal_id=${goalId}`),

  // 多设备会话
  sessions: () => request('/auth/sessions'),
  revokeSession: (id) => request(`/auth/sessions/${id}`, { method: 'DELETE' }),
  revokeOtherSessions: () => request('/auth/sessions/revoke-others', { method: 'POST' }),

  // 账号找回：密保问题与一次性恢复码
  securityOverview: () => request('/auth/security'),
  questionBank: () => request('/auth/security/questions'),
  saveSecurityQuestions: (body) => request('/auth/security/questions', { method: 'PUT', body }),
  issueRecoveryCodes: (body) => request('/auth/security/codes', { method: 'POST', body }),
  recoveryOptions: (username) =>
    request(`/auth/recovery/options?username=${encodeURIComponent(username)}`),
  recoveryVerify: (body) => request('/auth/recovery/verify', { method: 'POST', body }),
  recoveryReset: (body) => request('/auth/recovery/reset', { method: 'POST', body }),

  goals: () => request('/goals'),
  createGoal: (body) => request('/goals', { method: 'POST', body }),
  updateGoal: (id, body) => request(`/goals/${id}`, { method: 'PUT', body }),
  deleteGoal: (id) => request(`/goals/${id}`, { method: 'DELETE' }),

  knowledgePoints: (goalId) => request(`/goals/${goalId}/knowledge-points`),
  createKnowledgePoint: (goalId, body) => request(`/goals/${goalId}/knowledge-points`, { method: 'POST', body }),
  deleteKnowledgePoint: (goalId, kpId) =>
    request(`/goals/${goalId}/knowledge-points/${kpId}`, { method: 'DELETE' }),
  importText: (goalId, body) => request(`/goals/${goalId}/materials/text`, { method: 'POST', body }),
  importFile: (goalId, formData) =>
    request(`/goals/${goalId}/materials/upload`, { method: 'POST', body: formData, timeout: 60000 }),
  materials: (goalId) => request(`/goals/${goalId}/materials`),

  generatePlan: (goalId, body) => request(`/goals/${goalId}/plan`, { method: 'POST', body }),
  tasks: (goalId, params = {}) => {
    const query = new URLSearchParams()
    if (params.start) query.set('start', params.start)
    if (params.end) query.set('end', params.end)
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return request(`/goals/${goalId}/tasks${suffix}`)
  },
  updateTask: (goalId, taskId, status, extra = {}) =>
    request(`/goals/tasks/${taskId}`, { method: 'PATCH', body: { status, ...extra } }),
  replan: (goalId, trigger = 'manual') =>
    request(`/goals/${goalId}/replan?trigger=${encodeURIComponent(trigger)}`, { method: 'POST' }),
  replanLogs: (goalId) => request(`/goals/${goalId}/replan-logs`),

  createMistake: (goalId, body) => request(`/goals/${goalId}/mistakes`, { method: 'POST', body }),
  mistakes: (goalId, category = '') =>
    request(`/goals/${goalId}/mistakes${category ? `?category=${category}` : ''}`),
  mistakeSummary: (goalId) => request(`/goals/${goalId}/mistakes/summary`),
  focusSummary: (goalId) => request(`/goals/${goalId}/focus/summary`),
  deleteMistake: (goalId, mistakeId) => request(`/goals/mistakes/${mistakeId}`, { method: 'DELETE' }),
  mastery: (goalId) => request(`/goals/${goalId}/mastery`),
  answer: (goalId, kpId, correct) =>
    request(`/goals/${goalId}/mastery/${kpId}/answer`, { method: 'POST', body: { correct } }),

  reports: (goalId) => request(`/goals/${goalId}/reports`),
  createReport: (goalId) => request(`/goals/${goalId}/reports`, { method: 'POST' }),
  latestReport: (goalId) => request(`/goals/${goalId}/reports/latest`),

  dashboard: (goalId) => request(`/dashboard${goalId ? `?goal_id=${goalId}` : ''}`),
  rhythm: (goalId, days = 28) => request(`/goals/${goalId}/rhythm?days=${days}`),
  dailyReview: (goalId, day) =>
    request(`/goals/${goalId}/daily-review${day ? `?day=${day}` : ''}`),
  saveDailyReview: (goalId, body) =>
    request(`/goals/${goalId}/daily-review`, { method: 'PUT', body }),
  uploadMistakePhoto: (goalId, formData) =>
    request(`/goals/${goalId}/mistakes/photo`, { method: 'POST', body: formData, timeout: 60000 }),

  classes: () => request('/classes'),
  createClass: (body) => request('/classes', { method: 'POST', body }),
  joinClass: (body) => request('/classes/join', { method: 'POST', body }),
  leaveClass: (id) => request(`/classes/${id}/leave`, { method: 'POST' }),
  deleteClass: (id) => request(`/classes/${id}`, { method: 'DELETE' }),
  classDashboard: (id) => request(`/classes/${id}/dashboard`),
  removeClassMember: (classId, memberId) =>
    request(`/classes/${classId}/members/${memberId}`, { method: 'DELETE' }),
  searchUsers: (q) => request(`/users/search?q=${encodeURIComponent(q)}`),

  buddies: () => request('/buddies'),
  addBuddy: (username) => request('/buddies', { method: 'POST', body: { username } }),
  removeBuddy: (id) => request(`/buddies/${id}`, { method: 'DELETE' }),

  askCoach: (body) => request('/coach/ask', { method: 'POST', body, timeout: LONG_TIMEOUT }),
  autoAdjust: (goalId) => request(`/goals/${goalId}/auto-adjust`, { method: 'POST' }),
  startFocus: (body) => request('/focus/start', { method: 'POST', body }),
  activeFocus: (goalId) =>
    request(`/focus/active${goalId ? `?goal_id=${goalId}` : ''}`),
  heartbeatFocus: (id, leaves) =>
    request(`/focus/${id}/heartbeat`, { method: 'POST', body: { leaves } }),
  uploadFocusSnapshot: (id, formData) =>
    request(`/focus/${id}/snapshot`, { method: 'POST', body: formData }),
  focusPresence: (id, body) => request(`/focus/${id}/presence`, { method: 'POST', body }),
  finishFocus: (id, body) => request(`/focus/${id}/finish`, { method: 'POST', body }),
  abortFocus: (id, reason) => request(`/focus/${id}/abort`, { method: 'POST', body: { reason } }),
  violations: (goalId) => request(`/goals/${goalId}/violations`),
  focusHistory: (goalId) => request(`/focus/history?goal_id=${goalId}`),
  insights: (goalId) => request(`/goals/${goalId}/insights`),
  forecast: (goalId, dailyMinutes) =>
    request(`/goals/${goalId}/forecast${dailyMinutes ? `?daily_minutes=${dailyMinutes}` : ''}`),
  applyForecast: (goalId, dailyMinutes) =>
    request(`/goals/${goalId}/apply-forecast`, {
      method: 'POST',
      body: { daily_minutes: dailyMinutes }
    }),
  rest: (goalId) => request(`/goals/${goalId}/rest`, { method: 'POST' }),
  flashcards: (goalId, limit = 20) =>
    request(`/goals/${goalId}/flashcards?limit=${limit}`),
  reviewFlashcard: (goalId, kpId, remembered) =>
    request(`/goals/${goalId}/flashcards/${kpId}/review`, {
      method: 'POST',
      body: { remembered }
    }),
  flashcardExplain: (goalId, kpId) =>
    request(`/goals/${goalId}/flashcards/${kpId}/explain`),
  cockpit: (goalId) => request(`/goals/${goalId}/cockpit`),
  knowledgeGraph: (goalId) => request(`/goals/${goalId}/knowledge-graph`),
  verifyGap: (gapId) => request(`/gaps/${gapId}/verify`, { method: 'POST' }),
  submitGap: (gapId, body) => request(`/gaps/${gapId}/submit`, { method: 'POST', body }),
  simulate: (goalId) => request(`/goals/${goalId}/simulate`),
  risks: (goalId) => request(`/goals/${goalId}/risks`),
  resolveRisk: (goalId, code) =>
    request(`/goals/${goalId}/risks/${code}/resolve`, { method: 'POST' }),
  experiments: (goalId) => request(`/goals/${goalId}/experiments`),
  createExperiment: (goalId, body) =>
    request(`/goals/${goalId}/experiments`, { method: 'POST', body }),
  finishExperiment: (experimentId, body) =>
    request(`/experiments/${experimentId}/finish`, { method: 'POST', body }),
  twin: (goalId) => request(`/goals/${goalId}/twin`),
  probes: (goalId, params = {}) => {
    const query = new URLSearchParams()
    if (params.kind) query.set('kind', params.kind)
    if (params.status) query.set('status', params.status)
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return request(`/goals/${goalId}/probes${suffix}`)
  },
  generateProbes: (goalId, body) =>
    request(`/goals/${goalId}/probes/generate`, { method: 'POST', body, timeout: LONG_TIMEOUT }),
  submitProbe: (probeId, chosen) =>
    request(`/probes/${probeId}/submit`, { method: 'POST', body: { chosen } }),
  createTrace: (mistakeId) =>
    request(`/mistakes/${mistakeId}/trace`, { method: 'POST' }),
  panelReview: (goalId, topic) =>
    request(`/goals/${goalId}/panel/review`, { method: 'POST', body: { topic }, timeout: LONG_TIMEOUT }),
  panelReviews: (goalId) => request(`/goals/${goalId}/panel/reviews`),
  freshnessScan: (goalId) =>
    request(`/goals/${goalId}/freshness/scan`, { method: 'POST', timeout: LONG_TIMEOUT }),
  freshness: (goalId) => request(`/goals/${goalId}/freshness`),
  freshnessHistory: (goalId) => request(`/goals/${goalId}/freshness/history`),
  evidence: (goalId, kind = '') =>
    request(`/goals/${goalId}/evidence${kind ? `?kind=${kind}` : ''}`),
  cognitiveLoad: (goalId) => request(`/goals/${goalId}/cognitive-load`),
  applyCognitiveLoad: (goalId, action = 'auto') =>
    request(`/goals/${goalId}/cognitive-load/apply`, { method: 'POST', body: { action } }),
  integrations: () => request('/integrations'),
  cloudInstances: () => request('/integrations/cloud'),
  cloudServices: () => request('/cloud/services'),
  ocrExtract: (formData) => request('/cloud/ocr/extract', { method: 'POST', body: formData, timeout: 60000 }),
  sisSynthesize: (formData) => request('/cloud/sis/synthesize', { method: 'POST', body: formData }),
  testIntegrations: (force = false) => request(`/integrations/test?force=${force}`, { method: 'POST' }),
  knowledgeBaseProbe: () => request('/knowledge-base/probe'),
  knowledgeLookup: (term) => request(`/knowledge-base/lookup?term=${encodeURIComponent(term)}`),
  generateQuiz: (goalId, body) =>
    request(`/goals/${goalId}/quiz/generate`, { method: 'POST', body, timeout: LONG_TIMEOUT }),
  questionBankCatalog: (goalId) => request(`/goals/${goalId}/question-banks`),
  testQuestionBank: (goalId, kpId) =>
    request(`/goals/${goalId}/question-banks/test${kpId ? `?kp_id=${kpId}` : ''}`, {
      method: 'POST'
    }),
  quizHistory: (goalId, limit = 50) =>
    request(`/goals/${goalId}/quiz/history?limit=${limit}`),
  submitQuiz: (goalId, body) =>
    request(`/goals/${goalId}/quiz/submit`, { method: 'POST', body }),
  skillPackages: (goalId) =>
    request(`/skill-packages${goalId ? `?goal_id=${goalId}` : ''}`),
  applySkillPackage: (slug, goalId) =>
    request(`/skill-packages/${slug}/apply`, { method: 'POST', body: { goal_id: goalId } }),
  createSkillPackage: (body) => request('/skill-packages', { method: 'POST', body }),

  vocabSession: (goalId, kpId, limit = 20) =>
    request(`/goals/${goalId}/vocab?kp_id=${kpId}&limit=${limit}`),
  vocabReview: (goalId, body) =>
    request(`/goals/${goalId}/vocab/review`, { method: 'POST', body }),
  vocabFinish: (goalId, body) =>
    request(`/goals/${goalId}/vocab/finish`, { method: 'POST', body }),

  skills: () => request('/skills'),
  meta: () => request('/meta'),
  entertainmentKinds: () => request('/entertainment/kinds'),
  entertainmentContent: (kind, force = false) => request(`/entertainment/${kind}?force=${force}`),
  psychScales: () => request('/psychology/scales'),
  psychScale: (key) => request(`/psychology/scales/${key}`),
  psychAssess: (body) => request('/psychology/assess', { method: 'POST', body }),
  psychHistory: () => request('/psychology/history'),
  health: () => request('/health'),
  riskForecast: (goalId, params = {}) => {
    const query = new URLSearchParams()
    if (params.high != null) query.set('high', params.high)
    if (params.medium != null) query.set('medium', params.medium)
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return request(`/goals/${goalId}/risk-forecast${suffix}`)
  },
  riskForecastHistory: (goalId, kpId) =>
    request(`/goals/${goalId}/risk-forecast/history${kpId ? `?kp_id=${kpId}` : ''}`),
  riskQuestions: (predictionId, count = 2) =>
    request(`/risk-forecast/${predictionId}/questions?count=${count}`, {
      method: 'POST',
      timeout: LONG_TIMEOUT
    }),
  riskVerify: (predictionId, passed) =>
    request(`/risk-forecast/${predictionId}/verify`, { method: 'POST', body: { passed } }),
  riskFeedback: (predictionId, verdict) =>
    request(`/risk-forecast/${predictionId}/feedback`, { method: 'POST', body: { verdict } }),
  panelDebate: (goalId, topic) =>
    request(`/goals/${goalId}/panel/debate`, { method: 'POST', body: { topic }, timeout: LONG_TIMEOUT }),
  panelRuns: (goalId, runId) =>
    request(`/goals/${goalId}/panel/runs${runId ? `?run_id=${runId}` : ''}`),
  twinForecast: (goalId) => request(`/goals/${goalId}/twin/forecast`),
  experimentReport: (experimentId) => request(`/experiments/${experimentId}/report`),
  learningEvents: (goalId, params = {}) => {
    const query = new URLSearchParams()
    if (params.limit != null) query.set('limit', params.limit)
    if (params.eventType) query.set('event_type', params.eventType)
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return request(`/goals/${goalId}/learning-events${suffix}`)
  },
  learningEventStats: (goalId) => request(`/goals/${goalId}/learning-events/stats`),
  masteryDetail: (goalId, kpId) => request(`/goals/${goalId}/mastery/${kpId}/detail`),
  ragSearch: (goalId, query, topK = 5) =>
    request(`/goals/${goalId}/documents/search`, { method: 'POST', body: { query, top_k: topK } }),
  ragReindex: (goalId) => request(`/goals/${goalId}/documents/reindex`, { method: 'POST', body: {} }),
  socratic: (goalId, payload) =>
    request(`/goals/${goalId}/socratic`, { method: 'POST', body: payload, timeout: LONG_TIMEOUT }),
  socraticRecall: (goalId, payload) =>
    request(`/goals/${goalId}/socratic/recall`, { method: 'POST', body: payload, timeout: LONG_TIMEOUT }),
  generateResources: (goalId, payload) =>
    request(`/goals/${goalId}/resources/generate`, { method: 'POST', body: payload, timeout: LONG_TIMEOUT }),
  teacherDashboard: (classId) => request(`/classes/${classId}/teacher-dashboard`),
  getConsent: (goalId) => request(`/goals/${goalId}/consent`),
  setConsent: (goalId, granted) =>
    request(`/goals/${goalId}/consent`, { method: 'POST', body: { scope: 'parent_report', granted } }),
  parentReport: (goalId) => request(`/goals/${goalId}/parent-report`),
  evalRun: (limit = 6) =>
    request(`/eval/run?limit=${limit}`, { method: 'POST', body: {}, timeout: LONG_TIMEOUT }),
  evalRuns: () => request('/eval/runs'),
  syntheticStudents: (count = 10, seed = 42) =>
    request('/eval/synthetic-students', { method: 'POST', body: { count, seed } }),
  graph: (goalId) => request(`/goals/${goalId}/graph`),
  graphSync: (goalId) => request(`/goals/${goalId}/graph/sync`, { method: 'POST', body: {} }),
  graphNode: (goalId, kpId) => request(`/goals/${goalId}/graph/nodes/${kpId}`),
  taskWhy: (goalId, taskId) => request(`/goals/${goalId}/tasks/${taskId}/why`),
  setTaskMinutes: (goalId, taskId, minutes) =>
    request(`/goals/${goalId}/tasks/${taskId}/minutes`, { method: 'POST', body: { minutes } }),
  schedulePreview: (goalId, limit = 8, minutes = 20) =>
    request(`/goals/${goalId}/schedule/preview?limit=${limit}&minutes=${minutes}`),
  monteCarloForecast: (goalId, target = 0.7) =>
    request(`/goals/${goalId}/forecast/montecarlo?target=${target}`),
  phaseInfo: (goalId) => request(`/goals/${goalId}/phase`),
  fatigueInfo: (goalId) => request(`/goals/${goalId}/fatigue`),
  llmCalls: (limit = 30) => request(`/llm-calls?limit=${limit}`),
  exportReportFile: (goalId, fmt) => downloadFile(`/goals/${goalId}/reports/latest/export.${fmt}`, `xueji-report.${fmt}`),
  exportReportJson: (goalId, filename) =>
    downloadFile(`/goals/${goalId}/reports/latest/export`, filename || 'xueji-report.json'),
  exportMistakesFile: (goalId) => downloadFile(`/goals/${goalId}/mistakes/export.docx`, 'xueji-mistakes.docx'),

  // 反向教学：费曼讲解 / 反向判卷 / 错误免疫
  feynmanStart: (goalId, kpId) =>
    request('/teaching/feynman/start', { method: 'POST', body: { goal_id: goalId, kp_id: kpId || null } }),
  feynmanSubmit: (sessionId, speech, mode = 'text') =>
    request('/teaching/feynman/submit', {
      method: 'POST',
      body: { session_id: sessionId, speech, speech_mode: mode },
      timeout: LONG_TIMEOUT
    }),
  feynmanProfile: (goalId) => request(`/teaching/feynman/profile?goal_id=${goalId}`),
  feynmanHistory: (goalId, limit = 8) => request(`/teaching/feynman/history?goal_id=${goalId}&limit=${limit}`),
  reverseStart: (goalId, kpId, cause) =>
    request('/teaching/reverse/start', {
      method: 'POST',
      body: { goal_id: goalId, kp_id: kpId || null, cause: cause || null }
    }),
  reverseGrade: (taskId, pickedStep, pickedType, fixText) =>
    request('/teaching/reverse/grade', {
      method: 'POST',
      body: { task_id: taskId, picked_step: pickedStep, picked_type: pickedType, fix_text: fixText }
    }),
  reverseProfile: (goalId) => request(`/teaching/reverse/profile?goal_id=${goalId}`),
  reverseHistory: (goalId, limit = 8) => request(`/teaching/reverse/history?goal_id=${goalId}&limit=${limit}`),
  immuneFingerprints: (goalId) => request(`/teaching/immune/fingerprints?goal_id=${goalId}`),
  immuneDrill: (goalId, fingerprint) =>
    request('/teaching/immune/drill', {
      method: 'POST',
      body: { goal_id: goalId, fingerprint: fingerprint || null },
      timeout: LONG_TIMEOUT
    }),
  immuneAnswer: (drillId, picked) =>
    request('/teaching/immune/answer', { method: 'POST', body: { drill_id: drillId, picked } }),
  immuneProfile: (goalId) => request(`/teaching/immune/profile?goal_id=${goalId}`),

  // ===== 备考方案：阶段划分 + 每日三段课表 + 真实视频课程 + 阶段模考 =====
  examPrepPlan: (goalId) => request(`/goals/${goalId}/exam-prep`),
  examPrepRebuild: (goalId) =>
    request(`/goals/${goalId}/exam-prep/build`, {
      method: 'POST',
      body: { regenerate: true },
      timeout: LONG_TIMEOUT
    }),
  examPrepDay: (goalId, dayIndex) => request(`/goals/${goalId}/exam-prep/day/${dayIndex}`),
  examPrepStageExam: (goalId, stageId, count = 6) =>
    request(`/goals/${goalId}/exam-prep/stage-exam`, {
      method: 'POST',
      body: { stage_id: stageId, count },
      timeout: LONG_TIMEOUT
    }),
  examPrepStageExamSubmit: (goalId, quizId, answers) =>
    request(`/goals/${goalId}/exam-prep/stage-exam/submit`, {
      method: 'POST',
      body: { quiz_id: quizId, answers }
    }),

  // ===== 管理后台（仅超级管理员，普通账号会收到 403）=====
  adminOverview: () => request('/admin/overview'),
  adminUsers: (q = '', limit = 20, offset = 0) =>
    request(`/admin/users?q=${encodeURIComponent(q)}&limit=${limit}&offset=${offset}`),
  adminSetSuperadmin: (userId, enabled) =>
    request(`/admin/users/${userId}/superadmin`, { method: 'POST', body: { enabled } }),
  adminResetPassword: (userId) =>
    request(`/admin/users/${userId}/reset-password`, { method: 'POST' }),
  adminSystem: () => request('/admin/system')
}

