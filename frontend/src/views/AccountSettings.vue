<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { store, notify, logout, patchUser } from '../store'
import { confirmAction } from '../confirm'

const router = useRouter()

const profile = reactive({
  nickname: store.user?.nickname || '',
  school: store.user?.school || ''
})
const savingProfile = ref(false)

const password = reactive({ old: '', next: '', confirm: '' })
const savingPassword = ref(false)
const passwordError = ref('')

const exporting = ref(false)
const deleting = ref(false)

// ---- 登录设备 ----
const sessions = ref([])
const loadingSessions = ref(false)
const revokingId = ref(0)
const revokingOthers = ref(false)

// ---- 账号找回 ----
const security = ref({ has_questions: false, questions: [], codes_unused: 0, recovery_ready: false })
const securityLoaded = ref(false)
const bank = ref([])
const recoveryForm = reactive({ password: '', q1: '', q2: '', a1: '', a2: '' })
const setupError = ref('')
const savingQuestions = ref(false)
const codePassword = ref('')
const codeError = ref('')
const issuingCodes = ref(false)
const freshCodes = ref([])
const copied = ref(false)

const joinedAt = computed(() => {
  const raw = store.user?.created_at
  if (!raw) return '—'
  return String(raw).slice(0, 10)
})

const nameChanged = computed(
  () =>
    profile.nickname.trim() !== (store.user?.nickname || '') ||
    profile.school.trim() !== (store.user?.school || '')
)

const questionOptions = computed(() =>
  // 第二问不能和第一问重复；同时保留当前已选值，避免切换第一问时把第二问清空
  bank.value.filter((item) => item.key !== recoveryForm.q1 || item.key === recoveryForm.q2)
)

watch(
  () => recoveryForm.q1,
  (value) => {
    if (recoveryForm.q2 !== value) return
    const alternative = bank.value.find((item) => item.key !== value)
    if (alternative) recoveryForm.q2 = alternative.key
  }
)

const otherSessions = computed(() => sessions.value.filter((row) => !row.current).length)

function toDate(raw) {
  if (!raw) return null
  const text = String(raw)
  const iso = text.endsWith('Z') || text.includes('+') ? text : `${text}Z`
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? null : date
}

function relative(raw) {
  const date = toDate(raw)
  if (!date) return '—'
  const diff = Date.now() - date.getTime()
  if (diff < 60 * 1000) return '刚刚'
  if (diff < 3600 * 1000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400 * 1000) return `${Math.floor(diff / 3600000)} 小时前`
  if (diff < 30 * 86400 * 1000) return `${Math.floor(diff / 86400000)} 天前`
  return date.toISOString().slice(0, 10)
}

function platformLabel(platform) {
  if (platform === 'ios') return 'iOS'
  if (platform === 'android') return '安卓'
  if (platform === 'miniprogram') return '小程序'
  return 'Web'
}

async function loadSessions() {
  loadingSessions.value = true
  try {
    sessions.value = await api.sessions()
  } catch (e) {
    /* 会话列表失败不影响其它设置项 */
  } finally {
    loadingSessions.value = false
  }
}

async function loadSecurity() {
  try {
    const [overview, questions] = await Promise.all([api.securityOverview(), api.questionBank()])
    security.value = overview
    bank.value = Array.isArray(questions) ? questions : []
    if (overview.has_questions && overview.questions.length === 2) {
      recoveryForm.q1 = overview.questions[0].key
      recoveryForm.q2 = overview.questions[1].key
    } else if (bank.value.length >= 2) {
      recoveryForm.q1 = bank.value[0].key
      recoveryForm.q2 = bank.value[1].key
    }
    securityLoaded.value = true
  } catch (e) {
    /* 静默：卡片会显示未配置状态 */
  }
}

async function saveProfile() {
  const nickname = profile.nickname.trim()
  if (!nickname) {
    notify('昵称不能为空', true)
    return
  }
  savingProfile.value = true
  try {
    const user = await api.updateProfile({ nickname, school: profile.school.trim() || null })
    patchUser(user)
    profile.nickname = user.nickname
    profile.school = user.school || ''
    notify('资料已更新')
  } catch (e) {
    notify(e.message, true)
  } finally {
    savingProfile.value = false
  }
}

async function savePassword() {
  passwordError.value = ''
  if (!password.old) {
    passwordError.value = '请输入原密码'
    return
  }
  if (password.next.length < 6) {
    passwordError.value = '新密码至少 6 位'
    return
  }
  if (password.next !== password.confirm) {
    passwordError.value = '两次输入的新密码不一致'
    return
  }
  if (password.next === password.old) {
    passwordError.value = '新密码不能与原密码相同'
    return
  }
  savingPassword.value = true
  try {
    await api.changePassword({ old_password: password.old, new_password: password.next })
    password.old = ''
    password.next = ''
    password.confirm = ''
    await loadSessions()
    notify('密码已修改，其他设备已自动退出')
  } catch (e) {
    passwordError.value = e.message
  } finally {
    savingPassword.value = false
  }
}

