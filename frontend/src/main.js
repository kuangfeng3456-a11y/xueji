import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { notify } from './store'
import { cancelPendingRequests } from './api'
import './style.css'
// 纸感编辑风主题（theme.css）已停用，改用 style.css 的现代 SaaS 风格体系；
// 保留 theme.css 仅作历史参考，不再参与构建。

const app = createApp(App)

/**
 * 全局错误边界。
 *
 * 页面各自 catch 的错误走自己的提示；这里兜住「谁都没接住」的那部分：
 * 组件渲染/生命周期异常、事件处理器抛错、未处理的 Promise rejection。
 * 不把技术堆栈弹给用户，控制台保留完整信息，界面只给一句可理解的提示。
 */
function reportFatal(error, source) {
  const message = String(error?.message || error || '未知错误')
  // 已由业务层提示过的错误不重复弹
  if (/登录状态已失效|请求已取消/.test(message)) return
  console.error(`[学迹] ${source}`, error)
  notify('页面遇到问题，已记录。可刷新重试；若持续出现请联系支持。', true)
}

app.config.errorHandler = (error, _instance, info) => {
  reportFatal(error, `组件异常（${info}）`)
}

window.addEventListener('unhandledrejection', (event) => {
  reportFatal(event.reason, '未处理的异步错误')
})

// 退出登录时取消在途请求，避免上一个账号的数据回写到新会话
window.addEventListener('xueji:logout', () => cancelPendingRequests())

app.use(router)
app.mount('#app')
