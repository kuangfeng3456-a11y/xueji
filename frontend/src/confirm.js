import { reactive } from 'vue'

/**
 * 全局确认弹窗。
 *
 * 替代原生 confirm()：原生弹窗会阻塞主线程、样式不受控、移动端体验差，
 * 而且无法表达「危险操作」。这里用 Promise 化调用，写法与 await 一致：
 *
 *   if (!(await confirmAction({ title: '删除班级', message: '...', danger: true }))) return
 */
export const confirmState = reactive({
  open: false,
  title: '',
  message: '',
  detail: '',
  confirmText: '确定',
  cancelText: '取消',
  danger: false
})

let resolver = null

export function confirmAction(options = {}) {
  const {
    title = '请确认',
    message = '',
    detail = '',
    confirmText = '确定',
    cancelText = '取消',
    danger = false
  } = typeof options === 'string' ? { message: options } : options

  // 上一个还没答复就被新请求覆盖时，按「取消」结算，避免 Promise 永久挂起
  if (resolver) {
    resolver(false)
    resolver = null
  }

  Object.assign(confirmState, {
    open: true,
    title,
    message,
    detail,
    confirmText,
    cancelText,
    danger
  })

  return new Promise((resolve) => {
    resolver = resolve
  })
}

export function settleConfirm(value) {
  confirmState.open = false
  const done = resolver
  resolver = null
  if (done) done(Boolean(value))
}
