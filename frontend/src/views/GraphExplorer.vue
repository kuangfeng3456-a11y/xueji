<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'

const loading = ref(true)
const syncing = ref(false)
const graph = ref(null)
const filter = ref('all')
const selectedNode = ref(null)
const nodeDetail = ref(null)
const nodeLoading = ref(false)

const nodes = computed(() => graph.value?.nodes || [])
const edges = computed(() => graph.value?.edges || [])
const stats = computed(() => graph.value?.stats || { nodes: 0, edges: 0, prerequisite: 0, confusable: 0 })
const filteredEdges = computed(() => {
  if (filter.value === 'all') return edges.value
  return edges.value.filter((item) => item.type === filter.value)
})
const avgMastery = computed(() => {
  if (!nodes.value.length) return 0
  return Math.round((nodes.value.reduce((sum, item) => sum + item.mastery, 0) / nodes.value.length) * 100)
})

const levelLabel = { excellent: '稳固', good: '可控', risk: '风险', critical: '危急' }
const levelClass = { excellent: 'tag-review', good: 'tag-study', risk: 'tag-time', critical: 'tag-skipped' }

async function load() {
  if (!store.currentGoalId) return
  if (!store.currentGoalId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    graph.value = await api.graph(store.currentGoalId)
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function syncGraph() {
  syncing.value = true
  try {
    const data = await api.graphSync(store.currentGoalId)
    notify(`关系已重建：先修 ${data.prerequisites} 条、易混淆 ${data.confusable} 条`)
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    syncing.value = false
  }
}

async function openNode(node) {
  selectedNode.value = node
  nodeLoading.value = true
  nodeDetail.value = null
  try {
    nodeDetail.value = await api.graphNode(store.currentGoalId, node.id)
  } catch (e) {
    notify(e.message, true)
  } finally {
    nodeLoading.value = false
  }
}

function closeNode() {
  selectedNode.value = null
  nodeDetail.value = null
}

watch(() => store.currentGoalId, load, { immediate: true })
onMounted(load)
</script>

<template>
  <div v-if="!store.currentGoalId" class="empty">
    还没有考试目标。请先到 <router-link class="link-btn" to="/goal">目标与资料</router-link> 创建目标。
  </div>

  <div v-else-if="loading" class="empty">正在构建知识图谱...</div>

  <div v-else class="stack">
    <div class="hero">
      <h1>知识图谱浏览器</h1>
      <p>
        图谱以知识点为节点，显式维护「先修」与「易混淆」两类关系。点击节点可查看它的先修、后继与易混淆邻居，
        用于判断漏洞是否由前置知识缺失导致，以及哪些知识点容易相互干扰。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ stats.nodes }}</strong>
          <span>知识点节点</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ stats.prerequisite }}</strong>
          <span>先修关系</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ stats.confusable }}</strong>
          <span>易混淆关系</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ avgMastery }}%</strong>
          <span>平均掌握度</span>
        </div>
      </div>
    </div>

    <div class="row-between">
      <div class="chip-list">
        <button class="chip" :class="{ active: filter === 'all' }" @click="filter = 'all'">全部关系</button>
        <button class="chip" :class="{ active: filter === 'prerequisite' }" @click="filter = 'prerequisite'">先修</button>
        <button class="chip" :class="{ active: filter === 'confusable' }" @click="filter = 'confusable'">易混淆</button>
      </div>
      <button class="btn btn-ghost btn-sm" :disabled="syncing" @click="syncGraph">
        {{ syncing ? '重建中...' : '重建关系' }}
      </button>
    </div>

    <div class="split">
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">知识点节点</div>
            <div class="card-sub">共 {{ nodes.length }} 个，点击查看邻居</div>
          </div>
        </div>
        <div v-if="!nodes.length" class="empty">暂无知识点。</div>
        <div v-else class="stack" style="margin-top: 10px; max-height: 520px; overflow-y: auto">
          <div
            v-for="node in nodes"
            :key="node.id"
            class="gap-row click-card"
            role="button"
            tabindex="0"
            @click="openNode(node)"
            @keydown.enter.prevent="openNode(node)"
            @keydown.space.prevent="openNode(node)"
          >
            <div>
              <b>{{ node.name }}</b>
              <div class="small muted">{{ node.parent || '根知识点' }} · 权重 {{ node.weight }}</div>
              <div class="bar" style="margin-top: 4px"><i :style="{ width: Math.max(node.mastery * 100, 2) + '%' }"></i></div>
            </div>
            <span class="tag" :class="levelClass[node.level] || 'tag-pending'">
              {{ Math.round(node.mastery * 100) }}% {{ levelLabel[node.level] }}
            </span>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">关系列表</div>
            <div class="card-sub">当前筛选：{{ filter === 'all' ? '全部' : filter === 'prerequisite' ? '先修' : '易混淆' }} · {{ filteredEdges.length }} 条</div>
          </div>
        </div>
        <div v-if="!filteredEdges.length" class="empty">暂无该类型关系。</div>
        <div v-else class="stack" style="margin-top: 10px; max-height: 520px; overflow-y: auto">
          <div v-for="edge in filteredEdges" :key="edge.id" class="kv">
            <span>{{ edge.from_name }} → {{ edge.to_name }}</span>
            <strong>
              <span class="tag" :class="edge.type === 'prerequisite' ? 'tag-study' : 'tag-time'">{{ edge.label }}</span>
              权重 {{ edge.weight }}
            </strong>
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">关系怎么来的</div>
      <div class="stack" style="margin-top: 10px">
        <div class="kv"><span>先修关系</span><strong>来自知识点依赖（先学 A 才能学 B）</strong></div>
        <div class="kv"><span>易混淆关系</span><strong>同一模块下相邻知识点，容易相互干扰</strong></div>
        <div class="kv"><span>用途</span><strong>漏洞修复时先查前置，复习时避免同类混淆</strong></div>
        <div class="kv"><span>可复算</span><strong>关系由规则生成，可随时「重建关系」刷新</strong></div>
      </div>
    </div>

    <div v-if="selectedNode" class="modal-mask" @click.self="closeNode">
      <div class="modal knowledge-modal">
        <div class="card-head">
          <div>
            <div class="card-title">{{ selectedNode.name }}</div>
            <div class="card-sub">
              {{ selectedNode.parent || '根知识点' }} · 掌握度 {{ Math.round(selectedNode.mastery * 100) }}%
            </div>
          </div>
          <button class="btn btn-ghost btn-sm" @click="closeNode">关闭</button>
        </div>
        <div v-if="nodeLoading" class="empty">加载邻居...</div>
        <div v-else-if="nodeDetail" class="stack">
          <div class="row-between">
            <b>邻居关系</b>
            <span class="tag tag-study">{{ nodeDetail.neighbors.length }} 条</span>
          </div>
          <div v-if="!nodeDetail.neighbors.length" class="empty">这个知识点暂时没有显式关系。</div>
          <div v-else class="stack">
            <div v-for="item in nodeDetail.neighbors" :key="item.kp_id + item.type + item.direction" class="kv">
              <span>{{ item.name }}</span>
              <strong>
                <span class="tag" :class="item.type === 'prerequisite' ? 'tag-study' : 'tag-time'">{{ item.label }}</span>
                {{ item.direction === 'out' ? '指向' : '来自' }}
              </strong>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>