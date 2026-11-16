# 5. 前端架构与实现说明

## 5.1 构建链分析

### 5.1.1 自建构建脚本 `build.mjs`

项目**同时存在** `build.mjs`（Rollup 自建）和 `vite.config.js`（标准 Vite 配置），但 `package.json` 的 `scripts.build` 指向 `node build.mjs`，且 `vite` 和 `@vitejs/plugin-vue` **未出现在 dependencies 中**，说明 Vite 配置是残留文件，实际构建走自建链路。

**工作流程：**

| 步骤 | 实现 | 备注 |
|------|------|------|
| 入口 | `src/main.js` | 单入口，IIFE 格式输出 |
| SFC 编译 | 自写 `vuePlugin()`，调用 `@vue/compiler-sfc` 的 `parse → compileScript → compileTemplate → rewriteDefault` | 手写拼接 render 函数到组件对象 |
| CSS 处理 | `.css` 文件 transform 返回 `export default {}`（空模块），`style.css` 通过 `fs.copyFileSync` 原样拷贝 | **无 CSS 模块化、无 PostCSS、无压缩** |
| 别名解析 | 硬编码 `vue` → `vue.esm-browser.prod.js`、`vue-router` → `vue-router.esm-browser.prod.js` | 仅两个别名，无 `@/` 路径别名 |
| 产物哈希 | SHA-256 前 10 位作为查询参数 `?v=xxx` 追加到 HTML 引用 | 非文件名哈希，缓存策略依赖服务端正确响应 query 变化 |
| Sourcemap | `sourcemap: false` | 生产环境无源码映射 |
| 代码分割 | `inlineDynamicImports: true`，所有代码打入单个 `app.js` | 无懒加载，首屏加载全部 33 个页面 |
| 压缩 | **未配置任何 minifier** | 产物 `app.js` 为 1.1 MB（未压缩），估计 gzip 后约 300-400 KB |
| 静态资源 | 无图片/字体处理逻辑 | 项目纯 CSS + emoji 图标，无外部资源依赖 |
| 环境变量 | 不支持 `.env`，仅通过 `window.__XUEJI_API_BASE__` 运行时注入 API 地址 | 无编译期变量替换 |

### 5.1.2 与 Vite 对比的风险评估

| 维度 | 自建方案现状 | Vite 默认能力 | 风险等级 |
|------|-------------|--------------|---------|
| HMR | ❌ 无 | ✅ 开箱即用 | 高：开发体验差，改一行需全量刷新 |
| Tree-shaking | ⚠️ Rollup 有但 IIFE + inlineDynamicImports 可能削弱效果 | ✅ ESM 原生支持 | 中 |
| CSS 处理 | ❌ 原样拷贝，无 autoprefixer/nesting | ✅ PostCSS 内置 | 中：旧浏览器兼容性问题 |
| 代码压缩 | ❌ 无 | ✅ esbuild/Terser | 高：1.1MB 未压缩影响首屏 |
| 依赖升级 | ⚠️ 手动对齐 `vue` 与 `@vue/compiler-sfc` 版本 | ✅ 插件自动适配 | 高：版本不一致会导致编译错误 |
| 生态插件 | ❌ 无 | ✅ 丰富 | 低：当前需求简单 |
| 构建速度 | ✅ 快（无 minify） | ✅ 快（esbuild） | — |

**结论**：自建构建链在当前规模下**功能可用但脆弱**。最大风险是缺少代码压缩和 CSS 预处理，以及未来 Vue 版本升级时编译器 API 变更可能导致构建脚本失效。建议保留 `vite.config.js` 作为备选迁移路径。

## 5.2 应用骨架

### 5.2.1 初始化流程

`main.js` 仅 6 行：`createApp(App).use(router).mount('#app')`。无 Pinia/Vuex、无全局错误处理器、无性能监控。样式通过 `import './style.css'` 引入（被构建脚本替换为空模块，实际靠 HTML 中的 `<link>` 标签加载）。

### 5.2.2 App.vue 布局

采用经典侧边栏 + 顶栏 + 内容区三栏布局：
- **侧边栏**：6 组导航（今日 / 计划 / 练习与复盘 / 诊断与决策 / 协作与关怀 / 设置），共 33 个入口，硬编码在 `navGroups` 数组中
- **顶栏**：显示当前路由 `meta.title/sub`，右侧嵌入 `GoalSwitcher` 组件
- **路由视图**：使用 `<transition name="page-fade" mode="out-in">` 包裹，提供页面切换动画
- **Toast**：全局通知浮层，由 `store.toast` 驱动
- **公开页面**：`route.meta.public` 为 true 时跳过侧边栏布局（仅 Login 页）