async function removeSession(row) {
  const ok = await confirmAction({
    title: row.current ? '退出当前设备' : '让该设备下线',
    message: row.current
      ? `退出后当前浏览器需要重新登录。`
      : `${row.device} 将立即失去访问权，需要重新输入密码。`,
    detail: '会话在服务端撤销，不是只清掉浏览器里的记录。',
    confirmText: row.current ? '退出登录' : '下线',
    danger: row.current
  })
  if (!ok) return
  revokingId.value = row.id
  try {
    const result = await api.revokeSession(row.id)
    if (result.current) {
      logout()
      router.push('/login')
      return
    }
    await loadSessions()
    notify('该设备已下线')
  } catch (e) {
    notify(e.message, true)
  } finally {
    revokingId.value = 0
  }
}

async function revokeOthers() {
  const ok = await confirmAction({
    title: '退出其他设备',
    message: `将让 ${otherSessions.value} 台设备立即下线，只保留当前设备。`,
    detail: '适合在公共电脑登录过、或怀疑密码泄露时使用。',
    confirmText: '全部下线'
  })
  if (!ok) return
  revokingOthers.value = true
  try {
    const result = await api.revokeOtherSessions()
    await loadSessions()
    notify(result.revoked ? `已下线 ${result.revoked} 台设备` : '没有其他在线设备')
  } catch (e) {
    notify(e.message, true)
  } finally {
    revokingOthers.value = false
  }
}

async function saveQuestions() {
  setupError.value = ''
  if (!recoveryForm.password) {
    setupError.value = '请输入登录密码以确认身份'
    return
  }
  if (recoveryForm.q1 === recoveryForm.q2) {
    setupError.value = '请选择两个不同的问题'
    return
  }
  if (!recoveryForm.a1.trim() || !recoveryForm.a2.trim()) {
    setupError.value = '两个答案都要填写'
    return
  }
  savingQuestions.value = true
  try {
    security.value = await api.saveSecurityQuestions({
      password: recoveryForm.password,
      answers: [
        { question_key: recoveryForm.q1, answer: recoveryForm.a1.trim() },
        { question_key: recoveryForm.q2, answer: recoveryForm.a2.trim() }
      ]
    })
    recoveryForm.password = ''
    recoveryForm.a1 = ''
    recoveryForm.a2 = ''
    notify('密保问题已保存，忘记密码时可自助找回')
  } catch (e) {
    setupError.value = e.message
  } finally {
    savingQuestions.value = false
  }
}

async function issueCodes() {
  codeError.value = ''
  copied.value = false
  if (!codePassword.value) {
    codeError.value = '请输入登录密码以确认身份'
    return
  }
  const ok = await confirmAction({
    title: '生成新的恢复码',
    message: security.value.codes_unused
      ? `现有 ${security.value.codes_unused} 枚未使用的恢复码会立即作废。`
      : '将生成 8 枚一次性恢复码。',
    detail: '新恢复码只会显示一次，请复制或下载后离线保存。',
    confirmText: '生成'
  })
  if (!ok) return
  issuingCodes.value = true
  try {
    const data = await api.issueRecoveryCodes({ password: codePassword.value })
    freshCodes.value = data.codes || []
    codePassword.value = ''
    await loadSecurity()
    notify('恢复码已生成，请立即保存')
  } catch (e) {
    codeError.value = e.message
  } finally {
    issuingCodes.value = false
  }
}

async function copyCodes() {
  try {
    await navigator.clipboard.writeText(freshCodes.value.join('\n'))
    copied.value = true
    notify('已复制到剪贴板')
  } catch (e) {
    notify('浏览器不允许自动复制，请手动选择文本', true)
  }
}

