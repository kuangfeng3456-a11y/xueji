/**
 * 轻量 SSE 客户端：POST + 流式读取，按 event 分发。
 * 用法：await streamSse('/api/goals/1/coach/stream', null, { onResult, onFallback, onStage })
 */
import { apiFetch } from './api'

export async function streamSse(path, body, handlers = {}) {
  const headers = { Accept: 'text/event-stream' }
  if (body) headers['Content-Type'] = 'application/json'
  const resp = await apiFetch(path, {
    method: body ? 'POST' : 'GET',
    headers,
    body: body ? JSON.stringify(body) : undefined
  })
  if (!resp.ok || !resp.body) {
    let message = `流式接口返回 ${resp.status}`
    try {
      const data = await resp.json()
      if (typeof data.detail === 'string') message = data.detail
    } catch (e) {
      /* ignore non-JSON error bodies */
    }
    throw new Error(message)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let final = null

  function dispatch(block) {
    const lines = block.split(/\r?\n/)
    const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim()
    const dataLines = lines
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).replace(/^ /, ''))
    if (!event || !dataLines.length) return
    let data
    try {
      data = JSON.parse(dataLines.join('\n'))
    } catch (e) {
      return
    }
    if (event === 'stage' && handlers.onStage) handlers.onStage(data)
    if (event === 'delta' && handlers.onDelta) handlers.onDelta(data)
    if (event === 'result') {
      final = data
      if (handlers.onResult) handlers.onResult(data)
    }
    if (event === 'fallback') {
      final = { fallback: true, ...data }
      if (handlers.onFallback) handlers.onFallback(data)
    }
    if (event === 'error' && handlers.onError) handlers.onError(data)
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split(/\r?\n\r?\n/)
    buffer = parts.pop()
    for (const part of parts) dispatch(part)
  }
  buffer += decoder.decode()
  if (buffer.trim()) dispatch(buffer)
  return final
}