### 5.2.3 路由守卫

```js
router.beforeEach((to) => {
  if (!to.meta.public && !store.token) return { path: '/login' }
  if (to.meta.public && store.token) return { path: '/' }
})
```

逻辑简洁：无 token 跳登录，已登录访问登录页跳首页。**无异步 token 校验**，仅检查本地存储中的 token 是否存在，不验证有效性（401 由 API 层兜底）。

### 5.2.4 Hash 模式影响

使用 `createWebHashHistory()`，URL 形如 `/#/plan`。优势是部署无需服务端配置 fallback；劣势是 SEO 不友好（SPA 本身也无 SEO 需求）、部分 OAuth 回调不兼容。本项目为内部学习工具，Hash 模式合理。

## 5.3 状态管理

### 5.3.1 自研 reactive store

**未使用 Pinia 或 Vuex**。`store.js` 导出一个 `reactive()` 对象：

```js
export const store = reactive({
  token: session.token || '',
  user: session.user || null,
  goals: [],
  currentGoalId: storedGoal > 0 ? storedGoal : null,
  meta: null,
  toast: null
})
```

所有页面通过 `import { store } from '../store'` 直接读写同一个响应式对象。这种方式在小型项目中可行，但缺少以下能力：
- 无 action/mutation 约束，任何组件可直接修改任意字段
- 无 devtools 时间旅行调试
- 无模块化拆分，随着状态增长会变得难以维护

### 5.3.2 Token 存储与安全

Token 存储在 `localStorage` 的 `xueji_session` 键中，JSON 格式 `{ token, user }`。

**XSS 风险评估**：
- Token 以明文 JSON 存于 localStorage，任何 XSS 漏洞都可读取
- 未设置 CSP 头（需后端配合）
- 但本项目为内网/演示场景，风险可控
- 401 时自动清除 session 并跳转登录页，有一定兜底

### 5.3.3 目标切换机制

`currentGoalId` 持久化到 `localStorage('xueji_goal')`。切换时调用 `setGoal(id)` 更新 store 和 localStorage。各页面通过 `watch(() => store.currentGoalId, load, { immediate: true })` 监听变化并重新加载数据。`syncGoalSelection()` 确保当前选中的 goal 存在于列表中，不存在则自动回退到第一个。

**潜在问题**：`currentGoal()` 是普通函数而非 computed，每次调用都执行 `find()`，在高频渲染场景中可能有性能开销。

## 5.4 API 层

### 5.4.1 封装方式

`api.js` 基于原生 `fetch` 封装了统一的 `request()` 函数，导出 `api` 对象包含 **约 90 个** API 方法。

| 特性 | 实现 |
|------|------|
| baseURL | `/api`（可通过 `window.__XUEJI_API_BASE__` 覆盖） |
| 鉴权注入 | 每次请求从 localStorage 读取 token，设置 `Authorization: Bearer xxx` |
| 401 处理 | 清除 session → 跳转 `#/login` → 抛出错误 |
| 错误解析 | 尝试解析 FastAPI 格式的 `detail` 字段（字符串或数组） |
| FormData | 检测 `body instanceof FormData` 时不设置 Content-Type |
| 超时 | ❌ **未设置** |
| 重试 | ❌ 无 |
| 取消 | ❌ 无 AbortController |
| 并发控制 | ❌ 无 |

### 5.4.2 值得注意的设计

- `authToken()` 每次都重新读 localStorage 而非使用 store 中的 token，保证获取最新值
- 401 跳转使用 `location.hash = '#/login'` 而非 router.push，避免循环依赖
- 204 响应返回 null，非空响应先 `text()` 再 `JSON.parse()`，容错性好

## 5.5 页面清单

