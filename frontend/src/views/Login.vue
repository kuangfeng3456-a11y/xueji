<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { setSession, notify, store } from '../store'

const router = useRouter()
const mode = ref('login')
const loading = ref(false)
const showPassword = ref(false)
const remember = ref(true)
const errors = reactive({ username: '', password: '' })
const form = reactive({ username: '', password: '', nickname: '', school: '' })
const isRegister = computed(() => mode.value === 'register')
const degraded = computed(
  () =>
    store.health?.status === 'degraded' ||
    store.health?.database_fallback ||
    store.health?.database === 'sqlite-fallback'
)

function switchMode(next) {
  mode.value = next
  errors.username = ''
  errors.password = ''
}

function validate() {
  errors.username = ''
  errors.password = ''
  if (!form.username || form.username.trim().length < 3) errors.username = '用户名至少 3 个字符'
  if (!form.password || form.password.length < 6) errors.password = '密码至少 6 个字符'
  return !errors.username && !errors.password
}

function forgot() {
  router.push('/recover')
}

async function submit() {
  if (!validate()) return
  loading.value = true
  try {
    const payload =
      mode.value === 'login'
        ? { username: form.username.trim(), password: form.password }
        : {
            username: form.username.trim(),
            password: form.password,
            nickname: form.nickname.trim() || form.username.trim(),
            school: form.school.trim() || null
          }
    const data = mode.value === 'login' ? await api.login(payload) : await api.register(payload)
    setSession(data.access_token, data.user, remember.value)
    const isNew = mode.value === 'register'
    notify(
      isNew
        ? '注册成功。先设定一个考试目标，几分钟后就能看到今天该学什么。'
        : `欢迎回来，${data.user.nickname || data.user.username}`
    )
    router.push(isNew ? { path: '/plan', query: { tab: 'goal' } } : '/')
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    const [meta, health] = await Promise.all([api.meta(), api.health()])
    store.meta = meta
    store.health = health
  } catch (e) {
    /* 状态徽章不影响登录 */
  }
})
</script>

<template>
  <div class="login">
    <section class="login-statement">
      <div class="login-brand">
        <div class="brand-mark" aria-hidden="true">学</div>
        <div class="brand-lockup">
          <div class="brand-cn">学迹</div>
          <div class="brand-en">XUEJI · ADAPTIVE COACH</div>
        </div>
      </div>

      <p class="login-kicker">自适应 AI 学习教练</p>
      <h1 class="login-title">今天该学什么<br /><em>按你的弱项排好</em></h1>
      <p class="login-lede">
        刷视频容易过眼就忘，问大模型没有下一题。学迹把看课、随堂测、口语跟读和错题复盘连成一条线：
        打开就知道下一步做什么，做错的会改明天的安排。
      </p>

      <dl class="login-reasons">
        <div>
          <dt>对上你的弱项</dt>
          <dd>课和题按知识点和错因来匹配，不是随便搜一堆视频。</dd>
        </div>
        <div>
          <dt>一条线走完</dt>
          <dd>看完立刻练，练完开口跟读，不用在三个应用之间来回切。</dd>
        </div>
        <div>
          <dt>记住你的错</dt>
          <dd>错题进入错题本，并影响明天的计划；落后只是顺延，不是作废。</dd>
        </div>
      </dl>

      <p v-if="degraded" class="login-degraded">
        云端数据暂时连不上，已改为本地保存，登录和学习功能仍可使用。
      </p>
    </section>

    <section class="login-panel">
      <div class="login-tabs">
        <button :class="{ active: !isRegister }" type="button" @click="switchMode('login')">登录</button>
        <button :class="{ active: isRegister }" type="button" @click="switchMode('register')">注册</button>
      </div>

      <h2>{{ isRegister ? '创建你的账号' : '继续今天的学习' }}</h2>
      <p class="login-sub">
        {{ isRegister ? '注册后先设定一个考试目标，几分钟就能看到今天该学什么。' : '登录后直接进入今日闭环：看课、随堂测、口语跟读和复盘。' }}
      </p>

      <form class="login-form" @submit.prevent="submit">
        <label class="login-field">
          <span>用户名</span>
          <input v-model="form.username" class="input" autocomplete="username" placeholder="请输入用户名" />
          <small v-if="errors.username" class="login-error">{{ errors.username }}</small>
        </label>

        <label class="login-field">
          <span>密码</span>
          <div class="login-password">
            <input
              v-model="form.password"
              class="input"
              :type="showPassword ? 'text' : 'password'"
              :autocomplete="isRegister ? 'new-password' : 'current-password'"
              placeholder="至少 6 位"
            />
            <button type="button" class="link-quiet" @click="showPassword = !showPassword">
              {{ showPassword ? '隐藏' : '显示' }}
            </button>
          </div>
          <small v-if="errors.password" class="login-error">{{ errors.password }}</small>
        </label>

        <template v-if="isRegister">
          <label class="login-field">
            <span>昵称（可选）</span>
            <input v-model="form.nickname" class="input" placeholder="教练会这样称呼你" />
          </label>
          <label class="login-field">
            <span>学校（可选）</span>
            <input v-model="form.school" class="input" placeholder="用于班级与家长报告" />
          </label>
        </template>

        <div class="login-row">
          <label class="login-remember">
            <input v-model="remember" type="checkbox" />
            记住我
          </label>
          <button v-if="!isRegister" type="button" class="link-quiet" @click="forgot">忘记密码？</button>
        </div>

        <button class="btn btn-solid login-submit" :disabled="loading" type="submit">
          {{ loading ? '处理中…' : isRegister ? '注册并设定目标' : '开始今天的学习' }}
        </button>
      </form>
    </section>
  </div>
</template>
