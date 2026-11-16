<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { notify } from '../store'

const loading = ref(true)
const classes = ref([])
const selected = ref([])
const report = ref(null)
const running = ref(false)

const canCompare = computed(() => selected.value.length >= 2)

function toggle(id) {
  selected.value = selected.value.includes(id)
    ? selected.value.filter((item) => item !== id)
    : [...selected.value, id]
}

async function load() {
  loading.value = true
  try {
    const desk = await api.campusWorkbench()
    classes.value = desk.classes || []
    selected.value = classes.value.slice(0, 2).map((item) => item.class_id)
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function compare() {
  if (!canCompare.value) {
    notify('请至少选择两个班级', true)
    return
  }
  running.value = true
  report.value = null
  try {
    report.value = await api.campusCompare(selected.value.join(','))
  } catch (e) {
    notify(e.message, true)
  } finally {
    running.value = false
  }
}

function percent(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`
}

onMounted(load)
</script>

<template>
  <div class="stack">
    <div class="hero">
      <h1>班级报表</h1>
      <p>把你负责的班级放在一起看完成率、薄弱知识点和需要关注的人数。没有学习记录的班级会显示为空，不会用估算数字填补。</p>
    </div>

    <div class="card">
      <div class="card-title">选择班级</div>
      <div v-if="loading" class="empty">正在读取班级...</div>
      <div v-else-if="!classes.length" class="empty">还没有可对比的班级。请先在班级看板创建，或到教务对接同步名册。</div>
      <div v-else class="stack" style="margin-top: 12px">
        <label v-for="item in classes" :key="item.class_id" class="kv">
          <span>
            <input type="checkbox" :checked="selected.includes(item.class_id)" @change="toggle(item.class_id)" />
            {{ item.name }}
          </span>
          <strong>{{ item.member_count }} 人</strong>
        </label>
        <button class="btn" :disabled="running || !canCompare" @click="compare">
          {{ running ? '正在生成...' : '生成对比' }}
        </button>
      </div>
    </div>

    <div v-if="report" class="card">
      <div class="card-title">对比结果</div>
      <p class="small muted">{{ report.note }}</p>
      <div class="table-wrap" style="margin-top: 12px">
        <table class="data-table">
          <thead>
            <tr>
              <th>班级</th>
              <th>人数</th>
              <th>近 7 天完成率</th>
              <th>最薄弱知识点</th>
              <th>需关注</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in report.items" :key="item.class_id">
              <td>{{ item.name }}</td>
              <td>{{ item.member_count }}</td>
              <td>{{ percent(item.completion_rate) }}</td>
              <td>{{ item.top_weak || '暂无' }}</td>
              <td>{{ item.watch_count }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="report.lowest" class="small" style="margin-top: 12px">
        完成率较低的是「{{ report.lowest.name }}」。
      </p>
    </div>
  </div>
</template>
