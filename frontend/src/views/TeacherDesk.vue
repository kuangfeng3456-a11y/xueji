<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { notify } from '../store'
import AppSelect from '../components/AppSelect.vue'

const loading = ref(true)
const classes = ref([])
const classId = ref('')
const classOptions = computed(() => classes.value.map((item) => ({ value: item.id, label: item.name })))
const data = ref(null)
const running = ref(false)
const error = ref('')

const currentClass = computed(() => classes.value.find((item) => item.id === Number(classId.value)) || null)
const tiers = computed(() => data.value?.tiers || { high: 0, mid: 0, low: 0 })

async function loadClasses() {
  loading.value = true
  try {
    classes.value = await api.classes()
    if (!classId.value && classes.value.length) {
      classId.value = classes.value[0].id
      await loadDashboard()
    }
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function loadDashboard() {
  if (!classId.value) return
  running.value = true
  error.value = ''
  data.value = null
  try {
    data.value = await api.teacherDashboard(Number(classId.value))
  } catch (e) {
    error.value = e.message
  } finally {
    running.value = false
  }
}

onMounted(loadClasses)
</script>

<template>
  <div class="stack">
    <div class="hero">
      <h1>教师教学决策台</h1>
      <p>
        仅展示你创建或明确授权班级的聚合数据：班级薄弱知识点、共性错因、分层情况与需人工关注名单。
        优先给出可执行的干预建议，而不是给单个学生贴标签。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ classes.length }}</strong>
          <span>可访问班级</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ data ? data.member_count : '—' }}</strong>
          <span>班级人数</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ data ? Math.round(data.completion_rate * 100) + '%' : '—' }}</strong>
          <span>近 7 天完成率</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ data ? data.watch_list.length : '—' }}</strong>
          <span>需关注</span>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">选择班级</div>
          <div class="card-sub">教师决策台仅班级创建者可访问，其他成员会收到权限提示</div>
        </div>
        <div class="row" style="gap: 8px">
          <AppSelect v-model="classId" :options="classOptions" placeholder="选择班级" style="width: 180px" />
          <button class="btn" :disabled="running || !classId" @click="loadDashboard">
            {{ running ? '加载中...' : '查看决策台' }}
          </button>
        </div>
      </div>
      <div v-if="loading" class="empty" style="margin-top: 10px">正在加载班级...</div>
      <div v-else-if="!classes.length" class="empty" style="margin-top: 10px">
        还没有班级。请到 <router-link class="link-btn" to="/class">班级看板</router-link> 创建或加入班级。
      </div>
      <div v-else-if="error" class="empty" style="margin-top: 10px">{{ error }}</div>
    </div>

    <div v-if="data" class="stack">
      <div class="card">
        <div class="card-title">班级薄弱知识点</div>
        <div v-if="!data.weak_points.length" class="empty" style="margin-top: 10px">暂无足够数据。</div>
        <div v-else class="stack" style="margin-top: 10px">
          <div v-for="point in data.weak_points" :key="point.kp_id" class="kv">
            <span>{{ point.name }}</span>
            <strong>
              {{ Math.round(point.avg_mastery * 100) }}% · {{ point.students }} 人
            </strong>
          </div>
        </div>
      </div>

      <div class="split">
        <div class="card">
          <div class="card-title">共性错因</div>
          <div class="stack" style="margin-top: 10px">
            <div v-for="err in data.common_errors" :key="err.category" class="kv">
              <span>{{ err.label }}</span>
              <strong>{{ err.count }}</strong>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-title">分层情况</div>
          <div class="stack" style="margin-top: 10px">
            <div class="kv"><span>高掌握（≥70%）</span><strong>{{ tiers.high }} 人</strong></div>
            <div class="kv"><span>中等（40%-70%）</span><strong>{{ tiers.mid }} 人</strong></div>
            <div class="kv"><span>需关注（&lt;40%）</span><strong>{{ tiers.low }} 人</strong></div>
          </div>
          <div v-if="data.watch_list.length" class="stack" style="margin-top: 10px">
            <div class="small muted">需人工关注</div>
            <div v-for="item in data.watch_list" :key="item.user_id" class="small">
              · {{ item.name }}（掌握度 {{ Math.round(item.avg_mastery * 100) }}%）
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">教学干预建议</div>
        <div class="stack" style="margin-top: 10px">
          <div v-for="(item, index) in data.suggestions" :key="index" class="task-reason" style="margin-top: 0">{{ item }}</div>
        </div>
        <div class="small muted" style="margin-top: 10px">{{ data.note }}</div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">数据边界与隐私</div>
      <div class="stack" style="margin-top: 10px">
        <div class="kv"><span>聚合优先</span><strong>默认展示班级聚合，个体名单仅班级创建者可见</strong></div>
        <div class="kv"><span>不贴标签</span><strong>风险与分层仅用于教学干预参考，不作为惩罚依据</strong></div>
        <div class="kv"><span>权限</span><strong>非班级创建者访问会收到 403 提示</strong></div>
      </div>
    </div>

  </div>
</template>