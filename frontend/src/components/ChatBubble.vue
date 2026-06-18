<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { marked } from 'marked'
import AgentSteps from './AgentSteps.vue'

const props = defineProps({
  message: { type: Object, required: true },
})

const role = computed(() => props.message.role)

/** 思考面板是否已手工折叠过 */
const thinkingManuallyCollapsed = ref(false)

/** 是否显示思考面板 — done 后自动折叠（除非用户已手工展开） */
const showThinking = computed(() => {
  if (!props.message.thinking?.length) return false
  if (thinkingManuallyCollapsed.value) return false
  // 流式传输中默认展开，完成后默认折叠
  if (!props.message.isStreaming) {
    // 已完成 → 自动折叠
    return false
  }
  return true
})

/** 当消息完成流式时，reset 手动折叠标记 */
watch(
  () => props.message.isStreaming,
  (streaming) => {
    if (!streaming) {
      // 完成时保持折叠状态，不做特殊处理
    } else {
      // 新流开始时，自动展开
      thinkingManuallyCollapsed.value = false
    }
  },
)

/** 渲染 Markdown 内容 */
function renderMarkdown(text) {
  if (!text) return ''
  return marked.parse(text, { breaks: true, gfm: true })
}

/** 格式化时间戳 */
function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

/** 手动切换思考面板 */
function toggleThinking() {
  thinkingManuallyCollapsed.value = !thinkingManuallyCollapsed.value
}

/** 手动标记已完成展开 */
function expandCompleted() {
  thinkingManuallyCollapsed.value = false
}
</script>

<template>
  <div class="chat-bubble" :class="'bubble-' + role">
    <!-- =========================== -->
    <!-- 用户消息 -->
    <!-- =========================== -->
    <template v-if="role === 'user'">
      <div class="user-bubble">
        <div class="user-content">{{ message.content }}</div>
        <div class="user-time">{{ formatTime(message.timestamp) }}</div>
      </div>
    </template>

    <!-- =========================== -->
    <!-- 助手消息 -->
    <!-- =========================== -->
    <template v-else>
      <div class="assistant-bubble">
        <!-- A. 思考过程区（有步骤且可见时） -->
        <template v-if="message.thinking?.length">
          <!-- 完成后显示可展开标题 -->
          <div
            v-if="!message.isStreaming && thinkingManuallyCollapsed"
            class="completed-thinking-toggle"
            @click="expandCompleted"
          >
            ▸ 🧠 查看 Agent 思考过程（{{ message.thinking.length }} 步）
          </div>
        </template>

        <AgentSteps
          :steps="message.thinking"
          :visible="showThinking"
        />

        <!-- B. 回答内容区 -->
        <div class="assistant-content">
          <div
            v-if="message.content"
            class="markdown-body"
            v-html="renderMarkdown(message.content)"
          ></div>

          <!-- 流式光标 -->
          <span
            v-if="message.isStreaming"
            class="streaming-cursor"
          >▊</span>

          <!-- 空状态（流式中还没有内容） -->
          <div
            v-if="!message.content && !message.isStreaming && !message.error"
            class="empty-content"
          >
            <em>无回答内容</em>
          </div>
        </div>

        <!-- 错误提示 -->
        <div v-if="message.error" class="error-block">
          ❌ {{ message.error }}
        </div>

        <!-- C. 底部来源区 -->
        <div v-if="message.sources?.length" class="sources-bar">
          <span class="sources-label">📎 参考来源</span>
          <span
            v-for="(source, idx) in message.sources"
            :key="idx"
            class="source-tag"
          >{{ source }}</span>
        </div>

        <!-- 时间戳 -->
        <div class="assistant-time">{{ formatTime(message.timestamp) }}</div>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* =========================================
 * 通用
 * ========================================= */
.chat-bubble {
  margin-bottom: var(--spacing-md);
  max-width: 100%;
}

/* =========================================
 * 用户消息 — 右对齐，深色气泡
 * ========================================= */
.bubble-user {
  display: flex;
  justify-content: flex-end;
}

.user-bubble {
  max-width: 70%;
  background: var(--bg-dark);
  color: var(--text-light);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  border-bottom-right-radius: var(--radius-sm);
}

