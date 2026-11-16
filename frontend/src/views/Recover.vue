<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'

const router = useRouter()

/**
 * 无邮件/短信通道的自助找回：先用「密保问题」或「一次性恢复码」证明是本人，
 * 拿到 10 分钟有效的一次性票据，再设置新密码。全程不出网、不依赖外部通道。
 */
const step = ref(1)
const loading = ref(false)
const error = ref('')
const lockedUntil = ref('')

const username = ref('')
const methods = ref([])
const questions = ref([])
const method = ref('')
const answers = reactive({})
const code = ref('')

const resetToken = ref('')
const nextPassword = ref('')
const confirmPassword = ref('')
const done = ref(false)

const methodLabel = computed(() =>
  methods.value.includes('questions') && methods.value.includes('code')
    ? '密保问题 / 恢复码'
    : methods.value.includes('questions')
      ? '密保问题'
      : methods.value.includes('code')
        ? '恢复码'
        : '未配置'
)

/** 第 4 步是结果页，进度徽章仍然显示「3 / 3」，避免出现 4 / 3。 */
const stepLabel = computed(() => Math.min(step.value, 3))

const canVerify = computed(() => {
  if (method.value === 'questions') {
    return questions.value.every((item) => String(answers[item.key] || '').trim().length > 0)
  }
  if (method.value === 'code') return String(code.value).trim().length >= 8
  return false
})

function lockText(raw) {
  if (!raw) return ''
  const target = new Date(String(raw).endsWith('Z') ? raw : `${raw}Z`)
  if (Number.isNaN(target.getTime())) return '验证失败次数过多，请稍后再试'
  const minutes = Math.max(1, Math.ceil((target.getTime() - Date.now()) / 60000))
  return `验证失败次数过多，请 ${minutes} 分钟后再试`
}