| 页面 | 路由 | 用途 | API 调用数 | 行数 | 完整度 |
|------|------|------|-----------|------|--------|
| Dashboard | `/` | 今日概览、任务、薄弱点、教练提醒 | 3 | 365 | ✅ 完整 |
| Plan | `/plan` | 计划生成/重排/按天查看任务 | 9 | 387 | ✅ 完整 |
| Mistakes | `/mistakes` | 错题录入(含拍照)、归因、掌握度 | 9 | 469 | ✅ 完整 |
| FocusMode | `/focus` | 摄像头监督专注、倒计时、违约记录 | 7 | 591 | ✅ 完整 |
| GoalSetup | `/goal` | 目标CRUD、资料导入、知识点管理 | 11 | 474 | ✅ 完整 |
| Login | `/login` | 登录/注册、演示账号、运行时状态 | 2 | 263 | ✅ 完整 |
| VoiceCoach | `/voice` | 语音问答、ASR/TTS、微信风格聊天 | 1 | 240 | ✅ 完整 |
| Flashcards | `/flashcards` | 间隔重复闪卡、键盘快捷键 | 3 | 423 | ✅ 完整 |
| Quiz | `/quiz` | AI出题、判分、错因归因 | 3 | 381 | ✅ 完整 |
| Insights | `/insights` | 热力图、能力雷达、疲劳、徽章 | 4 | 493 | ✅ 完整 |
| Cockpit | `/cockpit` | 准备度、风险提示、关键任务 | 6 | 386 | ✅ 完整 |
| KnowledgeMap | `/knowledge-map` | 知识漏洞地图、先修依赖、验证题 | 10 | 655 | ✅ 完整 |
| RiskCenter | `/risk-center` | 风险识别、一键调整、前后对比 | 3 | 287 | ✅ 完整 |
| Experiments | `/experiments` | 策略对比实验 | 6 | 476 | ✅ 完整 |
| AiLab | `/ai-lab` | AI探针、盲区挑战 | 8 | 411 | ✅ 完整 |
| Panel | `/panel` | 多智能体评审团 | 4 | 307 | ✅ 完整 |
| Freshness | `/freshness` | 内容时效扫描 | 3 | 296 | ✅ 完整 |
| EvidenceSpace | `/evidence` | 学习证据链追溯 | 3 | 195 | ✅ 完整 |
| Sprint | `/sprint` | 未来模拟、多方案对比 | 4 | 296 | ✅ 完整 |
| Integrations | `/integrations` | 系统接入状态面板 | 8 | 448 | ✅ 完整 |
| Report | `/report` | 周报复盘 | 6 | 264 | ✅ 完整 |
| ClassBoard | `/class` | 班级看板、成员排行 | 8 | 389 | ✅ 完整 |
| Buddies | `/buddies` | 学习搭子、好友打卡 | 4 | 270 | ✅ 完整 |
| SkillMarket | `/market` | 学科Skill包导入 | 8 | 538 | ✅ 完整 |
| Skills | `/skills` | 能力Skills展示 | 1 | 247 | ⚠️ 基本可用 |
| TutorLab | `/tutor` | 苏格拉底导师、分级提示 | 4 | 227 | ✅ 完整 |
| TwinLab | `/twin` | 数字孪生推演 | 5 | 252 | ✅ 完整 |
| DocumentLibrary | `/documents` | RAG检索、段落定位 | 3 | 148 | ⚠️ 基本可用 |
| TeacherDesk | `/teacher` | 教师工作台 | 2 | 147 | ⚠️ 基本可用 |
| ParentReport | `/parent` | 家长成长报告 | 5 | 146 | ⚠️ 基本可用 |
| EvalCenter | `/eval-center` | AI评测基准 | 3 | 195 | ✅ 完整 |
| GraphExplorer | `/graph` | 知识图谱可视化 | 3 | 203 | ✅ 完整 |
| MindCare | `/mind-care` | 心理量表自评 | 4 | 327 | ✅ 完整 |
| FunZone | `/fun-zone` | 娱乐放松(联网内容) | 6 | 270 | ✅ 完整 |

**完整度分布**：完整 29 个，基本可用 4 个（Skills/DocumentLibrary/TeacherDesk/ParentReport），骨架/占位 0 个。所有页面均有空状态处理和加载态。

## 5.6 组件与复用

### 5.6.1 五个公共组件

| 组件 | 职责 | 被引用次数 |
|------|------|-----------|
| TaskCard.vue | 任务卡片：状态标签、完成/跳过、难度反馈、精简档位 | Dashboard, Plan, FocusMode 等 |
| GoalSwitcher.vue | 顶栏目标下拉选择器，含新建/管理快捷入口 | App.vue（全局） |
| DetailModal.vue | 通用详情弹窗：标题+KV列表+链接按钮 | Dashboard, Plan, GoalSetup, Cockpit 等 |
| TaskPracticeModal.vue | 任务关联的即时练习：AI出题→作答→判分→标记完成 | Dashboard, Plan |
| ModuleAI.vue | 模块级AI分析卡片：一键调用大模型生成洞察与建议 | 几乎所有核心页面 |

