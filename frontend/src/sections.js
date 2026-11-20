import Dashboard from './views/Dashboard.vue'
import Quiz from './views/Quiz.vue'
import Flashcards from './views/Flashcards.vue'
import FocusMode from './views/FocusMode.vue'
import VoiceCoach from './views/VoiceCoach.vue'

import Plan from './views/Plan.vue'
import ExamPrep from './views/ExamPrep.vue'
import GoalSetup from './views/GoalSetup.vue'
import SkillMarket from './views/SkillMarket.vue'
import Freshness from './views/Freshness.vue'

import Mistakes from './views/Mistakes.vue'
import Report from './views/Report.vue'
import AiLab from './views/AiLab.vue'
import TutorLab from './views/TutorLab.vue'
import ReverseTeach from './views/ReverseTeach.vue'

import Cockpit from './views/Cockpit.vue'
import Insights from './views/Insights.vue'
import TwinLab from './views/TwinLab.vue'
import Sprint from './views/Sprint.vue'
import KnowledgeMap from './views/KnowledgeMap.vue'
import GraphExplorer from './views/GraphExplorer.vue'
import DocumentLibrary from './views/DocumentLibrary.vue'
import RiskCenter from './views/RiskCenter.vue'
import Experiments from './views/Experiments.vue'
import Panel from './views/Panel.vue'

import ClassBoard from './views/ClassBoard.vue'
import TeacherDesk from './views/TeacherDesk.vue'
import ClassCompare from './views/ClassCompare.vue'
import AcademicBridge from './views/AcademicBridge.vue'
import SkillReview from './views/SkillReview.vue'
import ParentReport from './views/ParentReport.vue'
import Buddies from './views/Buddies.vue'
import MindCare from './views/MindCare.vue'
import FunZone from './views/FunZone.vue'

import EvidenceSpace from './views/EvidenceSpace.vue'
import AccountSettings from './views/AccountSettings.vue'
import AdminConsole from './views/AdminConsole.vue'
import Skills from './views/Skills.vue'
import Integrations from './views/Integrations.vue'

/**
 * 信息架构：商用版 5 个入口 + 1 个内部工具区。
 *
 * 每个标签带 audience 分级，决定它是否出现在导航里：
 *   core     —— 个人学习主流程，学生导航只显示这一层
 *   campus   —— 教师与教务：班级看板、教师工作台、班级报表、教务对接
 *   internal —— 运营与研发工具，只保留深链，不进入导航
 *
 * 分级只控制「入口是否展示」，路由与页面代码全部保留：
 * 运营或研发需要时用 /#/settings?tab=integrations 这类地址仍可直接访问，
 * 后续要用某个功能，把 audience 改回 core 即可恢复入口。
 */
export const AUDIENCES = ['core', 'campus']