.user-content {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
}

.user-time {
  font-size: 11px;
  opacity: 0.6;
  text-align: right;
  margin-top: 4px;
}

/* =========================================
 * 助手消息 — 左对齐，白色卡片
 * ========================================= */
.bubble-assistant {
  display: flex;
  justify-content: flex-start;
}

.assistant-bubble {
  max-width: 85%;
  width: 100%;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  border-bottom-left-radius: var(--radius-sm);
  padding: var(--spacing-md);
}

/* 完成后的思考展开按钮 */
.completed-thinking-toggle {
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-sm);
  transition: background 0.15s ease;
  user-select: none;
}

.completed-thinking-toggle:hover {
  background: var(--bg-secondary);
}

/* =========================================
 * 助手消息 — 回答内容
 * ========================================= */
.assistant-content {
  position: relative;
  min-height: 1em;
}

/* ---- Markdown 渲染 ---- */
.markdown-body {
  line-height: 1.7;
  color: var(--text-primary);
  word-break: break-word;
}

/* Markdown 元素通用样式 */
.markdown-body :deep(p) {
  margin-bottom: 0.8em;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(a) {
  color: var(--text-primary);
  text-decoration: underline;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  margin-top: 1.2em;
  margin-bottom: 0.6em;
  font-weight: 600;
  line-height: 1.3;
}

.markdown-body :deep(h1) { font-size: 1.3em; }
.markdown-body :deep(h2) { font-size: 1.15em; }
.markdown-body :deep(h3) { font-size: 1.05em; }

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 1.5em;
  margin-bottom: 0.8em;
}

.markdown-body :deep(li) {
  margin-bottom: 0.3em;
}

.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--border);
  padding-left: var(--spacing-md);
  color: var(--text-secondary);
  margin: 0.8em 0;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.8em 0;
  font-size: 13px;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--border);
  padding: 6px var(--spacing-sm);
  text-align: left;
}

.markdown-body :deep(th) {
  background: var(--bg-secondary);
  font-weight: 600;
}

.markdown-body :deep(code) {
  font-family: 'Fira Code', 'Cascadia Code', 'Consolas', 'Menlo', monospace;
  font-size: 0.9em;
  background: var(--bg-secondary);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
}

.markdown-body :deep(pre) {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: var(--spacing-md);
  border-radius: var(--radius-sm);
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.5;
  margin: 0.8em 0;
}

.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
  font-size: inherit;
  color: inherit;
}

.markdown-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--border);
  margin: var(--spacing-md) 0;
}

.markdown-body :deep(strong) {
  font-weight: 600;
}

.markdown-body :deep(img) {
  max-width: 100%;
  border-radius: var(--radius-sm);
}

/* 引用标注颜色 — 来源文档 */
.markdown-body :deep(.source-tag) {
  color: var(--success);
  font-size: 0.85em;
}

/* 引用标注 — 推断 */
.markdown-body :deep(.inferred-tag) {
  color: var(--text-secondary);
  font-size: 0.85em;
}

/* ---- 流式光标 ---- */
.streaming-cursor {
  display: inline;
  color: var(--text-primary);
  font-size: 16px;
  animation: blink 1s step-end infinite;
  margin-left: 1px;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* ---- 空内容 ---- */
.empty-content {
  color: var(--text-secondary);
  font-style: italic;
  font-size: 13px;
}

/* ---- 错误 ---- */
.error-block {
  margin-top: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: var(--radius-sm);
  color: var(--error);
  font-size: 13px;
}

/* =========================================
 * 来源标签
 * ========================================= */
.sources-bar {
  margin-top: var(--spacing-md);
  padding-top: var(--spacing-sm);
  border-top: 1px solid var(--border-light);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.sources-label {
  font-size: 11px;
  color: var(--text-secondary);
  margin-right: 2px;
}

.source-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  color: var(--success);
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  padding: 2px 8px;
  border-radius: 12px;
  font-family: 'Fira Code', 'Consolas', monospace;
}

.assistant-time {
  font-size: 11px;
  color: var(--text-secondary);
  opacity: 0.6;
  margin-top: var(--spacing-xs);
}
</style>
