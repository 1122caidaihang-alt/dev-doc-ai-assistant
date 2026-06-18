<script setup>
/**
 * HistorySidebar — 可展开/收起的对话历史栏
 *
 * 功能：
 *  - 点击左上角汉堡按钮或遮罩层切换展开/收起
 *  - 展开后显示所有历史会话列表
 *  - 点击某个历史会话 → 切换并加载该会话的消息
 *  - 新建对话按钮 → 清空消息开始新会话
 *  - 当前活跃 session 高亮显示
 */
import { onMounted } from 'vue'
import { useChatStore } from '../stores/chat.js'

const store = useChatStore()

// 组件挂载时自动加载会话列表
onMounted(() => {
  store.loadSessions()
})

/** 格式化时间为简短显示 */
function formatTime(isoStr) {
  if (!isoStr) return ''
  try {
    const date = new Date(isoStr)
    const now = new Date()
    const diffMs = now - date
    const diffMin = Math.floor(diffMs / 60000)
    const diffHour = Math.floor(diffMs / 3600000)
    const diffDay = Math.floor(diffMs / 86400000)

    if (diffMin < 1) return '刚才'
    if (diffMin < 60) return `${diffMin} 分钟前`
    if (diffHour < 24) return `${diffHour} 小时前`
    if (diffDay < 7) return `${diffDay} 天前`
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  } catch {
    return ''
  }
}

/** 点击切换会话 */
function handleSelect(id) {
  if (id === store.sessionId) return  // 已经是当前会话
  store.switchSession(id)
  store.isSidebarOpen = false  // 移动端自动收起
}

/** 新建对话 */
function handleNew() {
  store.clearMessages()
  store.isSidebarOpen = false
}

/** 删除历史会话（阻止冒泡防止触发切换） */
function handleDelete(e, id) {
  e.stopPropagation()
  if (confirm('确定删除这个对话吗？')) {
    store.deleteSession(id)
  }
}
</script>

<template>
  <!-- 遮罩层：移动端点击遮罩关闭侧栏 -->
  <div
    v-if="store.isSidebarOpen"
    class="sidebar-overlay"
    @click="store.isSidebarOpen = false"
  ></div>

  <!-- 侧栏主体 -->
  <aside class="history-sidebar" :class="{ open: store.isSidebarOpen }">
    <div class="sidebar-header">
      <h3 class="sidebar-title">历史对话</h3>
      <button
        class="sidebar-close-btn"
        @click="store.isSidebarOpen = false"
        title="收起侧栏"
      >
        ✕
      </button>
    </div>

    <!-- 新建对话按钮 -->
    <button class="new-chat-btn" @click="handleNew">
      <span class="new-chat-icon">+</span>
      新建对话
    </button>

    <!-- 会话列表 -->
    <div class="session-list">
      <div v-if="store.sessions.length === 0" class="no-history">
        暂无历史对话
      </div>

      <button
        v-for="s in store.sessions"
        :key="s.session_id"
        class="session-item"
        :class="{ active: s.session_id === store.sessionId }"
        @click="handleSelect(s.session_id)"
      >
        <div class="session-item-icon">💬</div>
        <div class="session-item-content">
          <div class="session-item-title">{{ s.title }}</div>
          <div class="session-item-meta">
            {{ s.message_count }} 条消息 · {{ formatTime(s.last_updated) }}
          </div>
        </div>
        <!-- 删除按钮：hover 时显示 -->
        <button
          class="session-delete-btn"
          title="删除此对话"
          @click="(e) => handleDelete(e, s.session_id)"
        >
          ✕
        </button>
      </button>
    </div>
  </aside>
</template>

<style scoped>
/* =========================================
 * 遮罩层（移动端）
 * ========================================= */
.sidebar-overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  z-index: 9;
}

@media (max-width: 768px) {
  .sidebar-overlay {
    display: block;
  }
}

/* =========================================
 * 侧栏主体
 * ========================================= */
.history-sidebar {
  width: 280px;
  height: 100vh;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow: hidden;
  transition: width 0.25s ease, padding 0.25s ease, border 0.25s ease;
}

/* 收起状态：宽度缩为 0 */
.history-sidebar:not(.open) {
  width: 0;
  border-right: none;
  padding: 0;
}

/* =========================================
 * 侧栏头部
 * ========================================= */
.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.sidebar-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.sidebar-close-btn {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
}

.sidebar-close-btn:hover {
  background: var(--border);
  color: var(--text-primary);
}

/* =========================================
 * 新建对话按钮
 * ========================================= */
.new-chat-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: var(--spacing-sm) var(--spacing-md);
  padding: 8px 12px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-primary);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;
  flex-shrink: 0;
}

.new-chat-btn:hover {
  border-color: var(--text-primary);
  background: var(--bg-primary);
}

.new-chat-icon {
  font-size: 18px;
  font-weight: 300;
  line-height: 1;
}

/* =========================================
 * 会话列表
 * ========================================= */
.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 var(--spacing-sm);
}

.no-history {
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
  padding: var(--spacing-lg);
  opacity: 0.6;
}

/* =========================================
 * 会话项
 * ========================================= */
.session-item {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-sm);
  width: 100%;
  padding: 10px var(--spacing-sm);
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-primary);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  text-align: left;
  transition: background 0.1s ease;
  position: relative;  /* 给删除按钮定位 */
}

.session-item:hover {
  background: var(--bg-primary);
}

.session-item.active {
  background: var(--bg-primary);
  box-shadow: var(--shadow-sm);
}

.session-item-icon {
  font-size: 14px;
  flex-shrink: 0;
  margin-top: 1px;
  opacity: 0.6;
}

.session-item-content {
  overflow: hidden;
  min-width: 0;
}

.session-item-title {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.4;
}

.session-item-meta {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 2px;
}

/* 删除按钮：默认隐藏，hover 时显示 */
.session-delete-btn {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  width: 24px;
  height: 24px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.15s ease, background 0.15s ease, color 0.15s ease;
}

.session-item:hover .session-delete-btn {
  opacity: 1;
}

.session-delete-btn:hover {
  background: var(--error);
  color: #fff;
}

/* =========================================
 * 移动端：侧栏变为绝对定位浮层
 * ========================================= */
@media (max-width: 768px) {
  .history-sidebar {
    position: fixed;
    left: 0;
    top: 0;
    z-index: 10;
    box-shadow: var(--shadow-md);
  }

  .history-sidebar:not(.open) {
    width: 0;
    box-shadow: none;
  }
}
</style>
