<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: [String, Number, Boolean, null], default: '' },
  options: { type: Array, default: () => [] },
  placeholder: { type: String, default: '请选择' },
  disabled: { type: Boolean, default: false },
  size: { type: String, default: 'md' }
})

const emit = defineEmits(['update:modelValue', 'change'])

defineOptions({ inheritAttrs: false })

const open = ref(false)
const activeIndex = ref(-1)
const rootRef = ref(null)
const triggerRef = ref(null)
const panelRef = ref(null)
const panelStyle = ref({})

const current = computed(() => {
  const hit = props.options.find((item) => item.value === props.modelValue)
  return hit || null
})

const label = computed(() => {
  const hit = current.value
  if (!hit) return props.placeholder
  return hit.label ?? String(hit.value)
})

const hasValue = computed(() => current.value !== null)

function updatePanelPosition() {
  const el = triggerRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const viewportW = window.innerWidth || document.documentElement.clientWidth || rect.right + 16
  const viewportH = window.innerHeight || document.documentElement.clientHeight || rect.bottom + 16
  // 面板不窄于触发器，也不窄于 200px；同时避免超出视口左右边界
  const width = Math.max(120, Math.min(Math.max(rect.width, 200), viewportW - 24))
  const left = Math.max(12, Math.min(rect.left, viewportW - width - 12))
  const maxUp = rect.top - 16
  const maxDown = viewportH - rect.bottom - 16
  // 空间不足时向上展开
  const openUp = maxDown < 180 && maxUp > maxDown
  const panelMax = Math.min(300, Math.max(120, openUp ? maxUp : maxDown))
  panelStyle.value = {
    left: `${Math.round(left)}px`,
    width: `${Math.round(width)}px`,
    maxHeight: `${panelMax}px`,
    ...(openUp
      ? { bottom: `${Math.round(viewportH - rect.top + 6)}px` }
      : { top: `${Math.round(rect.bottom + 6)}px` })
  }
}

function scrollActiveIntoView() {
  nextTick(() => {
    const panel = panelRef.value
    if (!panel) return
    const node = panel.querySelector('.app-select-option.is-active')
    if (!node) return
    // 手动滚动面板自身，避免 scrollIntoView 连带滚动页面（会把面板刚算好的位置顶偏）
    const target = node.offsetTop - panel.clientHeight / 2 + node.offsetHeight / 2
    panel.scrollTop = Math.max(0, target)
  })
}

/** 页面滚动或视口变化时跟随触发器重新定位；触发器完全离开视口才关闭。 */
function onViewportChange() {
  if (!open.value) return
  const el = triggerRef.value
  if (!el) {
    closePanel()
    return
  }
  const rect = el.getBoundingClientRect()
  const viewportH = window.innerHeight || document.documentElement.clientHeight || 800
  if (rect.bottom < 0 || rect.top > viewportH) {
    closePanel()
    return
  }
  updatePanelPosition()
}

function openPanel() {
  if (props.disabled || open.value) return
  open.value = true
  const index = props.options.findIndex((item) => item.value === props.modelValue)
  activeIndex.value = index >= 0 ? index : 0
  updatePanelPosition()
  // 首帧后校正一次：Teleport 面板刚挂载时高度可能尚未确定
  requestAnimationFrame(() => {
    updatePanelPosition()
    scrollActiveIntoView()
  })
  window.addEventListener('scroll', onViewportChange, true)
  window.addEventListener('resize', onViewportChange)
  document.addEventListener('pointerdown', onDocPointerDown, true)
  document.addEventListener('keydown', onKeydown, true)
}

function closePanel() {
  if (!open.value) return
  open.value = false
  window.removeEventListener('scroll', onViewportChange, true)
  window.removeEventListener('resize', onViewportChange)
  document.removeEventListener('pointerdown', onDocPointerDown, true)
  document.removeEventListener('keydown', onKeydown, true)
}

function toggle() {
  if (open.value) closePanel()
  else openPanel()
}

function onDocPointerDown(event) {
  if (rootRef.value?.contains(event.target) || panelRef.value?.contains(event.target)) return
  closePanel()
}

function pick(option, index) {
  if (option.disabled) return
  activeIndex.value = index
  emit('update:modelValue', option.value)
  emit('change', option.value)
  closePanel()
}

function onKeydown(event) {
  if (!open.value) {
    if (event.key === 'Enter' || event.key === ' ' || event.key === 'ArrowDown') {
      event.preventDefault()
      openPanel()
    }
    return
  }
  const total = props.options.length
  if (event.key === 'Escape') {
    event.preventDefault()
    closePanel()
  } else if (event.key === 'ArrowDown') {
    event.preventDefault()
    activeIndex.value = (activeIndex.value + 1) % total
    scrollActiveIntoView()
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    activeIndex.value = (activeIndex.value - 1 + total) % total
    scrollActiveIntoView()
  } else if (event.key === 'Enter') {
    event.preventDefault()
    const option = props.options[activeIndex.value]
    if (option) pick(option, activeIndex.value)
  } else if (event.key === 'Tab') {
    closePanel()
  }
}

watch(() => props.modelValue, () => {
  if (open.value) updatePanelPosition()
})

onBeforeUnmount(closePanel)
</script>

<template>
  <div ref="rootRef" class="app-select" :class="{ 'is-open': open, 'is-disabled': disabled, [`app-select-${size}`]: true }" v-bind="$attrs">
    <button
      ref="triggerRef"
      type="button"
      class="app-select-trigger"
      :class="{ 'is-empty': !hasValue }"
      :disabled="disabled"
      :aria-expanded="open"
      role="combobox"
      aria-haspopup="listbox"
      @click="toggle"
      @keydown="onKeydown"
    >
      <span class="app-select-label">{{ label }}</span>
      <svg class="app-select-arrow" viewBox="0 0 16 16" aria-hidden="true">
        <path d="M4 6.5 8 10.5 12 6.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>

    <Teleport to="body">
      <transition name="app-select-pop">
        <div
          v-if="open"
          ref="panelRef"
          class="app-select-panel"
          :style="panelStyle"
          role="listbox"
        >
          <button
            v-for="(option, index) in options"
            :key="String(option.value) + '-' + index"
            type="button"
            class="app-select-option"
            :class="{ 'is-active': index === activeIndex, 'is-selected': option.value === modelValue, 'is-disabled': option.disabled }"
            role="option"
            :aria-selected="option.value === modelValue"
            @mouseenter="activeIndex = index"
            @click="pick(option, index)"
          >
            <span class="app-select-option-text">{{ option.label }}</span>
            <span v-if="option.hint" class="app-select-option-hint">{{ option.hint }}</span>
            <svg v-if="option.value === modelValue" class="app-select-check" viewBox="0 0 16 16" aria-hidden="true">
              <path d="M3.5 8.5 6.5 11.5 12.5 5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>
          <div v-if="!options.length" class="app-select-empty">暂无可选项</div>
        </div>
      </transition>
    </Teleport>
  </div>
</template>
