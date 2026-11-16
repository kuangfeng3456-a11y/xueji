<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'
import { confirmAction } from '../confirm'
import DetailModal from '../components/DetailModal.vue'

const profiles = ref([])
const detail = ref(null)

function openFriend(friend) {
  detail.value = {
    title: friend.nickname,
    subtitle: `${friend.username} · ${friend.school || '未填写学校'}`,
    rows: [
      { label: '所属目标', value: friend.goal_name || '未设置' },
      { label: '连续打卡', value: `${friend.streak} 天` },
      { label: '本周完成率', value: `${Math.round(friend.completion_rate * 100)}%` },
      { label: '平均掌握度', value: `${Math.round(friend.avg_mastery * 100)}%` },
      { label: '互动建议', value: '可以约定同一时段学习，或在班级看板对比薄弱点后互相讲解。' }
    ],
    linkTo: '/class',
    linkText: '去班级看板'
  }
}
const loading = ref(true)
const keyword = ref('')
const searchResults = ref([])
const searching = ref(false)
const newUsername = ref('')
const busy = ref(false)

const me = computed(() => profiles.value.find((item) => item.is_me) || null)
const friends = computed(() => profiles.value.filter((item) => !item.is_me))
const myRank = computed(() => profiles.value.findIndex((item) => item.is_me) + 1)

