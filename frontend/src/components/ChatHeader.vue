<script setup>
import { ref } from 'vue'

const props = defineProps({
  sessionId: { type: String, default: '' },
  sidebarOpen: { type: Boolean, default: false },
})

const emit = defineEmits(['new-session', 'toggle-sidebar'])

const copied = ref(false)

/** 截断显示 session ID 前 8 位 */
function shortId(id) {
  return id ? id.slice(0, 8) : ''
}

/** 复制 session ID 到剪贴板 */
async function copySessionId() {
  if (!props.sessionId) return
  try {
    await navigator.clipboard.writeText(props.sessionId)
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  } catch {
    // fallback
    const textarea = document.createElement('textarea')
    textarea.value = props.sessionId
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  }
}
</script>

<template>
  <header class="chat-header">
    <div class="header-left">
      <!-- 汉堡按钮：切换历史栏 -->
      <button
        class="hamburger-btn"
        :title="sidebarOpen ? '收起历史栏' : '展开历史栏'"
        @click="emit('toggle-sidebar')"
      >
        <span class="hamburger-line"></span>
        <span class="hamburger-line"></span>
        <span class="hamburger-line"></span>
      </button>
      <h1 class="header-title">文档 AI 助手</h1>
      <span class="header-subtitle">基于芋道官方文档</span>
    </div>
    <div class="header-right">
      <div class="session-info">
        <span class="session-label">Session</span>
        <code class="session-id">{{ shortId(sessionId) || '—' }}</code>
      </div>
      <button
        class="icon-btn"
        :title="copied ? '已复制' : '复制 Session ID'"
        @click="copySessionId"
        :disabled="!sessionId"
      >
        {{ copied ? '✓' : '⎘' }}
      </button>
      <button
        class="icon-btn new-session-btn"
        title="新对话"
        @click="emit('new-session')"
      >
        ✧
      </button>
    </div>
  </header>
</template>

<style scoped>
.chat-header {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--spacing-lg);
  border-bottom: 1px solid var(--border);
  background: var(--bg-primary);
  flex-shrink: 0;
  gap: var(--spacing-md);
}

.header-left {
  display: flex;
  align-items: baseline;
  gap: var(--spacing-sm);
  flex-shrink: 0;
}

/* 汉堡按钮 */
.hamburger-btn {
  width: 32px;
  height: 32px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 6px;
  transition: background 0.15s ease;
  margin-right: var(--spacing-xs);
  /* 对齐标题文字 */;
}

.hamburger-btn:hover {
  background: var(--bg-secondary);
}

.hamburger-line {
  display: block;
  width: 18px;
  height: 2px;
  background: var(--text-secondary);
  border-radius: 1px;
  transition: all 0.2s ease;
}

.hamburger-btn:hover .hamburger-line {
  background: var(--text-primary);
}

.header-title {
  font-size: 17px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-subtitle {
  font-size: 12px;
  color: var(--text-secondary);
}

.header-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.session-info {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.session-label {
  opacity: 0.6;
}

.session-id {
  font-size: 11px;
  background: var(--bg-secondary);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
}

.icon-btn {
  width: 32px;
  height: 32px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  transition: all 0.2s ease;
}

.icon-btn:hover:not(:disabled) {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.icon-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.new-session-btn:hover:not(:disabled) {
  background: var(--bg-dark);
  color: var(--text-light);
}
</style>
