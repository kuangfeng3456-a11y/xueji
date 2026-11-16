<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'
import AppSelect from '../components/AppSelect.vue'

const MODES = [
  { key: 'feynman', label: '费曼讲解', hint: '讲给 AI 听，抓「熟练度错觉」' },
  { key: 'reverse', label: '我来判卷', hint: 'AI 交一份带错的答卷，你当老师' },
  { key: 'immune', label: '错误免疫', hint: '把反复犯的错做成疫苗' }
]

const mode = ref('feynman')
const points = ref([])
const kpId = ref('')

const kpOptions = computed(() => [
  { value: '', label: '自动挑最该练的' },
  ...points.value.map((point) => ({
    value: point.id,
    label: `${point.name}（${Math.round((point.mastery || 0) * 100)}%）`
  }))
])

/* ---------------- 费曼 ---------------- */
const feynman = ref(null)
const feynmanResult = ref(null)
const feynmanProfile = ref(null)
const speech = ref('')
const feynmanBusy = ref(false)

const speechLen = computed(() => speech.value.trim().length)
const coveragePct = computed(() =>
  feynmanResult.value ? Math.round((feynmanResult.value.coverage || 0) * 100) : 0
)

/* ---------------- 反向判卷 ---------------- */
const CAUSES = ['概念不清', '方法不会', '粗心']
const cause = ref('')
const causeOptions = [
  { value: '', label: '自动轮换' },
  ...CAUSES.map((item) => ({ value: item, label: item }))
]
const task = ref(null)
const gradeResult = ref(null)
const pickedStep = ref(null)
const pickedType = ref('')
const fixText = ref('')
const reverseProfile = ref(null)
const reverseBusy = ref(false)

/* ---------------- 错误免疫 ---------------- */
const immune = ref(null)
const drill = ref(null)
const drillResult = ref(null)
const pickedKey = ref('')
const immuneProfile = ref(null)
const immuneBusy = ref(false)

const goalId = computed(() => store.currentGoalId)

async function loadPoints() {
  if (!goalId.value) return
  try {
    points.value = await api.knowledgePoints(goalId.value)
  } catch (e) {
    notify(e.message, true)
  }
}

async function loadProfiles() {
  if (!goalId.value) return
  try {
    const [fp, rp, ip] = await Promise.all([
      api.feynmanProfile(goalId.value),
      api.reverseProfile(goalId.value),
      api.immuneProfile(goalId.value)
    ])
    feynmanProfile.value = fp
    reverseProfile.value = rp
    immuneProfile.value = ip
    immune.value = ip
  } catch (e) {
    notify(e.message, true)
  }
}

async function startFeynman() {
  if (!goalId.value) return
  feynmanBusy.value = true
  feynmanResult.value = null
  try {
    feynman.value = await api.feynmanStart(goalId.value, kpId.value || null)
    speech.value = ''
  } catch (e) {
    notify(e.message, true)
  } finally {
    feynmanBusy.value = false
  }
}

async function submitFeynman() {
  if (!feynman.value || speechLen.value < 30) return
  feynmanBusy.value = true
  try {
    feynmanResult.value = await api.feynmanSubmit(feynman.value.session_id, speech.value.trim())
    await loadProfiles()
  } catch (e) {
    notify(e.message, true)
  } finally {
    feynmanBusy.value = false
  }
}

function resetFeynman() {
  feynman.value = null
  feynmanResult.value = null
  speech.value = ''
}

async function startReverse() {
  if (!goalId.value) return
  reverseBusy.value = true
  gradeResult.value = null
  pickedStep.value = null
  pickedType.value = ''
  fixText.value = ''
  try {
    task.value = await api.reverseStart(goalId.value, kpId.value || null, cause.value || null)
  } catch (e) {
    notify(e.message, true)
  } finally {
    reverseBusy.value = false
  }
}

async function submitGrade() {
  if (!task.value) return
  if (!pickedStep.value) {
    notify('先选出「错在第几步」', true)
    return
  }
  if (!pickedType.value) {
    notify('再判断这属于哪类错因', true)
    return
  }
  reverseBusy.value = true
  try {
    gradeResult.value = await api.reverseGrade(task.value.task_id, pickedStep.value, pickedType.value, fixText.value)
    await loadProfiles()
  } catch (e) {
    notify(e.message, true)
  } finally {
    reverseBusy.value = false
  }
}

