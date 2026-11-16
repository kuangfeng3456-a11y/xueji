<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'

/**
 * 平台管理后台（仅超级管理员）。
 *
 * 能看到什么、看不到什么，是刻意划定的：
 *   看得到 —— 账号元信息（用户名/昵称/学校/注册时间）、使用量聚合、依赖探活状态；
 *   看不到 —— 任何人的资料原文、答题内容、心理数据。管理员有运维权限，
 *             但没有「翻别人隐私」的权限，这与产品 PRD 的合规口径一致。
 */

const isAdmin = computed(() => Boolean(store.user?.is_superadmin))

const overview = ref(null)
const users = ref([])
const total = ref(0)
const keyword = ref('')
const loading = ref(false)
const system = ref(null)
const busyId = ref(0)
const tempPassword = ref(null)

const PAGE = 20

async function loadOverview() {
  try {
    overview.value = await api.adminOverview()
  } catch (e) {
    notify(e.message || '概览加载失败', true)
  }
}

async function loadUsers(offset = 0) {
  loading.value = true
  try {
    const res = await api.adminUsers(keyword.value.trim(), PAGE, offset)
    users.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    notify(e.message || '用户列表加载失败', true)
  } finally {
    loading.value = false
  }
}

async function loadSystem() {
  try {
    system.value = await api.adminSystem()
  } catch (e) {
    notify(e.message || '系统状态加载失败', true)
  }
}

async function toggleAdmin(row) {
  if (row.id === store.user?.id && row.is_superadmin) {
    notify('不能收回自己的超管权限', true)
    return
  }
  busyId.value = row.id
  try {
    const res = await api.adminSetSuperadmin(row.id, !row.is_superadmin)
    row.is_superadmin = res.is_superadmin
    notify(res.is_superadmin ? `已授予 ${row.username} 超管权限` : `已收回 ${row.username} 的超管权限`)
    loadOverview()
  } catch (e) {
    notify(e.message || '操作失败', true)
  } finally {
    busyId.value = 0
  }
}

async function resetPassword(row) {
  if (!window.confirm(`确定为「${row.username}」重置密码？原有密码将立即失效。`)) return
  busyId.value = row.id
  try {
    tempPassword.value = await api.adminResetPassword(row.id)
    notify('已生成临时口令，仅展示一次')
  } catch (e) {
    notify(e.message || '重置失败', true)
  } finally {
    busyId.value = 0
  }
}

async function copyPassword() {
  if (!tempPassword.value) return
  try {
    await navigator.clipboard.writeText(tempPassword.value.password)
    notify('临时口令已复制')
  } catch (e) {
    notify('复制失败，请手动选中复制', true)
  }
}

function shortDate(value) {
  return value ? String(value).slice(0, 10) : '—'
}

onMounted(() => {
  if (!isAdmin.value) return
  loadOverview()
  loadUsers()
  loadSystem()
})
</script>