export const SECTIONS = [
  {
    key: 'today',
    path: '/today',
    index: '01',
    title: '今日',
    sub: '现在该做什么',
    tabs: [
      { key: 'home', label: '总览', component: Dashboard, hint: '今天的下一步，以及看课到复盘的闭环' },
      { key: 'quiz', label: '随堂测', component: Quiz, hint: '对着当前知识点出题，错了进入错题本' },
      { key: 'flashcards', label: '闪卡', component: Flashcards, hint: '记忆稳定度驱动的间隔重复' },
      { key: 'focus', label: '专注', component: FocusMode, hint: '端侧在场判断与专注计时' },
      { key: 'voice', label: '语音', component: VoiceCoach, hint: '口语跟读评测，也可语音提问' }
    ]
  },
  {
    key: 'plan',
    path: '/plan',
    index: '02',
    title: '计划',
    sub: '课和任务怎么排',
    tabs: [
      { key: 'exam', label: '备考方案', component: ExamPrep, hint: '阶段划分、每日早中晚三段课与阶段模考' },
      { key: 'plan', label: '排期', component: Plan, hint: '按天查看任务，落后时一键重排' },
      { key: 'goal', label: '目标与资料', component: GoalSetup, hint: '设定考试目标并抽取知识点' },
      { key: 'market', label: '学科包', component: SkillMarket, hint: '导入经过审核的学科题库' },
      { key: 'freshness', label: '时效雷达', component: Freshness, hint: '发现资料过时与考纲变化', audience: 'internal' }
    ]
  },
  {
    key: 'practice',
    path: '/practice',
    index: '03',
    title: '练习与复盘',
    sub: '错在哪、明天怎么补',
    tabs: [
      { key: 'mistakes', label: '错题本', component: Mistakes, hint: '四类错因与掌握度变化' },
      { key: 'report', label: '周报', component: Report, hint: '完成率、变化与下周重点' },
      { key: 'probing', label: '探针与挑战', component: AiLab, hint: '主动寻找盲区与迁移压力', audience: 'internal' },
      { key: 'tutor', label: '苏格拉底导师', component: TutorLab, hint: '分级提示，不直接给答案' },
      { key: 'reverse', label: '讲与判', component: ReverseTeach, hint: '费曼讲解、反向判卷、错误免疫', audience: 'internal' }
    ]
  },
  {
    key: 'diagnosis',
    path: '/diagnosis',
    index: '04',
    title: '诊断与决策',
    sub: '现在准备得怎样',
    tabs: [
      { key: 'cockpit', label: '驾驶舱', component: Cockpit, hint: '准备度、风险与今日关键任务' },
      { key: 'insights', label: '学情洞察', component: Insights, hint: '热力图、能力雷达与疲劳干预' },
      { key: 'twin', label: '数字孪生', component: TwinLab, hint: '7/14/30 天情景推演', audience: 'internal' },
      { key: 'sprint', label: '未来模拟', component: Sprint, hint: '四种策略的区间与负荷对比', audience: 'internal' },
      { key: 'map', label: '漏洞地图', component: KnowledgeMap, hint: '先修依赖与验证题确认' },
      { key: 'graph', label: '知识图谱', component: GraphExplorer, hint: '节点、先修与易混淆边', audience: 'internal' },
      { key: 'docs', label: '可信资料库', component: DocumentLibrary, hint: 'RAG 检索与段落引用', audience: 'internal' },
      { key: 'risk', label: '风险救援', component: RiskCenter, hint: '识别风险并对比调整前后', audience: 'internal' },
      { key: 'experiments', label: '策略实验', component: Experiments, hint: '比较学习方法的小实验', audience: 'internal' },
      { key: 'panel', label: '评审团', component: Panel, hint: '多角色独立审查同一方案', audience: 'internal' },
      { key: 'evidence', label: '可信度中心', component: EvidenceSpace, hint: '每个判断可追溯到数据、模型与提示词版本', audience: 'internal' }
    ]
  },
  {
    key: 'collab',
    path: '/collab',
    index: '05',
    title: '协作与关怀',
    sub: '状态与身边的人',
    tabs: [
      { key: 'class', label: '班级看板', component: ClassBoard, hint: '群体薄弱点与完成率', audience: 'campus' },
      { key: 'teacher', label: '教师工作台', component: TeacherDesk, hint: '分层教学建议', audience: 'campus' },
      { key: 'compare', label: '班级报表', component: ClassCompare, hint: '对比多个班级的完成率与薄弱点', audience: 'campus' },
      { key: 'academic', label: '教务对接', component: AcademicBridge, hint: '同步名册并回传班级摘要', audience: 'campus' },
      { key: 'packages', label: '学科包审核', component: SkillReview, hint: '上传、审核并分享自定义学科包', audience: 'campus' },
      { key: 'parent', label: '家长报告', component: ParentReport, hint: '授权后的阶段摘要', audience: 'campus' },
      { key: 'buddies', label: '学习搭子', component: Buddies, hint: '好友打卡与连续天数', audience: 'internal' },
      { key: 'mind', label: '心理自评', component: MindCare, hint: '非诊断解读与求助渠道' },
      { key: 'rest', label: '恢复站', component: FunZone, hint: '疲劳时 5 分钟恢复' }
    ]
  },
  {
    key: 'settings',
    path: '/settings',
    index: '06',
    title: '设置',
    sub: '账号与安全',
    tabs: [
      { key: 'account', label: '账号与安全', component: AccountSettings, hint: '资料、密码与数据处置' },
      { key: 'admin', label: '管理后台', component: AdminConsole, hint: '账号权限与使用统计', audience: 'internal' },
      { key: 'skills', label: '能力扩展', component: Skills, hint: '可复用的学习技能包', audience: 'internal' },
      { key: 'integrations', label: '系统接入', component: Integrations, hint: '模型与数据服务状态', audience: 'internal' }
    ]
  }
]