async function load() {
  loading.value = true
  try {
    profiles.value = await api.buddies()
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function search() {
  if (!keyword.value.trim()) return
  searching.value = true
  try {
    searchResults.value = await api.searchUsers(keyword.value.trim())
  } catch (e) {
    notify(e.message, true)
  } finally {
    searching.value = false
  }
}

async function add(username) {
  busy.value = true
  try {
    await api.addBuddy(username)
    notify(`已和 ${username} 成为学习搭子`)
    newUsername.value = ''
    searchResults.value = []
    keyword.value = ''
    await load()
  } catch (e) {
    notify(e.message, true)
  } finally {
    busy.value = false
  }
}

async function remove(item) {
  const ok = await confirmAction({
    title: '解除搭子关系',
    message: `解除与「${item.nickname}」的学习搭子关系？`,
    detail: '解除后双方不再互相可见完成率与连续天数，已有的学习记录不受影响。',
    confirmText: '解除'
  })
  if (!ok) return
  try {
    await api.removeBuddy(item.user_id)
    notify('已解除搭子关系')
    await load()
  } catch (e) {
    notify(e.message, true)
  }
}

onMounted(load)

const buddyStats = computed(() => ({
  friends: friends.value.length,
  rank: myRank.value,
  streak: me.value ? me.value.streak || 0 : 0,
  completion: me.value ? Math.round((me.value.completion_rate || 0) * 100) : 0
}))
</script>

<template>
  <div class="stack">
    <div class="hero">
      <h1>学习搭子 · 让坚持被看见</h1>
      <p>
        连续打卡天数就是最真实的坚持证据。和同学互相可见本周完成率、掌握度与最薄弱知识点，
        不用比较谁更聪明，只比较谁更稳定。
      </p>
      <div class="hero-meta" v-if="me">
        <div class="hero-meta-item">
          <strong>#{{ myRank }}</strong>
          <span>我的排名</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ me.streak }}</strong>
          <span>连续打卡天数</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ Math.round(me.completion_rate * 100) }}%</strong>
          <span>近 7 天完成率</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ friends.length }}</strong>
          <span>学习搭子</span>
        </div>
      </div>
    </div>

    <div v-if="loading" class="empty">正在加载搭子排行...</div>

    <div v-else class="split">
      <div class="stack">
        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">连续打卡排行榜</div>
              <div class="card-sub">自己和搭子一起排名，数据来自每日任务完成记录</div>
            </div>
          </div>
          <div class="stack">
            <div
              v-for="(profile, index) in profiles"
              :key="profile.user_id"
              class="member-row"
              :class="{ 'me-row': profile.is_me }"
            >
              <div class="rank-badge" :class="`rank-${index + 1}`">{{ index + 1 }}</div>
              <div class="member-avatar">{{ profile.nickname.slice(0, 1) }}</div>
              <div class="member-main">
                <div class="member-name">
                  {{ profile.nickname }}
                  <span v-if="profile.is_me" class="tag tag-review">我</span>
                </div>
                <div class="small muted">
                  {{ profile.goal_name || '未设置目标' }}
                  <span v-if="profile.days_left !== null"> · 剩 {{ profile.days_left }} 天</span>
                  <span v-if="profile.weakest"> · 最薄弱：{{ profile.weakest }}</span>
                </div>
              </div>
              <div class="member-metrics">
                <span>连续 <b>{{ profile.streak }}</b> 天</span>
                <span>完成 <b>{{ Math.round(profile.completion_rate * 100) }}%</b></span>
                <span>掌握 <b>{{ Math.round(profile.avg_mastery * 100) }}%</b></span>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <div>
              <div class="card-title">我的学习搭子</div>
              <div class="card-sub">共 {{ friends.length }} 位</div>
            </div>
          </div>
          <div v-if="!friends.length" class="empty">
            还没有学习搭子。在右侧输入对方的用户名即可添加，对方同意后互相可见本周完成率与连续天数。
          </div>
          <div v-else class="grid grid-2">
            <div v-for="friend in friends" :key="friend.user_id" class="buddy-card click-card" role="button" tabindex="0" @click="openFriend(friend)" @keydown.enter.prevent="openFriend(friend)" @keydown.space.prevent="openFriend(friend)">
              <div class="row-between">
                <div class="row">
                  <div class="member-avatar">{{ friend.nickname.slice(0, 1) }}</div>
                  <div>
                    <div class="member-name">{{ friend.nickname }}</div>
                    <div class="small muted">{{ friend.school || '未填写学校' }}</div>
                  </div>
                </div>
                <button class="btn btn-ghost btn-sm" @click.stop="remove(friend)">解除</button>
              </div>
              <div class="buddy-stats">
                <div><b>{{ friend.streak }}</b><span>连续天数</span></div>
                <div><b>{{ Math.round(friend.completion_rate * 100) }}%</b><span>本周完成</span></div>
                <div><b>{{ Math.round(friend.avg_mastery * 100) }}%</b><span>平均掌握</span></div>
              </div>
              <div class="small muted">目标：{{ friend.goal_name || '未设置' }}</div>
            </div>
          </div>
        </div>
      </div>

      <div class="stack">
        <div class="card">
          <div class="card-title">添加学习搭子</div>
          <div class="card-sub" style="margin-bottom: 12px">按用户名添加，添加后双方互相可见</div>
          <div class="row">
            <input
              v-model.trim="newUsername"
              class="input"
              placeholder="输入对方用户名"
              style="flex: 1"
              @keyup.enter="add(newUsername)"
            />
            <button class="btn" :disabled="busy" @click="add(newUsername)">添加</button>
          </div>

          <div style="margin-top: 14px">
            <label class="small" style="font-weight: 600">搜索同学</label>
            <div class="row" style="margin-top: 8px">
              <input
                v-model.trim="keyword"
                class="input"
                placeholder="用户名或昵称关键字"
                style="flex: 1"
                @keyup.enter="search"
              />
              <button class="btn btn-ghost" :disabled="searching" @click="search">搜索</button>
            </div>
            <div v-if="searchResults.length" class="stack" style="margin-top: 10px">
              <div v-for="item in searchResults" :key="item.id" class="search-row">
                <div>
                  <b>{{ item.nickname }}</b>
                  <span class="small muted"> @{{ item.username }} · {{ item.school || '未填写学校' }}</span>
                </div>
                <button class="btn btn-sm btn-teal" @click="add(item.username)">加为搭子</button>
              </div>
            </div>
            <div v-else-if="keyword && !searching" class="small muted" style="margin-top: 8px">
              输入关键字后点击搜索。
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-title">为什么是搭子而不是排名</div>
          <div class="small muted" style="margin-top: 10px; line-height: 1.9">
            学迹只展示连续天数、完成率和掌握度，不展示分数与名次之外的隐私数据。
            目标是把「今天要不要学」变成「搭子还在学，我也学 20 分钟」。
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">学习搭子概览</div>
          <div class="card-sub">搭子数量、排名、连续打卡与完成率</div>
        </div>
      </div>
      <div class="grid grid-4" style="margin-top: 10px">
        <div class="stat">
          <div class="stat-label">学习搭子</div>
          <div class="stat-value">{{ buddyStats.friends }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">我的排名</div>
          <div class="stat-value">{{ buddyStats.rank }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">连续打卡</div>
          <div class="stat-value">{{ buddyStats.streak }}<span style="font-size: 13px"> 天</span></div>
        </div>
        <div class="stat">
          <div class="stat-label">完成率</div>
          <div class="stat-value">{{ buddyStats.completion }}%</div>
        </div>
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