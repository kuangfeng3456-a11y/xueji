<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { notify } from '../store'
import AppSelect from '../components/AppSelect.vue'

const loading = ref(true)
const bridge = ref(null)
const result = ref(null)
const classes = ref([])
const classId = ref('')
const logs = ref([])
const busy = ref('')

async function load() {
  loading.value = true
  try {
    const [status, desk, history] = await Promise.all([
      api.campusBridge(),
      api.campusWorkbench(),
      api.campusLogs()
    ])
    bridge.value = status
    classes.value = desk.classes || []
    logs.value = history.items || []
    if (!classId.value && classes.value.length) classId.value = classes.value[0].class_id
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function syncRoster() {
  busy.value = 'sync'
  try {
    result.value = await api.campusSync()
    if (result.value.status === 'error') notify(result.value.detail, true)
    else notify(result.value.detail)
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

async function pushSummary() {
  if (!classId.value) {
    notify('请先选择班级', true)
    return
  }
  busy.value = 'push'
  try {
    const data = await api.campusPush(Number(classId.value))
    result.value = data
    if (data.status === 'error') notify(data.detail, true)
    else notify(data.detail)
    logs.value = (await api.campusLogs()).items || []
  } catch (e) {
    notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

onMounted(load)
</script>

<template>
  <div class="stack">
    <div class="hero">
      <h1>教务对接</h1>
      <p>
        把班级名册同步到学迹，并把班级摘要回传给教务系统。未配置校级地址时只使用内置样例名册，不会连接真实学校，也不会保存学校账号。
      </p>
    </div>

    <div class="card">
      <div class="card-title">当前对接方式</div>
      <div v-if="loading" class="empty">正在读取...</div>
      <template v-else-if="bridge">
        <p style="margin-top: 10px">{{ bridge.note }}</p>
        <p class="small muted">方式：{{ bridge.mode === 'http' ? '已配置的教务接口' : '内置样例名册' }}</p>
        <button class="btn" :disabled="busy === 'sync'" @click="syncRoster">
          {{ busy === 'sync' ? '正在同步...' : '同步名册' }}
        </button>
      </template>
    </div>

    <div v-if="result" class="card">
      <div class="card-title">最近一次结果</div>
      <p>{{ result.detail }}</p>
      <div v-if="result.created?.length" class="stack" style="margin-top: 8px">
        <div v-for="item in result.created" :key="item.id" class="kv">
          <span>{{ item.name }}</span>
          <strong>邀请码 {{ item.invite_code }}</strong>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">回传班级摘要</div>
      <p class="card-sub">只包含人数、完成率、最薄弱知识点和需关注人数。</p>
      <div class="row" style="margin-top: 12px; gap: 8px">
        <AppSelect
          v-model="classId"
          :options="classes.map((item) => ({ value: item.class_id, label: item.name }))"
          placeholder="选择班级"
          style="width: 220px"
        />
        <button class="btn" :disabled="busy === 'push' || !classId" @click="pushSummary">
          {{ busy === 'push' ? '正在回传...' : '回传摘要' }}
        </button>
      </div>
    </div>

    <div class="card">
      <div class="card-title">对接记录</div>
      <div v-if="!logs.length" class="empty">还没有同步或回传记录。</div>
      <div v-else class="stack" style="margin-top: 8px">
        <div v-for="item in logs" :key="item.id" class="kv">
          <span>{{ item.direction === 'pull' ? '同步名册' : '回传摘要' }} · {{ item.status }}</span>
          <strong>{{ item.created_at?.replace('T', ' ') }}</strong>
        </div>
      </div>
    </div>
  </div>
</template>
