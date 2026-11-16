<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { store, notify } from '../store'
import DetailModal from '../components/DetailModal.vue'

const skills = ref([])
const meta = ref(null)
const loading = ref(true)
const detail = ref(null)

const agents = [
  { name: 'Planner', input: '目标、日期、可用时长、知识点树、掌握度', output: '周计划、每日任务', skill: 'plan-builder', icon: '📅' },
  { name: 'Diagnoser', input: '题目、我的答案、正确答案', output: '错因类别、关联知识点、补救建议', skill: 'mistake-diagnosis', icon: '🔍' },
  { name: 'Coach', input: '当日任务、近期状态', output: '当日提醒、鼓励与调整说明', skill: 'daily-coach', icon: '💬' },
  { name: 'Reporter', input: '一周行为与掌握度数据', output: '周报与下周重点', skill: 'weekly-review', icon: '📊' }
]

const SKILL_LINKS = {
  'skill-package-builder': { to: '/plan?tab=market&create=1', text: '去创建学科包' },
  'feynman-check': { to: '/practice?tab=reverse', text: '去讲一遍' },
  'reverse-grader': { to: '/practice?tab=reverse', text: '去批改一份答卷' },
  'error-immunity': { to: '/practice?tab=reverse', text: '去接种' }
}

function openSkill(skill) {
  detail.value = {
    title: skill.name,
    subtitle: `${skill.agent} · v${skill.version}`,
    rows: [
      { label: '能力描述', value: skill.description },
      { label: '输入', value: skill.inputs.join('、') },
      { label: '输出', value: skill.outputs.join('、') },
      { label: '执行规则', value: skill.rules.join('；') },
      { label: '大模型角色', value: skill.llm_role },
      { label: '所属智能体', value: skill.agent }
    ],
    linkTo: SKILL_LINKS[skill.name]?.to || '/plan?tab=market',
    linkText: SKILL_LINKS[skill.name]?.text || '查看学科 Skill 包'
  }
}

function openAgent(agent) {
  detail.value = {
    title: agent.name,
    subtitle: `对应 Skill：${agent.skill}`,
    rows: [
      { label: '输入', value: agent.input },
      { label: '输出', value: agent.output },
      { label: '绑定 Skill', value: agent.skill },
      { label: '运行方式', value: store.meta?.llm_enabled ? '智能讲解已开启' : '备用讲解' }
    ],
    linkTo: '/ai-lab',
    linkText: '去 AI 探针验证'
  }
}

const skillStats = computed(() => {
  return {
    total: skills.value.length,
    withLlm: skills.value.filter(s => s.llm_role && s.llm_role.includes('大模型')).length,
    withRule: skills.value.filter(s => s.rules && s.rules.length).length,
    avgRules: skills.value.length ? (skills.value.reduce((sum, s) => sum + (s.rules?.length || 0), 0) / skills.value.length).toFixed(1) : 0
  }
})

const agentStats = computed(() => {
  return {
    total: agents.length,
    planner: agents.find(a => a.name === 'Planner'),
    diagnoser: agents.find(a => a.name === 'Diagnoser'),
    coach: agents.find(a => a.name === 'Coach'),
    reporter: agents.find(a => a.name === 'Reporter')
  }
})

