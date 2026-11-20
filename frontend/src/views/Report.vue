<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'
import DetailModal from '../components/DetailModal.vue'

const reports = ref([])
const selected = ref(null)
const loading = ref(true)
const digest = ref(null)
const generating = ref(false)
const detail = ref(null)
const consent = ref(null)
const parentReport = ref(null)
const consentLoading = ref(false)

const current = computed(() => selected.value)

const deltaText = computed(() => {
  if (!current.value) return ''
  const value = current.value.mastery_delta
  return `${value > 0 ? '+' : ''}${(value * 100).toFixed(0)} 个百分点`
})

const avgCompletion = computed(() => {
  if (!reports.value.length) return 0
  return Math.round((reports.value.reduce((sum, r) => sum + r.completion_rate, 0) / reports.value.length) * 100)
})

const bestCompletion = computed(() => {
  if (!reports.value.length) return 0
  return Math.round(Math.max(...reports.value.map((r) => r.completion_rate)) * 100)
})

const avgDelta = computed(() => {
  if (!reports.value.length) return 0
  return ((reports.value.reduce((sum, r) => sum + r.mastery_delta, 0) / reports.value.length) * 100).toFixed(0)
})

async function load() {
  if (!store.currentGoalId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    reports.value = await api.reports(store.currentGoalId)
    selected.value = reports.value[0] || null
    const board = await api.dashboard(store.currentGoalId).catch(() => null)
    digest.value = board?.today_digest || null
    await loadConsent()
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function loadConsent() {
  if (!store.currentGoalId) return
  try {
    consent.value = await api.getConsent(store.currentGoalId)
    parentReport.value = consent.value.granted
      ? await api.parentReport(store.currentGoalId)
      : null
  } catch (e) {
    /* ignore */
  }
}

async function toggleConsent() {
  if (!store.currentGoalId) return
  consentLoading.value = true
  try {
    const next = !(consent.value && consent.value.granted)
    consent.value = await api.setConsent(store.currentGoalId, next)
    if (next) {
      parentReport.value = await api.parentReport(store.currentGoalId)
      notify('已授权家长查看成长摘要')
    } else {
      parentReport.value = null
      notify('已撤销授权，家长无法再查看')
    }
  } catch (e) {
    notify(e.message, true)
  } finally {
    consentLoading.value = false
  }
}

async function generate() {
  generating.value = true
  try {
    const report = await api.createReport(store.currentGoalId)
    notify('本周周报已生成')
    await load()
    selected.value = report
  } catch (e) {
    notify(e.message, true)
  } finally {
    generating.value = false
  }
}

const exporting = ref(false)

async function exportFile(fmt) {
  if (!store.currentGoalId) return
  exporting.value = true
  try {
    if (fmt === 'json') {
      await exportReport()
    } else {
      await api.exportReportFile(store.currentGoalId, fmt)
      notify(`已导出 ${fmt.toUpperCase()}（页眉页脚含 AI 标识）`)
    }
  } catch (e) {
    notify(e.message, true)
  } finally {
    exporting.value = false
  }
}

async function exportReport() {
  if (!store.currentGoalId) return
  try {
    await api.exportReportJson(
      store.currentGoalId,
      `xueji-report-${current.value?.week_start || 'latest'}.json`
    )
    notify('周报已导出（文件内带 AI 标识与内容编号）')
  } catch (e) {
    notify(e.message === '请求失败（404）' ? '还没有周报，请先生成' : e.message, true)
  }
}

function formatRange(report) {
  return `${report.week_start.slice(5)} ~ ${report.week_end.slice(5)}`
}

function openReport(report) {
  detail.value = {
    title: formatRange(report) + ' 周报',
    subtitle: '完成率 ' + Math.round(report.completion_rate * 100) + '% · 重点：' + report.focus,
    rows: [
      { label: '周区间', value: formatRange(report) },
      { label: '完成率', value: Math.round(report.completion_rate * 100) + '%' },
      { label: '掌握度变化', value: (report.mastery_delta > 0 ? '+' : '') + (report.mastery_delta * 100).toFixed(0) + ' 个百分点' },
      { label: '下周重点', value: report.focus },
      { label: '生成时间', value: report.created_at ? report.created_at.slice(0, 16).replace('T', ' ') : '—' },
      { label: '周报内容', value: report.content }
    ]
  }
}

watch(() => store.currentGoalId, load, { immediate: true })
</script>

<template>
  <div v-if="!store.currentGoalId" class="empty">
    还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建目标。
  </div>

  <div v-else class="split">
    <div class="stack">
      <div v-if="reports.length" class="grid grid-4">
        <div class="stat">
          <div class="stat-label">累计周报</div>
          <div class="stat-value">{{ reports.length }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">平均完成率</div>
          <div class="stat-value">{{ avgCompletion }}%</div>
        </div>
        <div class="stat">
          <div class="stat-label">最佳完成率</div>
          <div class="stat-value">{{ bestCompletion }}%</div>
        </div>
        <div class="stat">
          <div class="stat-label">平均掌握度变化</div>
          <div class="stat-value" :style="{ color: avgDelta >= 0 ? '#0d9488' : '#dc2626' }">
            {{ avgDelta > 0 ? '+' : '' }}{{ avgDelta }}pp
          </div>
        </div>
      </div>

      <div v-if="digest" class="card">
        <div class="card-title">今天练完之后</div>
        <p class="small" style="margin-top: 8px">已完成：{{ digest.practiced.length ? digest.practiced.join('、') : '今天还没有完成的任务' }}</p>
        <p class="small">仍然较弱：{{ digest.still_weak.length ? digest.still_weak.join('、') : '目前没有明显弱项' }}</p>
        <p class="task-reason">下一步：{{ digest.next_practice }}</p>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">本周学习周报</div>
            <div class="card-sub">完成率与掌握度变化全部由程序统计，点评可由大模型润色</div>
          </div>
          <div class="row" style="gap: 8px; flex-wrap: wrap">
            <button class="btn btn-ghost" :disabled="!current || exporting" @click="exportFile('docx')">导出 Word</button>
            <button class="btn btn-ghost" :disabled="!current || exporting" @click="exportFile('pdf')">导出 PDF</button>
            <button class="btn btn-ghost" :disabled="!current || exporting" @click="exportFile('json')">导出 JSON</button>
            <button class="btn" :disabled="generating" @click="generate">
              {{ generating ? '生成中...' : '生成本周周报' }}
            </button>
          </div>
        </div>

        <div v-if="loading" class="empty">正在加载周报...</div>
        <div v-else-if="!current" class="empty">
          还没有周报。点击右上角「生成本周周报」，学迹会汇总这一周的任务、掌握度和错题。
        </div>
        <div v-else class="stack">
          <div class="row" style="justify-content: space-between">
            <div>
              <div class="card-title">{{ formatRange(current) }} 周报</div>
              <div class="card-sub">下周重点：{{ current.focus }}</div>
            </div>
            <span class="tag tag-review">完成率 {{ Math.round(current.completion_rate * 100) }}%</span>
          </div>

          <div class="grid grid-3">
            <div class="stat">
              <div class="stat-label">完成率</div>
              <div class="stat-value">{{ Math.round(current.completion_rate * 100) }}%</div>
              <div class="bar" style="margin-top: 8px">
                <i :style="{ width: current.completion_rate * 100 + '%' }"></i>
              </div>
            </div>
            <div class="stat">
              <div class="stat-label">掌握度变化</div>
              <div class="stat-value" :style="{ color: current.mastery_delta >= 0 ? '#0d9488' : '#dc2626' }">
                {{ deltaText }}
              </div>
              <div class="stat-note">周末均值对比周初快照</div>
            </div>
            <div class="stat">
              <div class="stat-label">下周重点</div>
              <div class="stat-value" style="font-size: 17px; line-height: 1.4">{{ current.focus }}</div>
              <div class="stat-note">自动取掌握度最低的知识点</div>
            </div>
          </div>

          <div class="card" style="background: var(--surface-2); box-shadow: none">
            <div class="pre-wrap">{{ current.content }}</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">历史周报</div>
        <div v-if="!reports.length" class="empty" style="margin-top: 12px">暂无历史周报。</div>
        <div v-else class="stack" style="margin-top: 12px">
          <div
            v-for="report in reports"
            :key="report.id"
            class="task"
            style="cursor: pointer; width: 100%"
            :style="{ borderColor: selected?.id === report.id ? '#93c5fd' : '' }"
            @click="selected = report"
          >
            <div class="task-main">
              <div class="task-title">{{ formatRange(report) }} 周报</div>
              <div class="task-meta small muted">
                完成率 {{ Math.round(report.completion_rate * 100) }}% · 掌握度变化
                {{ report.mastery_delta > 0 ? '+' : '' }}{{ (report.mastery_delta * 100).toFixed(0) }}pp · 重点
                {{ report.focus }}
              </div>
            </div>
            <button class="btn btn-ghost btn-sm" @click.stop="openReport(report)">详情</button>
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">家长授权成长报告</div>
          <div class="card-sub">学生主动授权后，家长仅能看到成长摘要，可随时撤销</div>
        </div>
        <button class="btn" :class="consent && consent.granted ? 'btn-ghost' : ''" :disabled="consentLoading" @click="toggleConsent">
          {{ consent && consent.granted ? '撤销授权' : '授权家长查看' }}
        </button>
      </div>
      <div v-if="parentReport" class="stack" style="margin-top: 10px">
        <div class="grid grid-3" style="gap: 10px">
          <div class="stat"><div class="stat-label">平均掌握度</div><div class="stat-value">{{ parentReport.avg_mastery }}%</div></div>
          <div class="stat"><div class="stat-label">7 天变化</div><div class="stat-value">{{ parentReport.mastery_delta > 0 ? '+' : '' }}{{ parentReport.mastery_delta }}pp</div></div>
          <div class="stat"><div class="stat-label">近 7 天完成率</div><div class="stat-value">{{ parentReport.completion_rate }}%</div></div>
        </div>
        <div v-for="(item, index) in parentReport.suggestions" :key="index" class="task-reason">{{ item }}</div>
        <div class="small muted">{{ parentReport.scope_note }}</div>
      </div>
      <div v-else class="empty">
        {{ consent && consent.granted ? '点击授权后可加载报告' : '尚未授权，家长无法查看成长摘要。' }}
      </div>
    </div>

    <DetailModal
      :open="Boolean(detail)"
      :title="detail?.title || ''"
      :subtitle="detail?.subtitle || ''"
      :rows="detail?.rows || []"
      @close="detail = null"
    />
  </div>
</template>