### 5.6.2 重复代码问题

**确认存在的复制粘贴：**

1. **`typeLabel` 字典**：在 `TaskCard.vue:12`、`FocusMode.vue:53`、`Plan.vue:161` 三处完全相同地定义了 `{ study: '学习', review: '复习', practice: '练习', remedial: '补救' }`
2. **`formatDay()` 函数**：`TaskCard.vue:27-38` 和 `Plan.vue:66-75` 各有一份几乎相同的日期格式化逻辑（Plan 版多了前缀"今天·"）
3. **`statusLabel` 字典**：同样在 TaskCard 和 Plan 中重复定义
4. **统计卡片模式**：多个页面（Dashboard、Plan、Mistakes、FocusMode、GoalSetup、Cockpit 等）反复使用相同的 `<div class="stat"><div class="stat-label">...<div class="stat-value">...` 结构，未抽取为 StatCard 组件
5. **KV 列表模式**：`<div class="kv"><span>...<strong>...` 在 DetailModal 内外大量重复

**评估**：对于一个竞赛项目、33 个页面的体量，这种程度的重复尚可接受，但若继续迭代应优先提取 StatCard、KvList 等基础组件。

## 5.7 样式体系

### 5.7.1 规模与组织

`style.css` 共 **5103 行**，是一个单文件全局样式表。按功能区块用注释分隔（如 `/* ===== 班级看板 ===== */`），包含约 20 个区块。

### 5.7.2 设计系统

- **CSS 变量**：`:root` 定义了 14 个语义变量（`--bg`, `--surface`, `--ink`, `--brand`, `--teal`, `--amber`, `--danger`, `--violet`, `--radius`, `--shadow` 等）
- **组件类**：`.card`, `.btn`, `.tag`, `.stat`, `.bar`, `.task`, `.hero`, `.empty`, `.modal` 等构成了一套完整的基础 UI 组件库
- **网格系统**：`.grid-2/3/4`, `.split`, `.stack`, `.row`, `.row-between` 提供布局能力
- **标签体系**：`.tag-study/review/practice/remedial/done/pending/skipped/conc/method/careless/time` 覆盖所有业务状态

### 5.7.3 响应式支持

三个断点：`@media (max-width: 980px)`、`760px`、`480px`。覆盖了：
- 网格列数递减（4→2→1）
- 侧边栏变为抽屉式（fixed + transform）
- 登录页隐藏左侧视觉区
- 字号/间距缩小

**移动端适配较完善**，但侧边栏在平板尺寸（760-980px）仍为固定宽度 232px，可能挤压内容区。

### 5.7.4 暗色模式

❌ **不支持**。所有 `brand-dark` 引用仅为颜色变量名，无 `prefers-color-scheme` 媒体查询。

## 5.8 浏览器能力使用

### 5.8.1 摄像头抓拍（FocusMode + Mistakes）

- **FocusMode**：`getUserMedia({ video: { width: 640, height: 480 }, audio: false })`，每 60 秒通过 Canvas 抓取 160×120 缩略图上传作为"学习见证"
- **端侧在场检测**：计算帧平均亮度和像素差异，低于阈值判定为"离开"（`avg < 12 || avgDiff < 0.6`），纯客户端计算，不上传原图
- **Mistakes**：支持摄像头拍照上传错题，Canvas 压缩为 JPEG 0.85 质量
- **降级**：两处均检查 `navigator.mediaDevices?.getUserMedia`，不支持时提示使用文件选择
- **清理**：`onBeforeUnmount` 中调用 `stream.getTracks().forEach(t => t.stop())`，✅ 正确释放

**隐私考虑**：UI 文案明确标注"不上传人脸识别结果""不上传原图"，仅上传低分辨率快照。但缺乏正式的隐私政策弹窗或用户授权记录。

### 5.8.2 语音识别与合成（VoiceCoach）