function downloadCodes() {
  const header = `学迹 · 账号恢复码\n账号：${store.user?.username || ''}\n生成时间：${new Date().toLocaleString()}\n每枚只能使用一次，请离线保存。\n\n`
  const blob = new Blob([header + freshCodes.value.join('\n')], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'xueji-recovery-codes.txt'
  link.click()
  URL.revokeObjectURL(url)
  notify('恢复码已下载，请妥善保存')
}

async function exportData() {
  exporting.value = true
  try {
    const data = await api.exportData()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `xueji-export-${new Date().toISOString().slice(0, 10)}.json`
    link.click()
    URL.revokeObjectURL(url)
    notify('学习数据已导出')
  } catch (e) {
    notify(e.message, true)
  } finally {
    exporting.value = false
  }
}

async function deleteAccount() {
  const ok = await confirmAction({
    title: '注销账号',
    message: '注销会清空所有目标、任务、错题与周报，且不可恢复。',
    detail: '建议先导出学习数据备份。注销后同一用户名可以重新注册，但历史数据无法找回。',
    confirmText: '确认注销',
    danger: true
  })
  if (!ok) return
  deleting.value = true
  try {
    await api.deleteAccount()
    logout()
    notify('账号已注销')
    router.push('/login')
  } catch (e) {
    notify(e.message, true)
  } finally {
    deleting.value = false
  }
}

onMounted(() => {
  loadSessions()
  loadSecurity()
})
</script>

<template>
  <div class="stack">
    <p class="page-intro">
      这里管理账号本身：展示资料、登录密码、登录设备与账号找回方式。密码与密保答案只保存哈希，服务端无法回显原文。
    </p>

    <div v-if="securityLoaded && !security.recovery_ready" class="stale-banner" role="alert">
      <span>还没有设置找回方式：忘记密码时只能联系管理员重置。建议现在设好密保问题，或保存一份恢复码。</span>
    </div>

    <div class="stack settings-grid">
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">账号信息</div>
            <div class="card-sub">用户名创建后不可修改，它是登录凭据</div>
          </div>
        </div>
        <div class="stack" style="margin-top: 12px">
          <div class="kv"><span>用户名</span><strong>{{ store.user?.username || '—' }}</strong></div>
          <div class="kv"><span>注册时间</span><strong>{{ joinedAt }}</strong></div>
          <div class="kv"><span>当前目标</span><strong>{{ store.goals.length }} 个</strong></div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">展示资料</div>
        <div class="card-sub">教练会用昵称呼唤你，学校用于班级与家长报告</div>
        <div class="stack" style="margin-top: 12px">
          <label class="login-field">
            <span>昵称</span>
            <input v-model="profile.nickname" class="input" maxlength="32" placeholder="例如：小林" />
          </label>
          <label class="login-field">
            <span>学校（可选）</span>
            <input v-model="profile.school" class="input" maxlength="64" placeholder="例如：信息工程学院" />
          </label>
          <div class="row" style="gap: 8px">
            <button class="btn btn-solid" :disabled="savingProfile || !nameChanged" @click="saveProfile">
              {{ savingProfile ? '保存中…' : '保存资料' }}
            </button>
            <span v-if="!nameChanged" class="small muted">没有改动</span>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">修改密码</div>
        <div class="card-sub">修改后其他设备会立刻退出登录，只保留当前设备</div>
        <div class="stack" style="margin-top: 12px">
          <label class="login-field">
            <span>原密码</span>
            <input v-model="password.old" class="input" type="password" autocomplete="current-password" />
          </label>
          <label class="login-field">
            <span>新密码</span>
            <input v-model="password.next" class="input" type="password" autocomplete="new-password" placeholder="至少 6 位" />
          </label>
          <label class="login-field">
            <span>确认新密码</span>
            <input v-model="password.confirm" class="input" type="password" autocomplete="new-password" />
          </label>
          <p v-if="passwordError" class="login-error">{{ passwordError }}</p>
          <button
            class="btn btn-solid"
            style="align-self: flex-start"
            :disabled="savingPassword"
            @click="savePassword"
          >
            {{ savingPassword ? '修改中…' : '修改密码' }}
          </button>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">登录设备</div>
            <div class="card-sub">
              共 {{ sessions.length }} 台设备在线<span v-if="otherSessions">，其中 {{ otherSessions }} 台不是本机</span>
            </div>
          </div>
          <button
            class="btn btn-ghost btn-sm"
            :disabled="revokingOthers || !otherSessions"
            @click="revokeOthers"
          >
            退出其他设备
          </button>
        </div>
        <div class="stack session-list">
          <div v-for="row in sessions" :key="row.id" class="session-row">
            <span class="session-icon">{{ platformLabel(row.platform) }}</span>
            <div class="session-main">
              <b>
                {{ row.device }}
                <span v-if="row.current" class="session-tag">当前设备</span>
              </b>
              <div class="small muted">
                {{ row.ip || '未记录 IP' }} · 最近活跃 {{ relative(row.last_seen_at) }} ·
                登录于 {{ relative(row.created_at) }}
              </div>
            </div>
            <button
              class="btn btn-ghost btn-sm"
              :disabled="revokingId === row.id"
              @click="removeSession(row)"
            >
              {{ row.current ? '退出' : '下线' }}
            </button>
          </div>
          <p v-if="!sessions.length" class="small muted">
            {{ loadingSessions ? '读取中…' : '暂无在线设备' }}
          </p>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">密保问题</div>
            <div class="card-sub">忘记密码时用来证明「你是本人」，需要设置两个问题</div>
          </div>
          <span class="chip" :class="{ active: security.has_questions }">
            {{ security.has_questions ? '已设置' : '未设置' }}
          </span>
        </div>
        <div class="stack" style="margin-top: 12px">
          <label class="login-field">
            <span>问题一</span>
            <select v-model="recoveryForm.q1" class="input">
              <option v-for="item in bank" :key="item.key" :value="item.key">{{ item.text }}</option>
            </select>
          </label>
          <label class="login-field">
            <span>答案一</span>
            <input v-model="recoveryForm.a1" class="input" maxlength="64" placeholder="不区分大小写与空格" />
          </label>
          <label class="login-field">
            <span>问题二</span>
            <select v-model="recoveryForm.q2" class="input">
              <option v-for="item in questionOptions" :key="item.key" :value="item.key">
                {{ item.text }}
              </option>
            </select>
          </label>
          <label class="login-field">
            <span>答案二</span>
            <input v-model="recoveryForm.a2" class="input" maxlength="64" placeholder="不区分大小写与空格" />
          </label>
          <label class="login-field">
            <span>当前登录密码</span>
            <input
              v-model="recoveryForm.password"
              class="input"
              type="password"
              autocomplete="current-password"
              placeholder="设置密保需要再次确认身份"
            />
          </label>
          <p v-if="setupError" class="login-error">{{ setupError }}</p>
          <button
            class="btn btn-solid"
            style="align-self: flex-start"
            :disabled="savingQuestions"
            @click="saveQuestions"
          >
            {{ savingQuestions ? '保存中…' : security.has_questions ? '更新密保问题' : '保存密保问题' }}
          </button>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">一次性恢复码</div>
            <div class="card-sub">每枚只能使用一次，明文只在生成时显示一次</div>
          </div>
          <span class="chip" :class="{ active: security.codes_unused > 0 }">
            剩余 {{ security.codes_unused }} 枚
          </span>
        </div>

        <div v-if="freshCodes.length" class="code-panel">
          <div class="code-grid">
            <code v-for="item in freshCodes" :key="item">{{ item }}</code>
          </div>
          <div class="row" style="gap: 8px; margin-top: 10px">
            <button class="btn btn-ghost btn-sm" @click="copyCodes">{{ copied ? '已复制' : '复制全部' }}</button>
            <button class="btn btn-ghost btn-sm" @click="downloadCodes">下载为 txt</button>
            <button class="link-quiet" @click="freshCodes = []">我已保存，隐藏</button>
          </div>
        </div>
        <p v-else class="small muted" style="margin-top: 10px">
          生成后请立即复制或下载保存；一旦离开本页，服务端无法再回显明文。重新生成会作废旧的未使用码。
        </p>

        <div class="stack" style="margin-top: 12px">
          <label class="login-field">
            <span>当前登录密码</span>
            <input
              v-model="codePassword"
              class="input"
              type="password"
              autocomplete="current-password"
              placeholder="生成恢复码需要再次确认身份"
            />
          </label>
          <p v-if="codeError" class="login-error">{{ codeError }}</p>
          <button
            class="btn btn-ghost"
            style="align-self: flex-start"
            :disabled="issuingCodes"
            @click="issueCodes"
          >
            {{ issuingCodes ? '生成中…' : security.codes_unused ? '重新生成 8 枚恢复码' : '生成 8 枚恢复码' }}
          </button>
        </div>
      </div>

      <div class="card card-wide">
        <div class="card-title">数据与账号处置</div>
        <div class="card-sub">导出后可自行留档；注销不可撤销</div>
        <div class="stack" style="margin-top: 12px">
          <div class="gap-row">
            <div>
              <b>导出学习数据</b>
              <div class="small muted">目标、知识点、任务、错题、周报与学习事件，一次性打包为 JSON</div>
            </div>
            <button class="btn btn-ghost" :disabled="exporting" @click="exportData">
              {{ exporting ? '导出中…' : '导出' }}
            </button>
          </div>
          <div class="gap-row">
            <div>
              <b>注销账号</b>
              <div class="small muted">清空全部学习数据并退出登录，无法恢复</div>
            </div>
            <button class="btn btn-danger" :disabled="deleting" @click="deleteAccount">
              {{ deleting ? '注销中…' : '注销账号' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
