<script setup>
defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  rows: { type: Array, default: () => [] },
  linkText: { type: String, default: '前往详情' },
  linkTo: { type: String, default: '' }
})
defineEmits(['close'])
</script>

<template>
  <div v-if="open" class="detail-mask" @click.self="$emit('close')">
    <div class="detail-modal" role="dialog" aria-modal="true">
      <div class="detail-head">
        <div>
          <div class="detail-title">{{ title }}</div>
          <div v-if="subtitle" class="small muted">{{ subtitle }}</div>
        </div>
        <button class="detail-close" aria-label="关闭详情" @click="$emit('close')">×</button>
      </div>
      <div class="detail-rows">
        <div v-for="row in rows" :key="row.label" class="detail-row">
          <span>{{ row.label }}</span>
          <strong>{{ row.value }}</strong>
        </div>
      </div>
      <div v-if="linkTo" class="detail-foot">
        <router-link class="btn" :to="linkTo" @click="$emit('close')">{{ linkText }}</router-link>
      </div>
    </div>
  </div>
</template>