- **ASR**：使用 `window.SpeechRecognition || window.webkitSpeechRecognition`，语言 `zh-CN`，单次识别模式
- **TTS**：使用 `SpeechSynthesisUtterance`，语言 `zh-CN`，语速 1.02
- **降级**：检测 `speechSupported` 和 `synthesisSupported`，不支持时禁用按钮并提示
- **清理**：`onBeforeUnmount` 中停止识别和朗读，✅ 正确

### 5.8.3 Web Audio 白噪音（FocusMode）

使用 `AudioContext` 合成三种背景音：
- **纯音 432Hz**：OscillatorNode sine 波
- **雨声**：白噪声 + highpass 滤波器 1200Hz
- **咖啡厅**：布朗噪声近似（一阶积分平滑）+ lowpass 700Hz

**降级**：检查 `window.AudioContext || window.webkitAudioContext`，不支持时 toast 提示。切换音效时先 `stopNoise()` 再 `startNoise()`，✅ 正确关闭旧上下文。

## 5.9 前端质量问题

### 5.9.1 内存泄漏风险

| 文件 | 问题 | 严重度 |
|------|------|--------|
| FocusMode.vue | `tickTimer = setInterval(tick, 1000)` 在 `onMounted` 创建，`cleanup()` 中清除 ✅ | 已修复 |
| FocusMode.vue | `snapshotTimer = setInterval(captureSnapshot, 60000)` 在 `cleanup()` 中清除 ✅ | 已修复 |
| FocusMode.vue | `document.addEventListener('visibilitychange', ...)` 在 `cleanup()` 中移除 ✅ | 已修复 |
| Flashcards.vue | `window.addEventListener('keydown', onKey)` 在 `onBeforeUnmount` 中移除 ✅ | 已修复 |
| VoiceCoach.vue | recognition/synthesis 在 `onBeforeUnmount` 中停止 ✅ | 已修复 |
| Mistakes.vue | cameraStream 在 `onBeforeUnmount` 中关闭 ✅ | 已修复 |
| GoalSwitcher.vue | document click 监听在 `onBeforeUnmount` 中移除 ✅ | 已修复 |
| store.js | `toastTimer = setTimeout(...)` 每次 notify 时 clearTimeout ✅ | 已修复 |

**结论**：定时器/事件监听/媒体流的清理做得**比较完善**，未发现明显的内存泄漏。

### 5.9.2 缺失的错误处理

- **api.js 无超时**：fetch 请求无 AbortController 超时，网络挂起时 UI 会无限等待
- **api.js 无请求取消**：页面快速切换时，前一个页面的请求完成后可能更新已卸载组件的状态（Vue 不会报错但浪费资源）
- **Dashboard.vue `load()` 失败后 `data` 保持旧值**：如果首次加载成功、后续刷新失败，用户看到的是过期数据而无提示

### 5.9.3 性能问题

- **单 bundle 1.1MB**：33 个页面全部打入一个文件，无路由级代码分割。首屏加载包含大量未使用的页面代码
- **KnowledgeMap.vue 655 行**：最大的单文件，内含 SVG 图谱渲染逻辑，大量 DOM 操作可能导致卡顿
- **无虚拟滚动**：Plan 页的任务列表、Mistakes 的错题列表、ClassBoard 的成员列表均直接 `v-for` 渲染，数据量大时会卡顿
- **style.css 5103 行全量加载**：无按需加载或 CSS-in-JS

### 5.9.4 可访问性问题

- 大部分交互元素使用了 `role="button"` + `tabindex="0"` + `@keydown.enter/space` ✅
- DetailModal 有 `role="dialog" aria-modal="true"` ✅
- 但大量 `<button>` 缺少 `aria-label`（如 GoalSwitcher 的触发按钮）
- 表单输入缺少 `id`/`for` 关联（Login 页除外）
- 颜色对比度未经验证（浅色文字 `#94a3b8` 在白色背景上可能不达标）

### 5.9.5 其他问题

- **硬编码文案**：所有中文文案直接写在模板中，无 i18n 支持。对于竞赛项目可接受，但国际化成本高
- **confirm() 阻塞**：Plan 页重新生成、Mistakes 删除、FocusMode 中止等操作使用原生 `confirm()`，体验粗糙
- ~~Login 页演示账号明文~~：已改为服务端 `DEMO_HINT` 下发，商用构建不再包含任何口令
- **无全局错误边界**：`app.config.errorHandler` 未设置，未捕获的 Promise rejection 不会展示给用户
- **CSS 重复媒体查询**：`@media (max-width: 980px)` 出现了至少 5 次，应合并
