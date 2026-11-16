<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { SECTIONS, sectionByKey, tabAudience, visibleTabs } from '../sections'
import { store } from '../store'

const route = useRoute()
const router = useRouter()

const section = computed(() => sectionByKey(route.meta.section) || SECTIONS[0])

/** 超管额外看到研发内部工具；教师与教务看到班级和教务入口。 */
const showInternal = computed(() => Boolean(store.user?.is_superadmin))
const showCampus = computed(() => Boolean(store.user?.campus_access))

const navTabs = computed(() => {
  const tabs = visibleTabs(section.value, showInternal.value, showCampus.value)
  const current = section.value.tabs.find((item) => item.key === activeKey.value)
  if (current && tabAudience(current) === 'internal' && !tabs.some((item) => item.key === current.key)) {
    return [...tabs, current]
  }
  if (tabs.length) return tabs
  return section.value.tabs.filter((item) => tabAudience(item) === 'core')
})

const activeKey = computed(() => {
  const requested = String(route.query.tab || '')
  const requestedTab = section.value.tabs.find((item) => item.key === requested)
  const allowed = visibleTabs(section.value, showInternal.value, showCampus.value)
  if (requestedTab && (allowed.some((item) => item.key === requested) || tabAudience(requestedTab) === 'internal')) {
    return requested
  }
  return allowed[0]?.key || section.value.tabs.find((item) => tabAudience(item) === 'core')?.key || section.value.tabs[0].key
})

const activeTab = computed(() => section.value.tabs.find((item) => item.key === activeKey.value))

const isInternalView = computed(() => tabAudience(activeTab.value) === 'internal')

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
        :class="{ active: item.key === activeKey, 'is-internal': tabAudience(item) === 'internal' }"
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