export function tabAudience(tab) {
  return tab?.audience || 'core'
}

/** 该标签是否出现在导航里（隐藏的仍可通过深链访问）。 */
export function isTabVisible(tab, showInternal = false, showCampus = false) {
  const audience = tabAudience(tab)
  if (audience === 'internal') return Boolean(showInternal)
  if (audience === 'campus') return Boolean(showCampus)
  return true
}

export function visibleTabs(section, showInternal = false, showCampus = false) {
  return (section?.tabs || []).filter((tab) => isTabVisible(tab, showInternal, showCampus))
}

/** 至少有一个可见标签的板块；全部隐藏的板块整块不进导航。 */
export function visibleSections(showInternal = false, showCampus = false) {
  return SECTIONS.filter(
    (section) => section.audience !== 'internal' && visibleTabs(section, showInternal, showCampus).length > 0
  )
}

export const NAV_GROUPS = [{ label: '入口', sections: visibleSections().map((item) => item.key) }]

/** 旧地址 → 中心页 + 标签，保证历史深链不 404。 */
export const LEGACY_ROUTES = {
  '/': ['today', 'home'],
  '/quiz': ['today', 'quiz'],
  '/flashcards': ['today', 'flashcards'],
  '/focus': ['today', 'focus'],
  '/voice': ['today', 'voice'],
  '/goal': ['plan', 'goal'],
  '/market': ['plan', 'market'],
  '/freshness': ['plan', 'freshness'],
  '/mistakes': ['practice', 'mistakes'],
  '/report': ['practice', 'report'],
  '/ai-lab': ['practice', 'probing'],
  '/tutor': ['practice', 'tutor'],
  '/cockpit': ['diagnosis', 'cockpit'],
  '/insights': ['diagnosis', 'insights'],
  '/twin': ['diagnosis', 'twin'],
  '/sprint': ['diagnosis', 'sprint'],
  '/knowledge-map': ['diagnosis', 'map'],
  '/graph': ['diagnosis', 'graph'],
  '/documents': ['diagnosis', 'docs'],
  '/risk-center': ['diagnosis', 'risk'],
  '/experiments': ['diagnosis', 'experiments'],
  '/panel': ['diagnosis', 'panel'],
  '/evidence': ['diagnosis', 'evidence'],
  '/prompt-center': ['diagnosis', 'evidence'],
  '/skills': ['settings', 'skills'],
  '/admin': ['settings', 'admin'],
  '/integrations': ['settings', 'integrations'],
  '/class': ['collab', 'class'],
  '/teacher': ['collab', 'teacher'],
  '/compare': ['collab', 'compare'],
  '/academic': ['collab', 'academic'],
  '/skill-review': ['collab', 'packages'],
  '/parent': ['collab', 'parent'],
  '/buddies': ['collab', 'buddies'],
  '/mind-care': ['collab', 'mind'],
  '/fun-zone': ['collab', 'rest'],
  // 上一版中心页路径 → 新入口
  '/knowledge': ['diagnosis', 'map'],
  '/decision': ['diagnosis', 'risk'],
  '/trust': ['diagnosis', 'evidence'],
  '/community': ['collab', 'class'],
  '/care': ['collab', 'mind']
}

export function sectionByKey(key) {
  return SECTIONS.find((item) => item.key === key)
}

export function sectionByPath(path) {
  return SECTIONS.find((item) => item.path === path)
}

export function tabOf(sectionKey, tabKey) {
  const section = sectionByKey(sectionKey)
  if (!section) return null
  return section.tabs.find((item) => item.key === tabKey) || section.tabs[0]
}
