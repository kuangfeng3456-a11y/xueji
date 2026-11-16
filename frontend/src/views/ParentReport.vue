<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'

const loading = ref(true)
const consent = ref(null)
const report = ref(null)
const reports = ref([])
const saving = ref(false)

const granted = computed(() => Boolean(consent.value && consent.value.granted))
const latest = computed(() => reports.value[0] || null)

function formatRange(item) {
  if (!item) return ''
  return `${item.week_start.slice(5)} ~ ${item.week_end.slice(5)}`
}

async function load() {
  if (!store.currentGoalId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const [consentData, reportList] = await Promise.all([
      api.getConsent(store.currentGoalId),
      api.reports(store.currentGoalId)
    ])
    consent.value = consentData
    reports.value = reportList || []
    report.value = consentData.granted ? await api.parentReport(store.currentGoalId) : null
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function toggleConsent() {
  if (!store.currentGoalId) return
  saving.value = true
  try {
    const next = !granted.value
    consent.value = await api.setConsent(store.currentGoalId, next)
    if (next) {
      report.value = await api.parentReport(store.currentGoalId)
      notify('已授权家长查看成长摘要')
    } else {
      report.value = null
      notify('已撤销授权，家长无法再查看')
    }
  } catch (e) {
    notify(e.message, true)
  } finally {
    saving.value = false
  }
}

watch(() => store.currentGoalId, load, { immediate: true })
onMounted(load)
</script>

<template>
  <div v-if="!store.currentGoalId" class="empty">
    还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建目标。
  </div>

  <div v-else class="stack">
    <div class="hero">
      <h1>家长成长报告</h1>
      <p>
        只有你主动授权后，家长才能看到阶段性成长摘要：目标、进步证据与支持建议。
        默认不分享私人对话、原始错题与不必要敏感信息，你可随时撤销授权。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ granted ? '已授权' : '未授权' }}</strong>
          <span>家长访问状态</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ report ? report.avg_mastery + '%' : '—' }}</strong>
          <span>平均掌握度</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ report ? report.completion_rate + '%' : '—' }}</strong>
          <span>近 7 天完成率</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ reports.length }}</strong>
          <span>历史周报</span>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">授权管理</div>
          <div class="card-sub">
            {{ granted ? '家长当前可查看成长摘要，撤销后立即失效' : '尚未授权，家长无法查看任何成长摘要' }}
          </div>
        </div>
        <button class="btn" :class="granted ? 'btn-ghost' : ''" :disabled="saving" @click="toggleConsent">
          {{ saving ? '处理中...' : granted ? '撤销授权' : '授权家长查看' }}
        </button>
      </div>
    </div>

    <div v-if="report" class="stack">
      <div class="grid grid-3" style="gap: 12px">
        <div class="stat">
          <div class="stat-label">平均掌握度</div>
          <div class="stat-value">{{ report.avg_mastery }}%</div>
        </div>
        <div class="stat">
          <div class="stat-label">7 天变化</div>
          <div class="stat-value">{{ report.mastery_delta > 0 ? '+' : '' }}{{ report.mastery_delta }}pp</div>
        </div>
        <div class="stat">
          <div class="stat-label">距考试</div>
          <div class="stat-value">{{ report.days_left }}<span style="font-size: 13px"> 天</span></div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">给家长的支持建议</div>
        <div class="stack" style="margin-top: 10px">
          <div v-for="(item, index) in report.suggestions" :key="index" class="task-reason" style="margin-top: 0">{{ item }}</div>
        </div>
        <div class="small muted" style="margin-top: 10px">{{ report.scope_note }}</div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">历史周报摘要</div>
      <div v-if="!reports.length" class="empty" style="margin-top: 10px">还没有周报。</div>
      <div v-else class="stack" style="margin-top: 10px">
        <div v-for="item in reports.slice(0, 6)" :key="item.id" class="kv">
          <span>{{ formatRange(item) }}</span>
          <strong>完成率 {{ Math.round(item.completion_rate * 100) }}% · {{ item.focus }}</strong>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">隐私与授权边界</div>
      <div class="stack" style="margin-top: 10px">
        <div class="kv"><span>最小必要</span><strong>只分享目标、掌握度变化、完成率与支持建议</strong></div>
        <div class="kv"><span>不分享</span><strong>私人 AI 对话、原始错题详情、敏感个人信息</strong></div>
        <div class="kv"><span>可撤销</span><strong>撤销授权后家长立即无法继续访问</strong></div>
        <div class="kv"><span>可追溯</span><strong>授权与撤销都会记录时间</strong></div>
      </div>
    </div>

  </div>
</template>