<template>
  <div v-if="!isAdmin" class="empty">
    需要超级管理员权限。请用开发者账号登录，或让现有超管在「管理后台」中授予。
  </div>

  <div v-else class="stack">
    <!-- 概览 -->
    <section class="card">
      <div class="card-head">
        <div>
          <div class="card-title">平台概览</div>
          <div class="card-sub">账号与内容的聚合计数，不含任何个人隐私数据</div>
        </div>
        <button class="btn btn-sm btn-ghost" @click="loadOverview(); loadUsers(); loadSystem()">刷新</button>
      </div>
      <div v-if="!overview" class="empty">加载中...</div>
      <div v-else class="admin-stats">
        <div class="admin-stat"><strong>{{ overview.users }}</strong><span>注册账号</span></div>
        <div class="admin-stat"><strong>{{ overview.superadmins }}</strong><span>超级管理员</span></div>
        <div class="admin-stat"><strong>{{ overview.goals }}</strong><span>学习目标</span></div>
        <div class="admin-stat"><strong>{{ overview.knowledge_points }}</strong><span>知识点</span></div>
        <div class="admin-stat"><strong>{{ overview.tasks }}</strong><span>任务</span></div>
        <div class="admin-stat"><strong>{{ overview.quiz_attempts }}</strong><span>答题记录</span></div>
        <div class="admin-stat"><strong>{{ overview.mistakes }}</strong><span>错题</span></div>
        <div class="admin-stat"><strong>{{ overview.llm_enabled ? '在线' : '离线' }}</strong><span>模型状态</span></div>
      </div>
    </section>

    <!-- 用户与权限 -->
    <section class="card">
      <div class="card-head">
        <div>
          <div class="card-title">账号与权限</div>
          <div class="card-sub">授予管理员后可访问管理后台；重置密码会立即让原密码失效</div>
        </div>
      </div>

      <div class="admin-search">
        <input
          v-model="keyword"
          class="input"
          placeholder="搜索用户名 / 昵称 / 学校"
          @keyup.enter="loadUsers(0)"
        />
        <button class="btn" :disabled="loading" @click="loadUsers(0)">搜索</button>
        <span class="small muted">共 {{ total }} 个账号</span>
      </div>

      <div class="admin-table">
        <div class="admin-row admin-head">
          <span>账号</span>
          <span>学校</span>
          <span>使用量</span>
          <span>注册时间</span>
          <span>身份 / 操作</span>
        </div>
        <div v-for="row in users" :key="row.id" class="admin-row">
          <span class="admin-user">
            <b>{{ row.nickname || row.username }}</b>
            <i>@{{ row.username }}</i>
          </span>
          <span class="small muted">{{ row.school || '—' }}</span>
          <span class="small muted">{{ row.goal_count }} 目标 · {{ row.task_count }} 任务 · {{ row.quiz_count }} 答题</span>
          <span class="small muted">{{ shortDate(row.created_at) }}</span>
          <span class="admin-actions">
            <span v-if="row.is_superadmin" class="tag tag-conc">超管</span>
            <span v-else class="tag">学生</span>
            <button
              class="btn btn-sm btn-ghost"
              :disabled="busyId === row.id || (row.id === store.user?.id && row.is_superadmin)"
              @click="toggleAdmin(row)"
            >
              {{ row.is_superadmin ? '收回超管' : '授予超管' }}
            </button>
            <button class="btn btn-sm btn-ghost" :disabled="busyId === row.id" @click="resetPassword(row)">
              重置密码
            </button>
          </span>
        </div>
        <div v-if="!users.length && !loading" class="empty">没有匹配的账号</div>
      </div>

      <div v-if="total > PAGE" class="admin-pager">
        <button class="btn btn-sm btn-ghost" @click="loadUsers(0)">第一页</button>
        <span class="small muted">当前展示前 {{ Math.min(PAGE, total) }} 个，可用搜索缩小范围</span>
      </div>

      <div v-if="tempPassword" class="admin-temp">
        <div>
          <b>临时口令已生成</b>
          <p class="small muted">{{ tempPassword.note }}</p>
          <code class="admin-temp-code">{{ tempPassword.username }} / {{ tempPassword.password }}</code>
        </div>
        <div class="admin-temp-actions">
          <button class="btn btn-sm" @click="copyPassword">复制</button>
          <button class="btn btn-sm btn-ghost" @click="tempPassword = null">我已保存</button>
        </div>
      </div>
    </section>

    <!-- 系统状态 -->
    <section class="card">
      <div class="card-head">
        <div>
          <div class="card-title">系统依赖状态</div>
          <div class="card-sub">查看当前各项服务是否可用</div>
        </div>
      </div>
      <div v-if="!system" class="empty">加载中...</div>
      <div v-else class="stack">
        <div class="admin-sys">
          <div class="admin-sys-item">
            <span>大模型</span>
            <b :class="system.llm.enabled ? 'ok' : 'off'">{{ system.llm.enabled ? '已配置' : '未配置' }}</b>
            <i class="small muted">{{ system.llm.model }} · {{ system.llm.base_url }}</i>
          </div>
          <div class="admin-sys-item">
            <span>外部题库</span>
            <b :class="system.tiku.status === 'ok' ? 'ok' : 'off'">{{ system.tiku.status }}</b>
            <i class="small muted">{{ system.tiku.configured ? '已配置' : '未配置' }}</i>
          </div>
          <div v-for="item in system.integrations" :key="item.key" class="admin-sys-item">
            <span>{{ item.name }}</span>
            <b :class="item.status === 'ok' ? 'ok' : 'off'">{{ item.status }}</b>
            <i class="small muted">{{ item.detail }}</i>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.admin-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.admin-stat {
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px 14px;
  background: var(--surface-2);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.admin-stat strong {
  font-size: 22px;
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}

.admin-stat span {
  font-size: 12px;
  color: var(--ink-2);
}

.admin-search {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 4px 0 12px;
}

.admin-search .input {
  max-width: 280px;
}

.admin-table {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.admin-row {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1.4fr 0.7fr 1.6fr;
  gap: 10px;
  align-items: center;
  padding: 10px 8px;
  border-bottom: 1px solid var(--line);
  font-size: 13px;
}

.admin-head {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink-2);
  border-bottom: 1px solid var(--line);
}

.admin-user {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.admin-user b {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.admin-user i {
  font-style: normal;
  font-size: 11px;
  color: var(--ink-2);
}

.admin-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.admin-pager {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}

.admin-temp {
  margin-top: 14px;
  border: 1px solid rgba(37, 99, 235, 0.3);
  background: rgba(37, 99, 235, 0.06);
  border-radius: 12px;
  padding: 12px 14px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.admin-temp-code {
  display: inline-block;
  margin-top: 6px;
  padding: 6px 10px;
  border-radius: 8px;
  background: #fff;
  border: 1px solid var(--line);
  font-size: 13px;
  user-select: all;
}

.admin-temp-actions {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.admin-sys {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.admin-sys-item {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface-2);
  font-size: 13px;
}

.admin-sys-item > span {
  min-width: 150px;
  font-weight: 600;
}

.admin-sys-item b {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
}

.admin-sys-item b.ok {
  color: #0f766e;
  background: rgba(13, 148, 136, 0.12);
}

.admin-sys-item b.off {
  color: #9a3412;
  background: rgba(234, 88, 12, 0.12);
}

@media (max-width: 760px) {
  .admin-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .admin-row {
    grid-template-columns: 1fr;
    gap: 4px;
    padding: 12px 6px;
  }

  .admin-head {
    display: none;
  }
}
</style>
