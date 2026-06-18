<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  steps: { type: Array, default: () => [] },
  /** 控制是否可见（外部 done 事件后折叠） */
  visible: { type: Boolean, default: true },
})

const expanded = ref(true)

/** 步骤类型 → 图标和样式映射 */
function stepIcon(type) {
  const icons = {
    thinking: '💭',
    memory: '📚',
    cache_hit: '⚡',
    tool_call: '🔧',
    tool_result: '📄',
    tool_end: '✅',
    compressed: '🗜',
  }
  return icons[type] || '💭'
}

/** 格式化 tool_call 的输入参数 */
function formatInput(input) {
  if (!input) return ''
  if (typeof input === 'string') return input
  return JSON.stringify(input, null, 0)
}

/** 是否展开详细内容 */
const expandedResults = ref({})

function toggleResult(index) {
  expandedResults.value[index] = !expandedResults.value[index]
}
</script>

<template>
  <div v-if="steps.length > 0 && visible" class="agent-steps">
    <div class="steps-header" @click="expanded = !expanded">
      <span class="steps-header-icon">{{ expanded ? '▾' : '▸' }}</span>
      <span class="steps-header-text">🧠 Agent 思考过程</span>
      <span class="steps-badge">{{ steps.length }}</span>
    </div>
    <div v-show="expanded" class="steps-body">
      <div
        v-for="(step, index) in steps"
        :key="index"
        class="step-item"
        :class="'step-' + step.type"
      >
        <!-- thinking -->
        <div v-if="step.type === 'thinking'" class="step-line step-thinking">
          <span class="step-icon">💭</span>
          <span class="step-text">{{ step.text }}</span>
        </div>

        <!-- memory -->
        <div v-else-if="step.type === 'memory'" class="step-line step-memory">
          <span class="step-icon">📚</span>
          <span class="step-text">
            已加载 <strong>{{ step.extra?.message_count ?? 0 }}</strong> 条历史消息
            <template v-if="step.extra?.token_usage">
              （{{ step.extra.token_usage }}% token）
            </template>
          </span>
        </div>

        <!-- cache_hit -->
        <div v-else-if="step.type === 'cache_hit'" class="step-line step-cache">
          <span class="step-icon">⚡</span>
          <span class="step-text">{{ step.text }}</span>
        </div>

        <!-- tool_call -->
        <div v-else-if="step.type === 'tool_call'" class="step-line step-tool">
          <span class="step-icon">🔧</span>
          <code class="step-tool-name">{{ step.tool }}</code>
          <span v-if="step.input" class="step-tool-input">({{ formatInput(step.input) }})</span>
        </div>

        <!-- tool_result -->
        <div v-else-if="step.type === 'tool_result'" class="step-result">
          <span class="step-icon">📄</span>
          <div class="step-result-content">
            <span class="step-result-label">检索结果</span>
            <div class="step-result-text">
              <template v-if="expandedResults[index]">
                {{ step.fullText || step.text }}
              </template>
              <template v-else>
                {{ (step.text?.length > 150 ? step.text.slice(0, 150) + '...' : step.text) }}
              </template>
            </div>
            <button
              v-if="(step.text?.length || 0) > 150"
              class="step-result-toggle"
              @click.stop="toggleResult(index)"
            >
              {{ expandedResults[index] ? '收起' : '展开' }}
            </button>
          </div>
        </div>

        <!-- tool_end -->
        <div v-else-if="step.type === 'tool_end'" class="step-line step-end">
          <span class="step-icon">✅</span>
          <span class="step-text">
            检索到 <strong>{{ step.count ?? step.sources?.length ?? 0 }}</strong> 篇相关文档
            <span v-if="step.sources?.length" class="step-end-sources">
              — {{ step.sources.join(', ') }}
            </span>
          </span>
        </div>

        <!-- compressed -->
        <div v-else-if="step.type === 'compressed'" class="step-line step-compress">
          <span class="step-icon">🗜</span>
          <span class="step-text">
            已压缩 <strong>{{ step.extra?.compressed_count ?? 0 }}</strong> 条历史消息
            <template v-if="step.extra?.summary_length">
              为 {{ step.extra.summary_length }} 字摘要
            </template>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agent-steps {
  margin-bottom: var(--spacing-md);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  font-size: 13px;
}

/* ---- 思考步骤 Header ---- */
.steps-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-secondary);
  cursor: pointer;
  user-select: none;
  transition: background 0.15s ease;
}

.steps-header:hover {
  background: #f0f0f0;
}

.steps-header-icon {
  font-size: 10px;
  color: var(--text-secondary);
  width: 12px;
}

.steps-header-text {
  flex: 1;
  font-weight: 500;
  color: var(--text-secondary);
}

.steps-badge {
  font-size: 11px;
  background: var(--border);
  color: var(--text-secondary);
  padding: 1px 6px;
  border-radius: 10px;
}

/* ---- 思考步骤 Body ---- */
.steps-body {
  padding: var(--spacing-sm) var(--spacing-md);
  border-left: 3px solid var(--border);
  margin-left: var(--spacing-sm);
}

.step-item {
  padding: 3px 0;
  border-bottom: 1px solid var(--border-light);
}

.step-item:last-child {
  border-bottom: none;
}

.step-line {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 2px 0;
  color: var(--thinking);
  line-height: 1.5;
}

.step-icon {
  flex-shrink: 0;
  font-size: 13px;
}

.step-text {
  color: var(--text-secondary);
}

/* ---- 各类型样式 ---- */
.step-cache .step-text {
  color: var(--success);
  font-weight: 500;
}

.step-tool-name {
  font-size: 12px;
  background: var(--bg-secondary);
  padding: 1px 5px;
  border-radius: 3px;
  font-family: 'Fira Code', 'Consolas', monospace;
}

.step-tool-input {
  color: var(--text-secondary);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 300px;
  display: inline-block;
  vertical-align: bottom;
}

/* ---- tool_result ---- */
.step-result {
  display: flex;
  gap: 6px;
  padding: 4px 0;
  line-height: 1.5;
}

.step-result-content {
  flex: 1;
  min-width: 0;
}

.step-result-label {
  font-size: 11px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.step-result-text {
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-secondary);
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-sm);
  margin-top: 2px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 120px;
  overflow-y: auto;
  line-height: 1.6;
}

.step-result-toggle {
  font-size: 11px;
  color: var(--text-primary);
  background: none;
  border: none;
  cursor: pointer;
  padding: 1px 0;
  margin-top: 2px;
  text-decoration: underline;
  opacity: 0.7;
  transition: opacity 0.15s;
}

.step-result-toggle:hover {
  opacity: 1;
}

/* ---- tool_end ---- */
.step-end .step-text {
  color: var(--success);
}

.step-end-sources {
  font-size: 11px;
  opacity: 0.8;
}

/* ---- compress ---- */
.step-compress .step-text {
  color: var(--text-secondary);
  font-style: italic;
}

.step-text strong {
  color: var(--text-primary);
  font-weight: 600;
}
</style>
