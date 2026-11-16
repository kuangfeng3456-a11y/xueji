<script setup>
import { computed } from 'vue'
import { store } from '../store'

const props = defineProps({
  /** bar：顶栏紧凑胶囊；panel：登录页状态卡 */
  variant: { type: String, default: 'bar' }
})

const health = computed(() => store.health || {})
const meta = computed(() => store.meta || {})
const cloud = computed(() => meta.value.huawei_cloud || {})

const items = computed(() => {
  const db = health.value.database || 'unknown'
  const cache = health.value.cache || meta.value.cache_backend || 'memory'
  const llm = health.value.llm ?? meta.value.llm_enabled
  const list = []

  list.push(
    llm
      ? { key: 'llm', label: '大模型', detail: 'DeepSeek 已接入', state: 'ok' }
      : { key: 'llm', label: '大模型', detail: '规则引擎兜底', state: 'warn' }
  )

  if (db === 'rds') {
    list.push({ key: 'rds', label: '学习数据', detail: '云端已同步', state: 'ok' })
  } else if (db === 'sqlite-fallback') {
    list.push({ key: 'rds', label: '学习数据', detail: '云端暂不可用，已改为本地保存', state: 'warn' })
  } else if (db === 'sqlite') {
    list.push({ key: 'rds', label: '学习数据', detail: '本地保存', state: 'muted' })
  } else {
    list.push({ key: 'rds', label: '数据库', detail: '检测中', state: 'muted' })
  }

  if (cache === 'redis') {
    list.push({ key: 'dcs', label: '学习加速', detail: '已开启', state: 'ok' })
  } else {
    list.push({ key: 'dcs', label: '学习加速', detail: '使用本机缓存', state: 'muted' })
  }

  const ocr = cloud.value.ocr
  const sis = cloud.value.sis
  if (ocr) {
    list.push(
      ocr === 'configured'
        ? { key: 'ocr', label: '拍题识别', detail: '已开启', state: 'ok' }
        : { key: 'ocr', label: '拍题识别', detail: '未开启', state: 'muted' }
    )
  }
  if (sis) {
    list.push(
      sis === 'configured'
        ? { key: 'sis', label: '语音能力', detail: '已开启', state: 'ok' }
        : { key: 'sis', label: '语音能力', detail: '未开启', state: 'muted' }
    )
  }
  return list
})

const degraded = computed(
  () => health.value.status === 'degraded' || health.value.database_fallback || health.value.database === 'sqlite-fallback'
)
</script>

<template>
  <div class="cloud-status" :class="['is-' + variant, { 'is-degraded': degraded }]" role="status">
    <div
      v-for="item in items"
      :key="item.key"
      class="cloud-chip"
      :class="'state-' + item.state"
      :title="item.label + ' · ' + item.detail"
    >
      <span class="status-dot" :class="item.state === 'ok' ? 'on' : item.state === 'warn' ? 'warn' : 'off'"></span>
      <span class="cloud-chip-label">{{ item.label }}</span>
      <span class="cloud-chip-detail">{{ item.detail }}</span>
    </div>
  </div>
</template>
