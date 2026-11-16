<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'
import { confirmAction } from '../confirm'
import DetailModal from '../components/DetailModal.vue'

const classes = ref([])
const activeId = ref(null)
const board = ref(null)
const loading = ref(true)
const busy = ref(false)
const detail = ref(null)

function openMember(member) {
  detail.value = {
    title: member.nickname,
    subtitle: `${member.username} · ${member.goal_name || '未设置目标'}`,
    rows: [
      { label: '所属目标', value: member.goal_name || '未设置' },
      { label: '剩余天数', value: member.days_left === null ? '—' : `${member.days_left} 天` },
      { label: '连续打卡', value: `${member.streak} 天` },
      { label: '近 7 天完成率', value: `${Math.round(member.completion_rate * 100)}%` },
      { label: '平均掌握度', value: `${Math.round(member.avg_mastery * 100)}%` },
      { label: '最薄弱知识点', value: member.weakest || '暂无' }
    ],
    linkTo: '/insights',
    linkText: '查看我的学情洞察'
  }
}

function openPoint(point) {
  detail.value = {
    title: point.name,
    subtitle: '群体薄弱知识点',
    rows: [
      { label: '平均掌握度', value: `${Math.round(point.value * 100)}%` },
      { label: '覆盖人数', value: `${point.sample_count} 人` },
      { label: '建议', value: '可安排一次班级统一复习，并让掌握度高的同学做讲解。' }
    ],
    linkTo: '/knowledge-map',
    linkText: '查看知识漏洞地图'
  }
}

const teacherData = ref(null)
const teacherLoading = ref(false)

async function openTeacher() {
  if (!activeId.value) {
    notify('请先选择一个班级', true)
    return
  }
  teacherLoading.value = true
  teacherData.value = null
  try {
    teacherData.value = await api.teacherDashboard(activeId.value)
  } catch (e) {
    notify(e.message, true)
  } finally {
    teacherLoading.value = false
  }
}

const createForm = reactive({ name: '', description: '' })
const joinCode = ref('')

const activeClass = computed(() => classes.value.find((item) => item.id === activeId.value) || null)
const isOwner = computed(() => Boolean(activeClass.value?.is_owner))

