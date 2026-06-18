/**
 * SSE 流解析工具 — 连接后端 POST /chat 接口，逐行解析 Server-Sent Events
 *
 * 注意点：
 * - answer 事件的 data 是**纯文本**，不用 JSON.parse
 * - 其他事件 data 是 JSON 字符串
 * - buffer 机制处理 TCP 流跨 chunk 的不完整行
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

/**
 * 分发 SSE 事件到对应回调
 */
function dispatchEvent(type, data, callbacks) {
  switch (type) {
    case 'thinking':
      callbacks.onThinking?.(data)
      break
    case 'memory':
      callbacks.onMemory?.(safeJsonParse(data))
      break
    case 'cache_hit':
      callbacks.onCacheHit?.(data)
      break
    case 'tool_call':
      callbacks.onToolCall?.(safeJsonParse(data))
      break
    case 'tool_result':
      callbacks.onToolResult?.(safeJsonParse(data))
      break
    case 'tool_end':
      callbacks.onToolEnd?.(safeJsonParse(data))
      break
    case 'compressed':
      callbacks.onCompressed?.(safeJsonParse(data))
      break
    case 'answer':
      // answer 的 data 是纯文本，不用 JSON.parse
      callbacks.onAnswer?.(data)
      break
    case 'sources':
      callbacks.onSources?.(safeJsonParse(data))
      break
    case 'done':
      callbacks.onDone?.()
      break
    case 'error':
      callbacks.onError?.(safeJsonParse(data)?.message || data)
      break
    default:
      // 忽略未知事件类型
      break
  }
}

/**
 * 安全 JSON.parse，解析失败返回原始值
 */
function safeJsonParse(data) {
  try {
    return JSON.parse(data)
  } catch {
    return data
  }
}

/**
 * 发送消息并建立 SSE 连接
 *
 * @param {string} question - 用户问题
 * @param {string} sessionId - 会话 ID
 * @param {object} callbacks - 事件回调
 * @param {function} callbacks.onThinking
 * @param {function} callbacks.onMemory
 * @param {function} callbacks.onCacheHit
 * @param {function} callbacks.onToolCall
 * @param {function} callbacks.onToolResult
 * @param {function} callbacks.onToolEnd
 * @param {function} callbacks.onCompressed
 * @param {function} callbacks.onAnswer
 * @param {function} callbacks.onSources
 * @param {function} callbacks.onDone
 * @param {function} callbacks.onError
 * @returns {Promise<AbortController>} 用于取消请求
 */
export async function connectSSE(question, sessionId, callbacks) {
  const controller = new AbortController()

  try {
    // [DEBUG] — 删了就不知道卡在哪一步
    console.log('[SSE] 发送请求... question:', question.slice(0, 30), '| session:', sessionId?.slice(0, 8))

    const response = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, session_id: sessionId }),
      signal: controller.signal,
    })

    console.log('[SSE] 响应到达, status:', response.status)

    if (!response.ok) {
      const errorBody = await response.text().catch(() => '')
      throw new Error(`HTTP ${response.status}: ${response.statusText}${errorBody ? ' — ' + errorBody : ''}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let eventCount = 0

    console.log('[SSE] 开始读流...')

    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        console.log('[SSE] 流结束, 共收到事件:', eventCount)
        break
      }

      buffer += decoder.decode(value, { stream: true })

      const parts = buffer.split('\n\n')
      buffer = parts.pop()

      for (const part of parts) {
        if (!part.trim()) continue

        const lines = part.split('\n')
        let eventType = ''
        let data = ''

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            data = line.slice(6)
          }
        }

        if (eventType && data !== '') {
          eventCount++
          if (eventCount <= 3 || eventType === 'done' || eventType === 'error') {
            console.log('[SSE] 事件 #' + eventCount + ':', eventType, '| len:', data.length)
          }
          dispatchEvent(eventType, data, callbacks)
        }
      }
    }
  } catch (err) {
    console.error('[SSE] 异常:', err.name, err.message)
    if (err.name === 'AbortError') return controller
    if (callbacks.onError) {
      callbacks.onError(err.message)
    }
  }

  return controller
}
