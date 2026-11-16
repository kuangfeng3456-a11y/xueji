<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { store, setGoal, currentGoal } from '../store'

const router = useRouter()
const open = ref(false)
const root = ref(null)

const current = computed(() => currentGoal())

function toggle() {
  open.value = !open.value
}

function choose(id) {
  setGoal(id)
  open.value = false
}

function go(path) {
  open.value = false
  router.push(path)
}

function onDocumentClick(event) {
  if (root.value && !root.value.contains(event.target)) open.value = false
}

onMounted(() => document.addEventListener('click', onDocumentClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocumentClick))
</script>

<template>
  <div ref="root" class="goal-switcher">
    <button class="goal-trigger" :class="{ open }" @click="toggle">
      <template v-if="current">
        <span class="goal-trigger-main">
          <span class="goal-trigger-name">{{ current.exam_name }}</span>
          <span class="goal-trigger-meta">
            剩 {{ current.days_left }} 天 · {{ current.knowledge_count }} 个知识点 · 掌握度
            {{ Math.round(current.avg_mastery * 100) }}%
          </span>
        </span>
      </template>
      <span v-else class="goal-trigger-main">
        <span class="goal-trigger-name">未设置考试目标</span>
        <span class="goal-trigger-meta">点击创建第一个目标</span>
      </span>
      <span class="goal-caret" :class="{ up: open }">▾</span>
    </button>

    <div v-if="open" class="goal-menu">
      <div class="goal-menu-title">我的考试目标</div>
      <div v-if="!store.goals.length" class="goal-menu-empty">还没有目标，先创建一个吧。</div>
      <button
        v-for="goal in store.goals"
        :key="goal.id"
        class="goal-option"
        :class="{ active: goal.id === store.currentGoalId }"
        @click="choose(goal.id)"
      >
        <span class="goal-option-head">
          <span class="goal-option-name">{{ goal.exam_name }}</span>
          <span v-if="goal.id === store.currentGoalId" class="goal-option-check">当前</span>
        </span>
        <span class="goal-option-meta">
          剩 {{ goal.days_left }} 天 · {{ goal.knowledge_count }} 个知识点 · 掌握度
          {{ Math.round(goal.avg_mastery * 100) }}% · 完成率 {{ Math.round(goal.completed_rate * 100) }}%
        </span>
      </button>

      <div class="goal-menu-sep"></div>
      <button class="goal-action" @click="go('/plan?tab=goal')"><b>＋</b> 新建考试目标</button>
      <button class="goal-action" @click="go('/plan?tab=goal')"><b>☰</b> 管理目标与学习资料</button>
      <button class="goal-action" @click="go('/plan?tab=market')"><b>◎</b> 从学科 Skill 市场导入知识点</button>
    </div>
  </div>
</template>