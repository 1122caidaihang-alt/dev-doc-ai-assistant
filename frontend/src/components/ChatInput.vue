<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['send', 'stop'])

const inputText = ref('')
const textareaEl = ref(null)

const canSend = computed(() => inputText.value.trim().length > 0 && !props.disabled)

/** 自动调整 textarea 高度，最大 4 行 */
function autoResize() {
  const el = textareaEl.value
  if (!el) return
  el.style.height = 'auto'
  const lineHeight = 22
  const maxHeight = lineHeight * 4 + 16 // 4 行 + padding
  el.style.height = Math.min(el.scrollHeight, maxHeight) + 'px'
}

/** 发送消息 */
function handleSend() {
  const text = inputText.value.trim()
  if (!text || props.disabled) return

  emit('send', text)
  inputText.value = ''

  // 重置 textarea 高度
  setTimeout(() => {
    if (textareaEl.value) {
      textareaEl.value.style.height = 'auto'
    }
  }, 0)
}

/** 键盘事件：Enter 发送，Shift+Enter 换行 */
function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

// 监听输入文本变化以调整高度
watch(inputText, autoResize)
</script>

<template>
  <div class="chat-input">
    <div class="input-wrapper">
      <textarea
        ref="textareaEl"
        v-model="inputText"
        class="input-textarea"
        :disabled="disabled"
        placeholder="输入你的技术问题..."
        rows="1"
        @keydown="handleKeydown"
      ></textarea>
      <!-- 中断按钮：只在 AI 回答期间显示 -->
      <button
        v-if="disabled"
        class="stop-btn"
        @click="$emit('stop')"
        title="中断回答"
      >
        <span class="stop-icon">■</span>
      </button>

      <button
        class="send-btn"
        :class="{ loading: disabled }"
        :disabled="!canSend"
        @click="handleSend"
        title="发送 (Enter)"
      >
        <span v-if="!disabled" class="send-icon">↑</span>
        <span v-else class="loading-spinner"></span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.chat-input {
  padding: var(--spacing-md) var(--spacing-lg);
  border-top: 1px solid var(--border);
  background: var(--bg-primary);
}

.input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: var(--spacing-sm);
  max-width: 800px;
  margin: 0 auto;
}

.input-textarea {
  flex: 1;
  border: none;
  border-bottom: 2px solid var(--border);
  outline: none;
  resize: none;
  padding: var(--spacing-sm) 0;
  font-family: inherit;
  font-size: 15px;
  line-height: 22px;
  color: var(--text-primary);
  background: transparent;
  min-height: 22px;
  max-height: calc(22px * 4 + 16px);
  transition: border-color 0.2s ease;
}

.input-textarea:focus {
  border-bottom-color: var(--text-primary);
}

.input-textarea:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.input-textarea::placeholder {
  color: var(--text-secondary);
  opacity: 0.7;
}

/* 中断按钮 */
.stop-btn {
  width: 36px;
  height: 36px;
  border: 2px solid var(--error);
  border-radius: 50%;
  background: transparent;
  color: var(--error);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.15s ease;
  margin-bottom: 2px;
}

.stop-btn:hover {
  background: var(--error);
  color: #fff;
}

.stop-icon {
  font-size: 14px;
  line-height: 1;
}

.send-btn {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: var(--bg-dark);
  color: var(--text-light);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s ease;
  margin-bottom: 2px;
}

.send-btn:hover:not(:disabled) {
  background: #333;
}

.send-btn:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.send-icon {
  font-size: 18px;
  line-height: 1;
}

/* loading 旋转动画 */
.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid transparent;
  border-top-color: var(--text-light);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
