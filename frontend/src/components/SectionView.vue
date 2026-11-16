<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { SECTIONS, sectionByKey, isTabVisible, visibleTabs } from '../sections'
import { store } from '../store'

const route = useRoute()
const router = useRouter()

const section = computed(() => sectionByKey(route.meta.section) || SECTIONS[0])

/** 超管（开发者账号）额外看到研发内部工具入口。 */
const showInternal = computed(() => Boolean(store.user?.is_superadmin))

/** 导航里展示的标签：普通用户只看商用可见的模块，超管额外看到内部工具。 */
const navTabs = computed(() => {
  const tabs = visibleTabs(section.value, showInternal.value)
  // 从深链进来且当前模块是内部工具时，把它临时挂到标签栏，
  // 否则用户会看到「没有任何标签处于选中态」的空白感。
  const current = section.value.tabs.find((item) => item.key === activeKey.value)
  if (current && !isTabVisible(current, showInternal.value)) return [...tabs, current]
  return tabs.length ? tabs : section.value.tabs
})

const activeKey = computed(() => {
  const requested = String(route.query.tab || '')
  // 深链优先：内部工具也允许通过 ?tab= 直接访问。
  if (requested && section.value.tabs.some((item) => item.key === requested)) return requested
  return visibleTabs(section.value, showInternal.value)[0]?.key || section.value.tabs[0].key
})

const activeTab = computed(() => section.value.tabs.find((item) => item.key === activeKey.value))

const isInternalView = computed(() => !isTabVisible(activeTab.value, false))

function select(key) {
  if (key === activeKey.value) return
  const isDefault = key === navTabs.value[0]?.key
  router.replace({ path: section.value.path, query: isDefault ? {} : { tab: key } })
}
</script>

<template>
  <section class="hub">
    <header class="hub-head">
      <div class="hub-eyebrow">
        <span>{{ section.index }}</span>
        <i>{{ section.title }}</i>
        <em>{{ navTabs.length }} 个模块</em>
      </div>
      <h1 class="hub-title">{{ activeTab?.label }}</h1>
      <p class="hub-desc">{{ activeTab?.hint }}</p>
    </header>

    <nav class="hub-tabs" role="tablist">
      <button
        v-for="item in navTabs"
        :key="item.key"
        class="hub-tab"
        :class="{ active: item.key === activeKey, 'is-internal': !isTabVisible(item) }"
        role="tab"
        :aria-selected="item.key === activeKey"
        @click="select(item.key)"
      >
        {{ item.label }}
      </button>
    </nav>

    <div class="hub-body">
      <Suspense>
        <component :is="activeTab.component" :key="activeTab.key" />
        <template #fallback>
          <div class="skeleton-page skeleton-page-compact" aria-busy="true" aria-label="正在加载模块">
            <div class="skeleton skeleton-line w-40"></div>
            <div class="skeleton skeleton-card"></div>
            <div class="skeleton skeleton-card"></div>
          </div>
        </template>
      </Suspense>
    </div>
  </section>
</template>
