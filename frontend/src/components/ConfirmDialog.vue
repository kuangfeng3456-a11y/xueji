<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { confirmState, settleConfirm } from '../confirm'

const confirmButton = ref(null)
const cancelButton = ref(null)

const titleId = 'confirm-dialog-title'
const descId = 'confirm-dialog-desc'

const visible = computed(() => confirmState.open)

watch(visible, async (open) => {
  if (!open) return
  await nextTick()
  // 危险操作默认聚焦「取消」，避免误按回车直接删数据
  const target = confirmState.danger ? cancelButton.value : confirmButton.value
  target?.focus()
})

function onKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    settleConfirm(false)
  }
  if (event.key === 'Tab') {
    // 两个按钮之间循环，避免焦点跑到遮罩后的页面
    const first = cancelButton.value
    const second = confirmButton.value
    if (!first || !second) return
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      second.focus()
    } else if (!event.shiftKey && document.activeElement === second) {
      event.preventDefault()
      first.focus()
    }
  }
}
</script>

<template>
  <div
    v-if="visible"
    class="confirm-mask"
    role="presentation"
    @click.self="settleConfirm(false)"
    @keydown="onKeydown"
  >
    <div
      class="confirm-card"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="titleId"
      :aria-describedby="confirmState.message ? descId : undefined"
    >
      <h2 :id="titleId" class="confirm-title">{{ confirmState.title }}</h2>
      <p v-if="confirmState.message" :id="descId" class="confirm-message">{{ confirmState.message }}</p>
      <p v-if="confirmState.detail" class="confirm-detail">{{ confirmState.detail }}</p>

      <div class="confirm-actions">
        <button ref="cancelButton" type="button" class="btn btn-ghost" @click="settleConfirm(false)">
          {{ confirmState.cancelText }}
        </button>
        <button
          ref="confirmButton"
          type="button"
          class="btn"
          :class="confirmState.danger ? 'btn-danger' : 'btn-solid'"
          @click="settleConfirm(true)"
        >
          {{ confirmState.confirmText }}
        </button>
      </div>
    </div>
  </div>
</template>
