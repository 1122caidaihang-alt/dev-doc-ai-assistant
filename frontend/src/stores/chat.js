import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { connectSSE } from '../utils/sse.js'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

/**
 * Chat Store — 管理对话会话、消息列表和 SSE 流状态
 *
 * 核心数据结构：
 *   messages: [{ id, role, content, timestamp, thinking[], sources[], isStreaming, error }]
 *   sessionId: localStorage 持久化
 *   sessions: 历史会话列表 [{ session_id, title, message_count, last_updated }]
 */
export const useChatStore = defineStore('chat', () => {
  // ========================
  // 会话状态
  // ========================
  const sessionId = ref(loadSession())
  const sessionName = ref('')

  // ========================
  // 消息列表 & 历史会话列表
  // ========================
  const messages = ref([])
  const sessions = ref([])           // 历史会话列表

  // ========================
  // UI 状态
  // ========================
  const isLoading = ref(false)
  const isStreaming = ref(false)
  const isSidebarOpen = ref(false)    // 历史栏展开/收起

  // 当前 AbortController（用于中断对话）
  let currentController = null

  // 当前正在流式接收的消息索引（方便组件直接引用）
  const streamingMessage = computed(() => {
    return messages.value.find(m => m.isStreaming) || null
  })

  // ========================
  // 工具函数
  // ========================

  /** 生成随机 session_id（UUID v4） */
  function generateSessionId() {
    if (crypto?.randomUUID) {
      return crypto.randomUUID()
    }
    // fallback: 手动 uuid v4
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0
      const v = c === 'x' ? r : (r & 0x3) | 0x8
      return v.toString(16)
    })
  }

  /** 从 localStorage 恢复 sessionId */
  function loadSession() {
    try {
      return localStorage.getItem('chat_session_id') || ''
    } catch {
      return ''
    }
  }

  /** 持久化 sessionId 到 localStorage */
  function saveSession() {
    try {
      localStorage.setItem('chat_session_id', sessionId.value)
    } catch {
      // localStorage 不可用时静默失败
    }
  }

  /** 生成消息 ID */
  function generateMsgId() {
    return 'msg-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8)
  }

  // ========================
  // Actions
  // ========================

  /**
   * 发送消息 — 核心函数
   * 1. 确保 sessionId 存在
   * 2. 追加 user 消息
   * 3. 创建空的 assistant 消息（isStreaming=true）
   * 4. 建立 SSE 连接，逐事件更新 assistant 消息
   */
  async function sendMessage(question) {
    const trimmed = question.trim()
    if (!trimmed || isLoading.value) return

    console.log('[chat] sendMessage 开始:', trimmed.slice(0, 30))

    // 1. 确保 sessionId
    if (!sessionId.value) {
      sessionId.value = generateSessionId()
      saveSession()
    }

    // 自动设置 session 名称为第一个问题
    if (!sessionName.value) {
      sessionName.value = trimmed.length > 30 ? trimmed.slice(0, 30) + '...' : trimmed
    }

    // 2. 创建并追加 user 消息
    const userMsg = {
      id: generateMsgId(),
      role: 'user',
      content: trimmed,
      timestamp: Date.now(),
    }
    messages.value.push(userMsg)

    // 3. 创建空的 assistant 消息，push 后从 reactive 数组取引用
    //    关键：不能用 push 前的原始对象！Vue3 的 reactive() 会包一层 Proxy，
    //    只有通过 messages.value[i] 拿到的才是 Proxy，才能触发 UI 更新。
    messages.value.push({
      id: generateMsgId(),
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      thinking: [],
      sources: [],
      isStreaming: true,
      error: null,
    })
    const assistantIndex = messages.value.length - 1  // 从 reactive 数组取索引

    // 设置 loading 状态
    isLoading.value = true
    isStreaming.value = true

    // 4. 建立 SSE 连接
    const controller = await connectSSE(trimmed, sessionId.value, {
      onThinking(text) {
        messages.value[assistantIndex].thinking.push({ type: 'thinking', text, timestamp: Date.now() })
      },

      onMemory(data) {
        const text = `已加载 ${data.message_count} 条历史消息（${data.token_usage ?? 0}% token）`
        messages.value[assistantIndex].thinking.push({
          type: 'memory',
          text,
          extra: data,
          timestamp: Date.now(),
        })
      },

      onCacheHit(data) {
        messages.value[assistantIndex].thinking.push({
          type: 'cache_hit',
          text: typeof data === 'string' ? data : '缓存命中，跳过检索直接返回',
          timestamp: Date.now(),
        })
      },

      onToolCall(data) {
        messages.value[assistantIndex].thinking.push({
          type: 'tool_call',
          tool: data.tool,
          input: data.input,
          text: `调用 ${data.tool}`,
          timestamp: Date.now(),
        })
      },

      onToolResult(data) {
        const content = typeof data.content === 'string' ? data.content : JSON.stringify(data)
        const truncated = content.length > 300 ? content.slice(0, 300) + '...' : content
        messages.value[assistantIndex].thinking.push({
          type: 'tool_result',
          text: truncated,
          fullText: content,
          timestamp: Date.now(),
        })
      },

      onToolEnd(data) {
        const count = data.result_count || 0
        const sources = data.sources || []
        messages.value[assistantIndex].thinking.push({
          type: 'tool_end',
          text: `检索到 ${count} 篇相关文档`,
          sources,
          count,
          timestamp: Date.now(),
        })
        if (sources.length > 0) {
          const msg = messages.value[assistantIndex]
          msg.sources = [...new Set([...msg.sources, ...sources])]
        }
      },

      onCompressed(data) {
        const text = `已压缩 ${data.compressed_count} 条历史消息为 ${data.summary_length} 字摘要`
        messages.value[assistantIndex].thinking.push({
          type: 'compressed',
          text,
          extra: data,
          timestamp: Date.now(),
        })
      },

      onAnswer(token) {
        messages.value[assistantIndex].content += token
      },

      onSources(sources) {
        if (Array.isArray(sources) && sources.length > 0) {
          const msg = messages.value[assistantIndex]
          msg.sources = [...new Set([...msg.sources, ...sources])]
        }
      },

      onDone() {
        console.log('[chat] onDone, content:', messages.value[assistantIndex].content.length, '字')
        const msg = messages.value[assistantIndex]
        msg.isStreaming = false
        isLoading.value = false
        isStreaming.value = false
      },

      onError(errorMsg) {
        console.error('[chat] onError:', errorMsg)
        messages.value[assistantIndex].error = errorMsg
        messages.value[assistantIndex].isStreaming = false
        isLoading.value = false
        isStreaming.value = false
      },
    })

    // 保存 controller 引用以便取消
    currentController = controller
    messages.value[assistantIndex]._controller = controller
  }

  /** 清空消息并重置会话 */
  function clearMessages() {
    messages.value = []
    sessionId.value = generateSessionId()
    saveSession()
    sessionName.value = ''
    sessions.value = []  // 清空历史列表缓存，下次打开重新加载
  }

  /** 从 localStorage 恢复会话 */
  function restoreSession() {
    sessionId.value = loadSession()
  }

  // ========================
  // 中断对话
  // ========================

  /** 中断当前正在生成的 AI 回答 */
  function abortMessage() {
    if (currentController) {
      currentController.abort()
      currentController = null
    }
    // 把 stream 状态收尾
    const streaming = messages.value.find(m => m.isStreaming)
    if (streaming) {
      streaming.isStreaming = false
      if (!streaming.content) {
        streaming.content = '(已中断)'
      }
    }
    isLoading.value = false
    isStreaming.value = false
  }

  // ========================
  // 历史会话列表
  // ========================

  /** 从后端加载历史会话列表 */
  async function loadSessions() {
    try {
      const res = await fetch(`${API_BASE}/sessions`)
      if (res.ok) {
        sessions.value = await res.json()
      }
    } catch (e) {
      console.error('[chat] 加载历史会话失败:', e.message)
    }
  }

  /** 切换到指定历史会话 */
  async function switchSession(id) {
    if (isLoading.value) return  // 正在回答中不能切换

    // 1. 切 sessionId
    sessionId.value = id
    saveSession()

    // 2. 从后端加载该 session 的消息
    try {
      const res = await fetch(`${API_BASE}/sessions/${id}`)
      if (res.ok) {
        const data = await res.json()
        // 把后端消息转成前端消息格式
        messages.value = (data.messages || []).map(msg => ({
          id: generateMsgId(),
          role: msg.role,
          content: msg.content,
          timestamp: Date.now(),
          thinking: [],
          sources: [],
          isStreaming: false,
          error: null,
        }))
        // 更新 session 标题
        const firstUser = messages.value.find(m => m.role === 'user')
        sessionName.value = firstUser
          ? (firstUser.content.length > 30 ? firstUser.content.slice(0, 30) + '...' : firstUser.content)
          : ''
      }
    } catch (e) {
      console.error('[chat] 加载会话消息失败:', e.message)
    }
  }

  /** 删除指定历史会话 */
  async function deleteSession(id) {
    try {
      const res = await fetch(`${API_BASE}/sessions/${id}`, { method: 'DELETE' })
      if (res.ok) {
        // 从列表中移除
        sessions.value = sessions.value.filter(s => s.session_id !== id)
        // 如果删的是当前会话 → 清空消息开始新会话
        if (id === sessionId.value) {
          messages.value = []
          sessionId.value = generateSessionId()
          saveSession()
          sessionName.value = ''
        }
      }
    } catch (e) {
      console.error('[chat] 删除会话失败:', e.message)
    }
  }

  /** 切换侧栏展开/收起 */
  function toggleSidebar() {
    isSidebarOpen.value = !isSidebarOpen.value
  }

  return {
    // 状态
    sessionId,
    sessionName,
    messages,
    sessions,
    isLoading,
    isStreaming,
    isSidebarOpen,
    streamingMessage,
    // 动作
    sendMessage,
    clearMessages,
    restoreSession,
    abortMessage,
    loadSessions,
    switchSession,
    deleteSession,
    toggleSidebar,
  }
})