async function startDrill(fingerprint = null) {
  if (!goalId.value) return
  immuneBusy.value = true
  drillResult.value = null
  pickedKey.value = ''
  try {
    drill.value = await api.immuneDrill(goalId.value, fingerprint)
  } catch (e) {
    notify(e.message, true)
  } finally {
    immuneBusy.value = false
  }
}

async function answerDrill() {
  if (!drill.value || !pickedKey.value) return
  immuneBusy.value = true
  try {
    drillResult.value = await api.immuneAnswer(drill.value.drill_id, pickedKey.value)
    await loadProfiles()
  } catch (e) {
    notify(e.message, true)
  } finally {
    immuneBusy.value = false
  }
}

watch(goalId, () => {
  resetFeynman()
  task.value = null
  drill.value = null
  loadPoints()
  loadProfiles()
})

onMounted(() => {
  loadPoints()
  loadProfiles()
})
</script>

<template>
  <div class="stack">
    <div class="hero">
      <h1>讲与判：把「以为会」变成「真的会」</h1>
      <p>
        考场丢分往往不是「没学过」，而是「以为自己会」。这三件工具都反过来练：
        把知识点讲出来（费曼）、批改一份带错的答卷（反向判卷）、把反复犯的错做成疫苗（错误免疫）。
        判定基准全部预置在服务端，模型只负责写题面与辅助判命中，结果可复现。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ feynmanProfile?.attempts ?? 0 }}</strong>
          <span>讲解次数</span>
        </div>
        <div class="hero-meta-item">
          <strong>
            {{ feynmanProfile?.avg_coverage === null || feynmanProfile?.avg_coverage === undefined
              ? '—'
              : Math.round(feynmanProfile.avg_coverage * 100) + '%' }}
          </strong>
          <span>平均要点覆盖</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ reverseProfile?.attempts ?? 0 }}</strong>
          <span>判卷次数</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ immuneProfile?.immune ?? 0 }}</strong>
          <span>已免疫指纹</span>
        </div>
      </div>
    </div>

    <div class="rt-tabs">
      <button
        v-for="item in MODES"
        :key="item.key"
        class="rt-tab"
        :class="{ active: mode === item.key }"
        @click="mode = item.key"
      >
        <b>{{ item.label }}</b>
        <span>{{ item.hint }}</span>
      </button>
    </div>

    <div class="rt-kpbar">
      <span class="small muted">知识点</span>
      <AppSelect v-model="kpId" :options="kpOptions" style="max-width: 260px" />
      <span class="small muted">留空则由系统按掌握度与错题自动挑选</span>
    </div>

    <!-- ---------------- 费曼 ---------------- -->
    <div v-if="mode === 'feynman'" class="rt-grid">
      <div class="card rt-main">
        <div class="card-head">
          <div>
            <div class="card-title">费曼检验场</div>
            <div class="card-sub">讲解要点在服务端预置，讲完按「讲没讲到」逐条核对，漏掉的就是盲区</div>
          </div>
          <button v-if="feynman" class="btn btn-ghost btn-sm" @click="resetFeynman">换一个</button>
        </div>

        <div v-if="!feynman" class="rt-empty">
          <div class="rt-empty-icon">🎤</div>
          <div class="rt-empty-title">挑一个「看着会」的知识点，讲 60 秒</div>
          <div class="small muted">
            看答案都懂、一到考场写不出来，就是熟练度错觉。讲给不懂的人听，讲不全的地方才是真的不会。
          </div>
          <button class="btn" :disabled="feynmanBusy" @click="startFeynman">
            {{ feynmanBusy ? '准备中...' : '开始讲解' }}
          </button>
        </div>

        <template v-else>
          <div class="rt-prompt">
            <div class="rt-prompt-kp">{{ feynman.kp_name }}</div>
            <div class="rt-prompt-text">{{ feynman.prompt }}</div>
            <div class="rt-prompt-reason">为什么挑它：{{ feynman.reason }}</div>
          </div>

          <template v-if="!feynmanResult">
            <textarea
              v-model="speech"
              class="textarea rt-speech"
              :maxlength="feynman.max_chars"
              placeholder="像给同学讲题一样写下来：它是什么、怎么用、哪里容易错。不用背术语，讲清楚就行。"
            ></textarea>
            <div class="rt-row">
              <span class="small muted">
                {{ speechLen }} 字<span v-if="speechLen < 30">（至少 30 字）</span>
              </span>
              <button class="btn" :disabled="feynmanBusy || speechLen < 30" @click="submitFeynman">
                {{ feynmanBusy ? '核对中...' : '提交核对' }}
              </button>
            </div>
          </template>

          <template v-else>
            <div class="rt-result">
              <div class="rt-gauge" :style="{ '--pct': coveragePct + '%' }">
                <div class="rt-gauge-inner">
                  <b>{{ coveragePct }}<small>%</small></b>
                  <span>要点覆盖</span>
                </div>
              </div>
              <div class="rt-result-body">
                <div class="rt-verdict">{{ feynmanResult.verdict }}</div>
                <div class="rt-count">
                  讲到 {{ feynmanResult.covered.length }} 条 ·
                  漏了 {{ feynmanResult.missed.length }} 条 ·
                  引擎 {{ feynmanResult.engine }}
                </div>
                <div v-if="feynmanResult.insight" class="rt-insight">{{ feynmanResult.insight }}</div>
              </div>
            </div>

            <div v-if="feynmanResult.covered.length" class="rt-block">
              <div class="rt-block-title">讲到了</div>
              <div class="chip-list">
                <span v-for="term in feynmanResult.covered" :key="term" class="rt-chip ok">{{ term }}</span>
              </div>
            </div>

            <div v-if="feynmanResult.missed.length" class="rt-block">
              <div class="rt-block-title">漏掉的要点（这才是盲区）</div>
              <div class="stack" style="gap: 6px">
                <div v-for="item in feynmanResult.missed" :key="item.term" class="rt-missed">
                  <b>{{ item.term }}</b>
                  <span>{{ item.hint }}</span>
                </div>
              </div>
            </div>

            <div v-if="feynmanResult.suspects.length" class="rt-block">
              <div class="rt-block-title">疑似表述问题（仅供参考，不参与计分）</div>
              <div v-for="line in feynmanResult.suspects" :key="line" class="rt-suspect">{{ line }}</div>
            </div>

            <div class="rt-row">
              <button class="btn btn-ghost btn-sm" @click="resetFeynman">讲下一个知识点</button>
            </div>
          </template>
        </template>
      </div>

      <div class="card rt-side">
        <div class="card-title">熟练度错觉榜</div>
        <div class="card-sub">自测掌握分高、但讲解覆盖率低的知识点，差值越大越危险</div>
        <div v-if="!feynmanProfile?.items?.length" class="small muted" style="margin-top: 12px">
          还没有讲解记录。讲满 2 次同一个知识点，这里就会出现对比。
        </div>
        <div v-else class="stack" style="margin-top: 12px; gap: 8px">
          <div v-for="item in feynmanProfile.items" :key="item.kp_id" class="rt-illus">
            <div class="rt-illus-head">
              <b>{{ item.kp_name }}</b>
              <span v-if="item.gap >= 0.2" class="tag tag-review">错觉 {{ Math.round(item.gap * 100) }}pt</span>
              <span v-else class="tag tag-study">一致</span>
            </div>
            <div class="rt-illus-meta">
              自测 {{ Math.round((item.mastery || 0) * 100) }}% · 讲出 {{ Math.round(item.avg_coverage * 100) }}% ·
              {{ item.sessions }} 次
            </div>
          </div>
        </div>
        <div v-if="feynmanProfile?.insight" class="rt-side-note">{{ feynmanProfile.insight }}</div>
      </div>
    </div>

    <!-- ---------------- 反向判卷 ---------------- -->
    <div v-if="mode === 'reverse'" class="rt-grid">
      <div class="card rt-main">
        <div class="card-head">
          <div>
            <div class="card-title">反向判卷：AI 当学生，你当老师</div>
            <div class="card-sub">答卷里只有一处错，错在哪一步、属于哪类错、该怎么改，都由你指出</div>
          </div>
          <button v-if="task" class="btn btn-ghost btn-sm" @click="task = null; gradeResult = null">换一份</button>
        </div>

        <div v-if="!task" class="rt-empty">
          <div class="rt-empty-icon">📝</div>
          <div class="rt-empty-title">让 AI 交一份「犯了典型错误」的答卷</div>
          <div class="small muted">
            批改是考场外没人练的能力：你做错了，能不能自己发现？错误是出题时预置的，所以你的批改会被确定性核对。
          </div>
          <div class="row" style="gap: 8px; flex-wrap: wrap; justify-content: center">
            <AppSelect v-model="cause" :options="causeOptions" style="width: 160px" />
            <button class="btn" :disabled="reverseBusy" @click="startReverse">
              {{ reverseBusy ? '出题中...' : '开始批改' }}
            </button>
          </div>
        </div>

        <template v-else>
          <div class="rt-question">{{ task.question }}</div>
          <div class="rt-reason">为什么挑它：{{ task.reason }}</div>

          <div class="rt-steps">
            <button
              v-for="step in task.steps"
              :key="step.no"
              class="rt-step"
              :class="{
                picked: pickedStep === step.no,
                right: gradeResult && gradeResult.truth.error_step === step.no,
                wrong: gradeResult && pickedStep === step.no && gradeResult.truth.error_step !== step.no
              }"
              :disabled="!!gradeResult"
              @click="pickedStep = step.no"
            >
              <span class="rt-step-no">第 {{ step.no }} 步</span>
              <span class="rt-step-text">{{ step.text }}</span>
            </button>
          </div>

          <template v-if="!gradeResult">
            <div class="rt-block">
              <div class="rt-block-title">这属于哪类错因</div>
              <div class="chip-list">
                <button
                  v-for="item in CAUSES"
                  :key="item"
                  class="chip"
                  :class="{ active: pickedType === item }"
                  @click="pickedType = item"
                >
                  {{ item }}
                </button>
              </div>
            </div>
            <div class="rt-block">
              <div class="rt-block-title">该怎么改（写到能照着改的程度）</div>
              <textarea
                v-model="fixText"
                class="textarea"
                maxlength="1000"
                placeholder="例如：这一步漏了前提条件，应先说明 x≠1，再讨论单调性。"
              ></textarea>
            </div>
            <div class="rt-row">
              <span class="small muted">
                定位 45 分 · 错因 30 分 · 修正 25 分
              </span>
              <button class="btn" :disabled="reverseBusy" @click="submitGrade">
                {{ reverseBusy ? '批改核对中...' : '提交批改' }}
              </button>
            </div>
          </template>

          <template v-else>
            <div class="rt-score">
              <div class="rt-score-num">{{ gradeResult.score }}<small>分</small></div>
              <div class="rt-score-body">
                <div class="rt-verdict">{{ gradeResult.verdict }}</div>
                <div class="rt-score-bars">
                  <div class="rt-bar">
                    <span>定位 {{ gradeResult.breakdown.position.points }}/45</span>
                    <div class="rt-bar-track">
                      <i :style="{ width: (gradeResult.breakdown.position.points / 45) * 100 + '%' }"></i>
                    </div>
                  </div>
                  <div class="rt-bar">
                    <span>错因 {{ gradeResult.breakdown.type.points }}/30</span>
                    <div class="rt-bar-track">
                      <i :style="{ width: (gradeResult.breakdown.type.points / 30) * 100 + '%' }"></i>
                    </div>
                  </div>
                  <div class="rt-bar">
                    <span>修正 {{ gradeResult.breakdown.fix.points }}/25</span>
                    <div class="rt-bar-track">
                      <i :style="{ width: (gradeResult.breakdown.fix.points / 25) * 100 + '%' }"></i>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div class="rt-truth">
              <div class="rt-truth-row">
                <span>真正的错误</span>
                <strong>
                  第 {{ gradeResult.truth.error_step }} 步 · {{ gradeResult.truth.error_type }}
                </strong>
              </div>
              <div class="rt-truth-row">
                <span>错在这里</span>
                <strong>{{ gradeResult.truth.wrong_step_text }}</strong>
              </div>
              <div class="rt-truth-row">
                <span>正确写法</span>
                <strong>{{ gradeResult.truth.correct_step }}</strong>
              </div>
              <div class="rt-truth-row">
                <span>必须提到的词</span>
                <strong>
                  {{ gradeResult.truth.key_terms.join('、') }}
                  <em v-if="gradeResult.breakdown.fix.missed.length">
                    （漏了 {{ gradeResult.breakdown.fix.missed.join('、') }}）
                  </em>
                </strong>
              </div>
              <div class="rt-truth-row">
                <span>为什么会错</span>
                <strong>{{ gradeResult.truth.why }}</strong>
              </div>
            </div>

            <div class="rt-insight">{{ gradeResult.lesson }}</div>

            <div class="rt-row">
              <button class="btn btn-ghost btn-sm" @click="task = null; gradeResult = null">再来一份</button>
            </div>
          </template>
        </template>
      </div>

      <div class="card rt-side">
        <div class="card-title">辨别力画像</div>
        <div class="card-sub">能发现哪类错 × 自己常犯哪类错</div>
        <div class="rt-stats">
          <div class="rt-stat">
            <b>{{ reverseProfile?.attempts ?? 0 }}</b>
            <span>判卷</span>
          </div>
          <div class="rt-stat">
            <b>{{ reverseProfile?.avg_score ?? '—' }}</b>
            <span>平均分</span>
          </div>
          <div class="rt-stat">
            <b>{{ reverseProfile?.position_rate === null || reverseProfile?.position_rate === undefined
              ? '—' : Math.round(reverseProfile.position_rate * 100) + '%' }}</b>
            <span>定位准确</span>
          </div>
          <div class="rt-stat">
            <b>{{ reverseProfile?.type_rate === null || reverseProfile?.type_rate === undefined
              ? '—' : Math.round(reverseProfile.type_rate * 100) + '%' }}</b>
            <span>错因准确</span>
          </div>
        </div>
        <div v-if="reverseProfile?.by_type?.length" class="stack" style="gap: 6px; margin-top: 12px">
          <div v-for="item in reverseProfile.by_type" :key="item.cause" class="rt-illus">
            <div class="rt-illus-head">
              <b>{{ item.cause }}</b>
              <span class="small muted">
                {{ item.detected }}/{{ item.total || 0 }}
                <template v-if="item.rate !== null">（{{ Math.round(item.rate * 100) }}%）</template>
              </span>
            </div>
          </div>
        </div>
        <div v-if="reverseProfile?.insight" class="rt-side-note">{{ reverseProfile.insight }}</div>
      </div>
    </div>

    <!-- ---------------- 错误免疫 ---------------- -->
    <div v-if="mode === 'immune'" class="rt-grid">
      <div class="card rt-main">
        <div class="card-head">
          <div>
            <div class="card-title">错误免疫：把反复犯的错做成疫苗</div>
            <div class="card-sub">错因 × 板块出现 2 次以上才立项；诱饵选项出题时写死，选哪个规则一比对就出结果</div>
          </div>
          <button class="btn btn-ghost btn-sm" :disabled="immuneBusy" @click="startDrill(null)">
            自动挑一个抗原
          </button>
        </div>

        <div v-if="!drill" class="rt-empty">
          <div class="rt-empty-icon">🧬</div>
          <div class="rt-empty-title">同一类错换个题面又栽一次，才是真正拖分的地方</div>
          <div class="small muted">
            从下面的抗原清单里挑一个接种，或者让系统按「复发预警 → 未接种」的顺序自动挑。
          </div>
        </div>

        <template v-else>
          <div class="rt-fp-line">
            <span class="rt-fp-tag">{{ drill.fingerprint }}</span>
            <span class="small muted">
              累计 {{ drill.count }} 次 · 引擎 {{ drill.engine }}
            </span>
          </div>
          <div class="rt-question">{{ drill.question }}</div>
          <div class="rt-options">
            <button
              v-for="option in drill.options"
              :key="option.key"
              class="rt-option"
              :class="{
                picked: pickedKey === option.key,
                right: drillResult && drillResult.correct_key === option.key,
                trap: drillResult && drillResult.trap_key === option.key
              }"
              :disabled="!!drillResult"
              @click="pickedKey = option.key"
            >
              <span class="rt-option-key">{{ option.key }}</span>
              <span class="rt-option-text">{{ option.text }}</span>
            </button>
          </div>

          <div v-if="!drillResult" class="rt-row">
            <span class="small muted">一次只能答一次，答完才揭晓哪个是诱饵</span>
            <button class="btn" :disabled="immuneBusy || !pickedKey" @click="answerDrill">
              {{ immuneBusy ? '核对中...' : '提交' }}
            </button>
          </div>

          <template v-else>
            <div class="rt-result" :class="drillResult.outcome">
              <div class="rt-result-mark">
                {{ drillResult.outcome === 'guard' ? '守住' : drillResult.outcome === 'relapse' ? '复发' : '偏了' }}
              </div>
              <div class="rt-result-body">
                <div class="rt-verdict">{{ drillResult.verdict }}</div>
                <div class="rt-count">
                  抗体浓度 {{ drillResult.guards }}/{{ drillResult.guard_target }} ·
                  {{ drillResult.status_label }} · 引擎 {{ drillResult.engine }}
                </div>
              </div>
            </div>
            <div class="rt-block">
              <div class="rt-block-title">正确答案</div>
              <div class="rt-suspect" style="border-color: #a7f3d0; background: #ecfdf5">
                {{ drillResult.correct_key }}. {{ drillResult.correct_text }}
              </div>
            </div>
            <div class="rt-block">
              <div class="rt-block-title">诱饵选项（专门骗「{{ drill.cause }}」）</div>
              <div class="rt-suspect">{{ drillResult.trap_key }}. {{ drillResult.trap_text }}</div>
              <div class="small muted" style="margin-top: 6px">{{ drillResult.trap_reason }}</div>
            </div>
            <div class="rt-insight">{{ drillResult.why }}</div>
            <div class="rt-row">
              <button class="btn btn-ghost btn-sm" @click="startDrill(drill.fingerprint)">同一抗原再来一次</button>
              <button class="btn btn-ghost btn-sm" @click="drill = null; drillResult = null">换个抗原</button>
            </div>
          </template>
        </template>
      </div>

      <div class="card rt-side">
        <div class="card-title">抗原清单</div>
        <div class="card-sub">{{ immune?.note }}</div>
        <div class="rt-stats">
          <div class="rt-stat">
            <b>{{ immune?.total ?? 0 }}</b>
            <span>指纹</span>
          </div>
          <div class="rt-stat">
            <b>{{ immune?.immune ?? 0 }}</b>
            <span>已免疫</span>
          </div>
          <div class="rt-stat">
            <b>{{ immune?.relapse ?? 0 }}</b>
            <span>复发预警</span>
          </div>
          <div class="rt-stat">
            <b>{{ immuneProfile?.guard_rate === null || immuneProfile?.guard_rate === undefined
              ? '—' : Math.round(immuneProfile.guard_rate * 100) + '%' }}</b>
            <span>守住率</span>
          </div>
        </div>

        <div v-if="!immune?.items?.length" class="small muted" style="margin-top: 12px">
          还没有可接种的抗原：同一类错（错因 × 板块）出现 2 次以上才会立项。
        </div>
        <div v-else class="stack rt-fp-list">
          <button
            v-for="item in immune.items"
            :key="item.fingerprint"
            class="rt-fp"
            :class="item.status"
            @click="startDrill(item.fingerprint)"
          >
            <span class="rt-fp-main">
              <b>{{ item.cause }}</b>
              <span>· {{ item.board }}</span>
            </span>
            <span class="rt-fp-meta">
              {{ item.count }} 次 · {{ item.status_label }}
              <span class="rt-fp-go">接种 ›</span>
            </span>
          </button>
        </div>

        <div v-if="immuneProfile?.insight" class="rt-side-note">{{ immuneProfile.insight }}</div>
      </div>
    </div>
  </div>
</template>