onMounted(async () => {
  try {
    const [skillData, metaData] = await Promise.all([api.skills(), api.meta()])
    skills.value = skillData.skills
    meta.value = metaData
    store.meta = metaData
  } catch (e) {
    notify(e.message, true)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="stack">
    <div class="hero">
      <h1>能力 Skills 化</h1>
      <p>
        计划拆解、错题归因、复习排期、周报复盘各自封装成独立 Skills，
        skill-package-builder 负责把任意学科的知识点树封装成可替换的 Skill 包。
        大模型负责理解和生成文字，排程与掌握度计算由程序规则完成，结果稳定、可复现。
        点击任意 Skill 或智能体查看完整定义。
      </p>
      <div class="hero-meta">
        <div class="hero-meta-item">
          <strong>{{ skillStats.total }}</strong>
          <span>Skills 总数</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ skillStats.withLlm }}</strong>
          <span>大模型参与</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ skillStats.avgRules }}</strong>
          <span>平均规则数</span>
        </div>
        <div class="hero-meta-item">
          <strong>{{ agentStats.total }}</strong>
          <span>智能体数</span>
        </div>
      </div>
    </div>

    <div v-if="loading" class="empty">正在加载 Skills...</div>

    <div v-else class="grid grid-2">
      <div
        v-for="skill in skills"
        :key="skill.name"
        class="skill-card click-card"
        role="button"
        tabindex="0"
        :aria-label="`查看 ${skill.name} 详情`"
        @click="openSkill(skill)"
        @keydown.enter.prevent="openSkill(skill)"
        @keydown.space.prevent="openSkill(skill)"
      >
        <div class="row-between">
          <span class="skill-name">{{ skill.name }}</span>
          <span class="tag tag-practice">{{ skill.agent }} · v{{ skill.version }}</span>
        </div>
        <div class="skill-line">{{ skill.description }}</div>
        <div class="skill-line"><b>输入：</b>{{ skill.inputs.join('、') }}</div>
        <div class="skill-line"><b>输出：</b>{{ skill.outputs.join('、') }}</div>
        <div class="skill-line"><b>规则：</b>{{ skill.rules.join('；') }}</div>
        <div class="skill-line"><b>大模型角色：</b>{{ skill.llm_role }}</div>
        <div class="click-hint"><span>查看完整定义</span><span>→</span></div>
      </div>
    </div>

    <div class="card skill-builder-card">
      <div class="card-head">
        <div>
          <div class="card-title">skill-package-builder · 把自己的学科也变成一个 Skill 包</div>
          <div class="card-sub">填名称 → 写知识点树 → 预览 → 注册并应用，四步即可复用整套排程与复习能力</div>
        </div>
        <router-link class="btn btn-sm" to="/plan?tab=market&create=1">去创建</router-link>
      </div>
      <div class="skill-line" style="margin-top: 10px">
        知识点树写法：<code>模块: 知识点(权重), 知识点(权重)</code>，每行一个模块；同名自动去重，权重夹在 0.1–5.0。
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">四个智能体的职责边界</div>
          <div class="card-sub">每个智能体对应一个 Skill，便于替换与复用 · 点击查看详情</div>
        </div>
      </div>
      <div class="stack">
        <div
          v-for="agent in agents"
          :key="agent.name"
          class="kv click-row"
          role="button"
          tabindex="0"
          @click="openAgent(agent)"
          @keydown.enter.prevent="openAgent(agent)"
          @keydown.space.prevent="openAgent(agent)"
        >
          <span style="min-width: 92px; color: var(--ink)"><b>{{ agent.icon }} {{ agent.name }}</b></span>
          <strong style="flex: 1; text-align: left">
            <div class="small muted">输入：{{ agent.input }}</div>
            <div class="small muted">输出：{{ agent.output }}</div>
            <div class="small" style="color: var(--brand-dark)">Skill：{{ agent.skill }}</div>
          </strong>
          <span class="click-arrow">→</span>
        </div>
      </div>
    </div>

    <div class="split">
      <div class="card">
        <div class="card-title">三条核心规则</div>
        <div class="stack" style="margin-top: 12px">
          <div class="kv">
            <span>掌握度更新</span>
            <strong>m_new = m_old + 0.3 × (r − m_old)</strong>
          </div>
          <div class="kv">
            <span>复习间隔</span>
            <strong>1 / 2 / 4 / 7 / 15 天，答错回到 1 天</strong>
          </div>
          <div class="kv">
            <span>任务优先级</span>
            <strong>权重 × (1 − 掌握度) × 临近系数</strong>
          </div>
        </div>
        <div class="small muted" style="margin-top: 12px; line-height: 1.8">
          临近系数 = 1 + 3 × e<sup>−剩余天数 / 14</sup>，越接近考试越高。
        </div>
      </div>

      <div class="card">
        <div class="card-title">运行环境</div>
        <div class="stack" style="margin-top: 12px" v-if="meta">
          <div class="kv"><span>应用</span><strong>{{ meta.app }} v{{ meta.version }}</strong></div>
          <div class="kv"><span>大模型</span><strong>{{ meta.llm_enabled ? meta.llm_model : '未配置，规则引擎兜底' }}</strong></div>
          <div class="kv"><span>缓存</span><strong>{{ meta.cache_backend === 'redis' ? 'Redis (DCS)' : '内存缓存（开发模式）' }}</strong></div>
          <div class="kv"><span>已注册 Skills</span><strong>{{ meta.skills.length }} 个</strong></div>
        </div>
        <div class="small muted" style="margin-top: 12px; line-height: 1.8">
          配置 <b>LLM_BASE_URL</b>、<b>LLM_API_KEY</b>、<b>LLM_MODEL</b> 后自动启用大模型能力；
          <b>REDIS_URL</b> 配置后自动切换为 Redis 缓存与限流。
        </div>
      </div>
    </div>

    <div class="split">
      <div class="card">
        <div class="card-title">Skills 设计原则</div>
        <div class="stack" style="margin-top: 12px">
          <div class="kv"><span>单一职责</span><strong>每个 Skill 只做一件事，输入输出清晰</strong></div>
          <div class="kv"><span>可替换</span><strong>学科包可替换，智能体能力不变</strong></div>
          <div class="kv"><span>可解释</span><strong>规则公开，结果可复现，不黑盒</strong></div>
          <div class="kv"><span>可插拔</span><strong>大模型可插拔，无密钥时自动降级</strong></div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">Skills 与智能体的关系</div>
        <div class="small muted" style="margin-top: 10px; line-height: 1.9">
          学科包只提供「学科知识结构」，Planner、Diagnoser、Coach、Reporter 四个智能体保持不变。
          这正是 Skills 化的价值：能力可复用，内容可替换。
          <router-link class="link-btn" to="/skills" style="margin-left: 4px">查看能力 Skills</router-link>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Skills 调用统计</div>
      <div class="grid grid-4" style="margin-top: 12px">
        <div class="stat">
          <div class="stat-label">Skills 总数</div>
          <div class="stat-value">{{ skillStats.total }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">大模型参与</div>
          <div class="stat-value">{{ skillStats.withLlm }}</div>
          <div class="stat-note">个 Skills 使用 LLM</div>
        </div>
        <div class="stat">
          <div class="stat-label">规则驱动</div>
          <div class="stat-value">{{ skillStats.withRule }}</div>
          <div class="stat-note">个 Skills 有规则</div>
        </div>
        <div class="stat">
          <div class="stat-label">平均规则数</div>
          <div class="stat-value">{{ skillStats.avgRules }}</div>
          <div class="stat-note">条 / Skill</div>
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