async function loadClasses(selectId) {
  loading.value = true
  try {
    classes.value = await api.classes()
    if (selectId) activeId.value = selectId
    if (!classes.value.length) {
      board.value = null
      return
    }
    if (!activeId.value || !classes.value.some((item) => item.id === activeId.value)) {
      activeId.value = classes.value[0].id
    }
    board.value = await api.classDashboard(activeId.value)
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function switchClass(id) {
  activeId.value = id
  try {
    board.value = await api.classDashboard(id)
  } catch (e) {
    notify(e.message, true)
  }
}

async function createClass() {
  if (!createForm.name.trim()) {
    notify('请填写班级名称', true)
    return
  }
  busy.value = true
  try {
    const created = await api.createClass({
      name: createForm.name.trim(),
      description: createForm.description.trim()
    })
    createForm.name = ''
    createForm.description = ''
    notify(`班级已创建，邀请码 ${created.invite_code}`)
    await loadClasses(created.id)
  } catch (e) {
    notify(e.message, true)
  } finally {
    busy.value = false
  }
}

async function joinClass() {
  if (!joinCode.value.trim()) {
    notify('请输入邀请码', true)
    return
  }
  busy.value = true
  try {
    const joined = await api.joinClass({ invite_code: joinCode.value.trim() })
    joinCode.value = ''
    notify(`已加入「${joined.name}」`)
    await loadClasses(joined.id)
  } catch (e) {
    notify(e.message, true)
  } finally {
    busy.value = false
  }
}

async function copyCode() {
  const code = activeClass.value?.invite_code
  if (!code) return
  try {
    await navigator.clipboard.writeText(code)
    notify(`邀请码 ${code} 已复制`)
  } catch (e) {
    notify(`邀请码：${code}`)
  }
}

async function removeMember(member) {
  const ok = await confirmAction({
    title: '移出班级',
    message: `将「${member.nickname}」移出班级？`,
    detail: '只解除班级关系，该成员的个人学习数据与错题不会删除。',
    confirmText: '移出',
    danger: true
  })
  if (!ok) return
  try {
    await api.removeClassMember(activeId.value, member.user_id)
    notify('已移除成员')
    await switchClass(activeId.value)
  } catch (e) {
    notify(e.message, true)
  }
}

async function deleteClass() {
  const ok = await confirmAction({
    title: '删除班级',
    message: '确定删除这个班级吗？',
    detail: '班级、邀请码与成员关系会一并删除；成员的个人学习数据保留。',
    confirmText: '删除班级',
    danger: true
  })
  if (!ok) return
  try {
    await api.deleteClass(activeId.value)
    notify('班级已删除')
    activeId.value = null
    await loadClasses()
  } catch (e) {
    notify(e.message, true)
  }
}

onMounted(() => loadClasses())
</script>

<template>
  <div class="stack">
    <div class="hero">
      <h1>班级看板</h1>
      <p>
        查看班级平均掌握度、近 7 天完成率和大家共同的薄弱点，
        找到全班卡住的地方，再决定下一节课讲什么。
      </p>
      <div class="hero-meta" v-if="board">
        <div class="hero-meta-item">
          <strong>{{ board.member_count }}</strong>
          <span>班级成员</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ board.active_members }}</strong>
          <span>近 7 天活跃</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ Math.round(board.avg_mastery * 100) }}%</strong>
          <span>平均掌握度</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ Math.round(board.avg_completion * 100) }}%</strong>
          <span>平均完成率</span>
        </div>
      </div>
    </div>

    <div v-if="loading" class="empty">正在加载班级数据...</div>

    <div v-else class="split">
      <div class="stack">
        <div v-if="!classes.length" class="card">
          <div class="empty">
            你还没有加入任何班级。可以在右侧创建班级，或用老师给你的邀请码加入已有班级。
          </div>
        </div>

        <template v-else>
          <div class="card">
            <div class="card-head">
              <div>
                <div class="card-title">{{ activeClass?.name || '选择一个班级' }}</div>
                <div v-if="activeClass" class="card-sub">
                  {{ activeClass.description || '暂无班级简介' }} · 创建者 {{ activeClass.owner_name }}
                </div>
                <div v-else class="card-sub">点击下方「＋ 创建 / 加入」新建班级，或用邀请码加入</div>
              </div>
              <button v-if="isOwner" class="btn btn-danger btn-sm" @click="deleteClass">删除班级</button>
            </div>

            <div class="class-switch">
              <button
                v-for="item in classes"
                :key="item.id"
                class="chip"
                :class="{ active: item.id === activeId }"
                @click="switchClass(item.id)"
              >
                {{ item.name }} · {{ item.member_count }} 人
              </button>
              <button class="chip" @click="activeId = null">＋ 创建 / 加入</button>
            </div>

            <div v-if="activeClass" class="invite-box">
              <div>
                <div class="small muted">班级邀请码</div>
                <div class="invite-code">{{ activeClass.invite_code }}</div>
              </div>
              <button class="btn btn-ghost btn-sm" @click="copyCode">复制邀请码</button>
            </div>

            <div v-if="board" class="stack" style="margin-top: 16px">
              <div>
                <div class="row-between small">
                  <b>群体薄弱知识点</b>
                  <span class="muted">按成员平均掌握度排序</span>
                </div>
                <div v-if="!board.weak_points.length" class="empty" style="margin-top: 8px">
                  成员还没有掌握度数据，导入资料并完成自测后这里会自动汇总。
                </div>
                <div v-else class="stack" style="margin-top: 10px">
                  <div
                    v-for="point in board.weak_points"
                    :key="point.name"
                    class="click-line"
                    style="padding: 8px; border-radius: 10px"
                    role="button"
                    tabindex="0"
                    @click="openPoint(point)"
                    @keydown.enter.prevent="openPoint(point)"
                    @keydown.space.prevent="openPoint(point)"
                  >
                    <div class="row-between small">
                      <span>{{ point.name }}（{{ point.sample_count }} 人）</span>
                      <b>{{ Math.round(point.value * 100) }}%</b>
                    </div>
                    <div class="bar" style="margin-top: 5px">
                      <i :style="{ width: Math.max(point.value * 100, 2) + '%' }"></i>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="card" v-if="board">
            <div class="card-head">
              <div>
                <div class="card-title">成员排行</div>
                <div class="card-sub">按连续打卡、近 7 天完成率与平均掌握度排序</div>
              </div>
            </div>
            <div class="stack">
              <div
                v-for="(member, index) in board.members"
                :key="member.user_id"
                class="member-row click-line"
                style="padding: 8px; border-radius: 10px"
                role="button"
                tabindex="0"
                @click="openMember(member)"
                @keydown.enter.prevent="openMember(member)"
                @keydown.space.prevent="openMember(member)"
              >
                <div class="rank-badge" :class="`rank-${index + 1}`">{{ index + 1 }}</div>
                <div class="member-avatar">{{ member.nickname.slice(0, 1) }}</div>
                <div class="member-main">
                  <div class="member-name">
                    {{ member.nickname }}
                    <span class="tag tag-pending">{{ member.username }}</span>
                    <span v-if="member.user_id === store.user?.id" class="tag tag-review">我</span>
                  </div>
                  <div class="small muted">
                    {{ member.goal_name || '未设置目标' }}
                    <span v-if="member.days_left !== null"> · 剩 {{ member.days_left }} 天</span>
                    <span v-if="member.weakest"> · 最薄弱：{{ member.weakest }}</span>
                  </div>
                </div>
                <div class="member-metrics">
                  <span>连续 <b>{{ member.streak }}</b> 天</span>
                  <span>完成 <b>{{ Math.round(member.completion_rate * 100) }}%</b></span>
                  <span>掌握 <b>{{ Math.round(member.avg_mastery * 100) }}%</b></span>
                </div>
                <button
                  v-if="isOwner && member.user_id !== store.user?.id"
                  class="btn btn-ghost btn-sm"
                  @click="removeMember(member)"
                >
                  移除
                </button>
              </div>
            </div>
          </div>
        </template>
      </div>

      <div class="stack">
        <div class="card">
          <div class="card-title">创建班级</div>
          <div class="card-sub" style="margin-bottom: 12px">教师或班长创建后，把邀请码发给同学</div>
          <div class="field">
            <label>班级名称</label>
            <input v-model.trim="createForm.name" class="input" placeholder="例如：高三（1）班" />
          </div>
          <div class="field">
            <label>班级简介（可选）</label>
            <input v-model.trim="createForm.description" class="input" placeholder="例如：备考互助小组" />
          </div>
          <button class="btn btn-block" :disabled="busy" @click="createClass">创建班级</button>
        </div>

        <div class="card">
          <div class="card-title">加入班级</div>
          <div class="card-sub" style="margin-bottom: 12px">输入老师或班长提供的 6 位邀请码</div>
          <div class="row">
            <input v-model.trim="joinCode" class="input" placeholder="请输入邀请码" style="flex: 1" />
            <button class="btn btn-ghost" :disabled="busy" @click="joinClass">加入</button>
          </div>
        </div>

        <div class="card">
          <div class="card-title">班级可以怎么用</div>
          <div class="stack" style="margin-top: 10px">
            <div class="kv"><span>共同薄弱点</span><strong>看到全班最需要补的知识点</strong></div>
            <div class="kv"><span>完成情况</span><strong>跟踪练习的完成率</strong></div>
            <div class="kv"><span>数据范围</span><strong>只展示学习方面的汇总数据</strong></div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="activeId" class="card">
      <div class="card-head">
        <div>
          <div class="card-title">教师决策台</div>
          <div class="card-sub">仅班级创建者可访问，展示聚合薄弱点、共性错因与分层建议</div>
        </div>
        <button class="btn btn-sm" :disabled="teacherLoading" @click="openTeacher">
          {{ teacherLoading ? '加载中...' : '查看教师决策台' }}
        </button>
      </div>
      <div v-if="teacherData" class="stack" style="margin-top: 10px">
        <div class="grid grid-3" style="gap: 10px">
          <div class="stat"><div class="stat-label">班级人数</div><div class="stat-value">{{ teacherData.member_count }}</div></div>
          <div class="stat"><div class="stat-label">近 7 天完成率</div><div class="stat-value">{{ Math.round(teacherData.completion_rate * 100) }}%</div></div>
          <div class="stat"><div class="stat-label">需关注</div><div class="stat-value">{{ teacherData.watch_list.length }}</div></div>
        </div>
        <div class="small muted">班级薄弱知识点</div>
        <div v-for="point in teacherData.weak_points" :key="point.kp_id" class="kv">
          <span>{{ point.name }}</span>
          <strong>{{ Math.round(point.avg_mastery * 100) }}% · {{ point.students }} 人</strong>
        </div>
        <div class="small muted">共性错因</div>
        <div v-for="err in teacherData.common_errors" :key="err.category" class="kv">
          <span>{{ err.label }}</span><strong>{{ err.count }}</strong>
        </div>
        <div class="small muted">分层</div>
        <div class="kv"><span>高掌握</span><strong>{{ teacherData.tiers.high }}</strong></div>
        <div class="kv"><span>中等</span><strong>{{ teacherData.tiers.mid }}</strong></div>
        <div class="kv"><span>需关注</span><strong>{{ teacherData.tiers.low }}</strong></div>
        <div v-for="(item, index) in teacherData.suggestions" :key="index" class="task-reason">{{ item }}</div>
        <div class="small muted">{{ teacherData.note }}</div>
      </div>
    </div>

    <DetailModal
      :open="Boolean(detail)"
      :title="detail?.title || ''"
      :subtitle="detail?.subtitle || ''"
      :rows="detail?.rows || []"
      :link-to="detail?.linkTo || ''"
      :link-text="detail?.linkText || '前往详情'"
      @close="detail = null"
    />
  </div>
</template>