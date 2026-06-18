<script setup>
import { useChatStore } from './stores/chat.js'
import ChatHeader from './components/ChatHeader.vue'
import ChatArea from './components/ChatArea.vue'
import ChatInput from './components/ChatInput.vue'
import HistorySidebar from './components/HistorySidebar.vue'

const chatStore = useChatStore()
</script>

<template>
  <div class="app-layout">
    <!-- 可展开历史对话栏 -->
    <HistorySidebar />

    <!-- 主内容区 -->
    <div class="app-main">
      <ChatHeader
        :session-id="chatStore.sessionId"
        :sidebar-open="chatStore.isSidebarOpen"
        @new-session="chatStore.clearMessages()"
        @toggle-sidebar="chatStore.toggleSidebar()"
      />
      <ChatArea :messages="chatStore.messages" />
      <ChatInput
        :disabled="chatStore.isLoading"
        @send="chatStore.sendMessage"
        @stop="chatStore.abortMessage()"
      />
    </div>
  </div>
</template>

<style scoped>
.app-layout {
  height: 100vh;
  display: flex;
  background: var(--bg-primary);
  overflow: hidden;
}

.app-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;  /* 防止 flex 子元素溢出 */
}
</style>