async function lookup() {
  error.value = ''
  if (username.value.trim().length < 3) {
    error.value = '请输入注册时的用户名'
    return
  }
  loading.value = true
  try {
    const data = await api.recoveryOptions(username.value.trim())
    methods.value = data.methods || []
    questions.value = data.questions || []
    lockedUntil.value = lockText(data.locked_until)
    if (!methods.value.length) {
      error.value = lockedUntil.value || '该账号没有可用的找回方式，请联系管理员重置密码'
      return
    }
    method.value = methods.value[0]
    step.value = 2
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function verify() {
  error.value = ''
  if (!canVerify.value) {
    error.value = method.value === 'questions' ? '请填写全部答案' : '请输入完整的恢复码'
    return
  }
  loading.value = true
  try {
    const body =
      method.value === 'questions'
        ? {
            username: username.value.trim(),
            method: 'questions',
            answers: questions.value.map((item) => ({
              question_key: item.key,
              answer: String(answers[item.key] || '').trim()
            }))
          }
        : { username: username.value.trim(), method: 'code', code: String(code.value).trim() }
    const data = await api.recoveryVerify(body)
    resetToken.value = data.reset_token
    step.value = 3
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function resetPassword() {
  error.value = ''
  if (nextPassword.value.length < 6) {
    error.value = '新密码至少 6 位'
    return
  }
  if (nextPassword.value !== confirmPassword.value) {
    error.value = '两次输入的新密码不一致'
    return
  }
  loading.value = true
  try {
    await api.recoveryReset({ reset_token: resetToken.value, new_password: nextPassword.value })
    done.value = true
    step.value = 4
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function back() {
  error.value = ''
  step.value = Math.max(1, step.value - 1)
}
</script>

<template>
  <div class="login recover">
    <section class="login-statement">
      <div class="login-brand">
        <div class="brand-mark" aria-hidden="true">学</div>
        <div class="brand-lockup">
          <div class="brand-cn">学迹</div>
          <div class="brand-en">XUEJI · ACCOUNT RECOVERY</div>
        </div>
      </div>

      <p class="login-kicker">不需要邮箱，也不需要短信</p>
      <h1 class="login-title">用只有你知道的答案<br /><em>换回账号访问权</em></h1>
      <p class="login-lede">
        我们不做「假装发了一封邮件」的流程。密保问题与一次性恢复码都只存在你的账号里，
        验证通过后签发 10 分钟有效的一次性凭据，重设密码的同时让所有旧设备下线。
      </p>

      <ol class="recover-steps">
        <li :class="{ on: step >= 1 }"><b>01</b><span>确认用户名</span></li>
        <li :class="{ on: step >= 2 }"><b>02</b><span>回答问题或输入恢复码</span></li>
        <li :class="{ on: step >= 3 }"><b>03</b><span>设置新密码</span></li>
      </ol>
    </section>

    <section class="login-panel">
      <div class="recover-head">
        <span class="recover-badge">第 {{ stepLabel }} / 3 步</span>
        <button type="button" class="link-quiet" @click="router.push('/login')">返回登录</button>
      </div>

      <template v-if="step === 1">
        <h2>先确认你的账号</h2>
        <p class="login-sub">输入注册时使用的用户名，我们会告诉你这个账号可用哪种方式找回。</p>
        <form class="login-form" @submit.prevent="lookup">
          <label class="login-field">
            <span>用户名</span>
            <input v-model="username" class="input" autocomplete="username" placeholder="请输入用户名" />
          </label>
          <p v-if="error" class="login-error">{{ error }}</p>
          <button class="btn btn-solid login-submit" type="submit" :disabled="loading">
            {{ loading ? '查询中…' : '下一步' }}
          </button>
        </form>
      </template>

      <template v-else-if="step === 2">
        <h2>证明这是你的账号</h2>
        <p class="login-sub">账号 {{ username }} 可用方式：{{ methodLabel }}。</p>

        <div v-if="methods.length > 1" class="recover-tabs">
          <button
            type="button"
            :class="{ active: method === 'questions' }"
            @click="method = 'questions'; error = ''"
          >
            密保问题
          </button>
          <button type="button" :class="{ active: method === 'code' }" @click="method = 'code'; error = ''">
            恢复码
          </button>
        </div>

        <form class="login-form" @submit.prevent="verify">
          <template v-if="method === 'questions'">
            <label v-for="item in questions" :key="item.key" class="login-field">
              <span>{{ item.text }}</span>
              <input v-model="answers[item.key]" class="input" autocomplete="off" placeholder="不区分大小写，空格可忽略" />
            </label>
          </template>

          <label v-else class="login-field">
            <span>恢复码</span>
            <input
              v-model="code"
              class="input"
              autocomplete="one-time-code"
              placeholder="形如 XJ-7K2M-9QDF"
            />
            <small class="muted">每枚恢复码只能使用一次，可在「设置 · 账号与安全」中重新生成</small>
          </label>

          <p v-if="error" class="login-error">{{ error }}</p>

          <div class="recover-actions">
            <button type="button" class="btn btn-ghost" @click="back">上一步</button>
            <button class="btn btn-solid" type="submit" :disabled="loading || !canVerify">
              {{ loading ? '验证中…' : '验证并继续' }}
            </button>
          </div>
        </form>
      </template>

      <template v-else-if="step === 3">
        <h2>设置新密码</h2>
        <p class="login-sub">重置成功后，所有设备上的登录都会失效，需要重新登录。</p>
        <form class="login-form" @submit.prevent="resetPassword">
          <label class="login-field">
            <span>新密码</span>
            <input
              v-model="nextPassword"
              class="input"
              type="password"
              autocomplete="new-password"
              placeholder="至少 6 位"
            />
          </label>
          <label class="login-field">
            <span>确认新密码</span>
            <input v-model="confirmPassword" class="input" type="password" autocomplete="new-password" />
          </label>
          <p v-if="error" class="login-error">{{ error }}</p>
          <div class="recover-actions">
            <button type="button" class="btn btn-ghost" @click="back">上一步</button>
            <button class="btn btn-solid" type="submit" :disabled="loading">
              {{ loading ? '提交中…' : '重设密码' }}
            </button>
          </div>
        </form>
      </template>

      <template v-else>
        <h2>密码已重设</h2>
        <p class="login-sub">所有旧设备已下线。用新密码登录，之前的学习数据都在。</p>
        <div v-if="done" class="recover-done">
          <span class="status-dot on"></span>
          <span>账号 {{ username }} 已更新</span>
        </div>
        <button class="btn btn-solid login-submit" type="button" @click="router.push('/login')">
          去登录
        </button>
        <p class="small muted" style="margin-top: 14px">
          建议登录后到「设置 · 账号与安全」补设密保问题并保存一份恢复码，下次就不用找管理员了。
        </p>
      </template>
    </section>
  </div>
</template>
