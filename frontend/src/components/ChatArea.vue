<script setup>
import { ref, watch, nextTick, onMounted } from 'vue'
import ChatBubble from './ChatBubble.vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
})

const chatListEl = ref(null)

/** 滚动到底部 */
function scrollToBottom(smooth = true) {
  nextTick(() => {
    const el = chatListEl.value
    if (el) {
      el.scrollTo({
        top: el.scrollHeight,
        behavior: smooth ? 'smooth' : 'instant',
      })
    }
  })
}

/** 监听消息变化，自动滚动 */
watch(
  () => props.messages.length,
  () => scrollToBottom(true),
)

/** 监听流式内容变化（频繁触发），用平滑滚动 */
watch(
  () => {
    // 取最后一条消息的 content 长度和 thinking 步数，触发流式更新滚动
    const last = props.messages[props.messages.length - 1]
    if (!last) return ''
    return last.content + (last.thinking?.length || 0)
  },
  () => scrollToBottom(true),
)

onMounted(() => scrollToBottom(false))
</script>

<template>
  <div ref="chatListEl" class="chat-area">
    <!-- 空状态 -->
    <div v-if="messages.length === 0" class="empty-state">
      <div class="empty-icon">💬</div>
      <h2 class="empty-title">向你的技术文档 AI 助手提问</h2>
      <p class="empty-hint">例如：Redis 缓存怎么配置？</p>
    </div>

    <!-- 消息列表 -->
    <div v-else class="message-list">
      <ChatBubble
        v-for="msg in messages"
        :key="msg.id"
        :message="msg"
      />
    </div>
  </div>
</template>

<style scoped>
.chat-area {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-lg);
  scroll-behavior: smooth;
}

/* =========================================
 * 空状态
 * ========================================= */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-secondary);
  user-select: none;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: var(--spacing-md);
  opacity: 0.5;
}

.empty-title {
  font-size: 18px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: var(--spacing-sm);
}

.empty-hint {
  font-size: 14px;
  opacity: 0.6;
}

/* =========================================
 * 消息列表
 * ========================================= */
.message-list {
  max-width: 800px;
  margin: 0 auto;
}
</style>
