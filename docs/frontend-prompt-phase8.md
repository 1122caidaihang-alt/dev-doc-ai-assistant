# Phase 8：前端 Chat UI 实施 Prompt

> **使用方法**：把这份文档发给 VS Code Claude，让它按步骤执行。
> **项目路径**：`D:\Projects\dev-doc-ai-assistant\frontend\`（新项目，需从零创建）

---

## 0. 项目概述

你要做一个**开发者文档 AI 知识助手的 Chat UI**。后端是 Python FastAPI，已部署在 `http://localhost:8000`，提供 POST `/chat` SSE 流式接口。

### 核心功能
1. 用户输入问题 → 点击发送 → SSE 流式接收 Agent 回答
2. 展示 Agent 思考过程（检索了哪些文档、调了什么工具）
3. 展示记忆加载状态、缓存命中状态
4. Markdown 格式渲染（代码高亮、引用标注）
5. Session 管理（localStorage 持久化 session_id）

### 技术栈
- Vue3 + Vite（Composition API，`<script setup>`）
- Pinia（状态管理）
- marked（Markdown 渲染）
- 纯 CSS（极简黑白风，不用 UI 库）

---

## 1. 创建项目

```bash
cd D:\Projects\dev-doc-ai-assistant
npm create vite@latest frontend -- --template vue
cd frontend
npm install
npm install pinia marked
```

清理默认文件：删掉 `src/components/HelloWorld.vue`、`src/assets/vue.svg`、`src/style.css` 的默认样式。

---

## 2. 后端 API 接口说明

### 核心接口：POST /chat

```
POST http://localhost:8000/chat
Content-Type: application/json

{
  "question": "Redis 缓存怎么配置",
  "session_id": "abc123-def456"
}
```

响应：`Content-Type: text/event-stream`（SSE 格式）

### SSE 事件类型（按出现顺序）

| event | data 格式 | 含义 | 前端展示 |
|-------|----------|------|---------|
| `thinking` | 纯文本字符串 | Agent 思考步骤 | 灰色小字，逐条追加到思考面板 |
| `memory` | `{"message_count": 20, "token_usage": 45.2}` | 已加载历史上下文 | "📚 已加载 20 条历史消息（45.2% token）" |
| `cache_hit` | `"缓存命中"` | 语义缓存命中 | "⚡ 缓存命中，跳过检索直接返回" |
| `tool_call` | `{"tool": "search_docs", "input": {"query": "Redis 缓存"}}` | Agent 调用工具 | 可折叠面板，显示工具名和参数 |
| `tool_result` | `{"content": "文档片段..."}` | 工具返回结果 | 展开显示（截断 300 字符 + "..."） |
| `tool_end` | `{"tool": "Agent 推理完成", "result_count": 5, "sources": ["redis-cache.md"]}` | 工具调用完成 | "✅ 检索到 5 篇相关文档" |
| `compressed` | `{"compressed_count": 12, "summary_length": 180}` | 记忆压缩完成 | "🗜 已压缩 12 条历史消息为 180 字摘要" |
| `answer` | 纯文本字符串（1 个 token） | 逐 token 答案 | 追加到助手消息气泡，Markdown 实时渲染 |
| `sources` | `["redis-cache.md", "quick-start.md"]` | 引用文档来源 | 回答底部文档标签列表 |
| `done` | `{}` | 传输完成 | 恢复输入框，停止 loading |
| `error` | `{"message": "错误原因"}` | 出错 | 红色错误提示 |

### SSE 原始格式示例

```
event: thinking
data: Agent 正在分析问题意图...

event: tool_call
data: {"tool": "search_docs", "input": {"query": "Redis 缓存配置"}}

event: tool_result
data: {"content": "[文档1] spring.redis.host=127.0.0.1..."}

event: tool_end
data: {"tool": "search_docs", "result_count": 5, "sources": ["redis-cache.md"]}

event: answer
data: Redis

event: answer
data:  缓存配置在

event: answer
data: application.yml 中...

event: sources
data: ["redis-cache.md", "quick-start.md"]

event: done
data: {}
```

---

## 3. Pinia Store（`src/stores/chat.js`）

管哪些状态：

```javascript
// 会话
sessionId: ''        // 从 localStorage 恢复，首次自动生成
sessionName: ''      // 可选，用第一个问题截断

// 消息列表（核心数据结构）
messages: [
  {
    id: 'msg-1',
    role: 'user',           // 'user' | 'assistant'
    content: 'Redis 缓存怎么配置',   // 完整文本（user 一次性，assistant 逐 token 追加）
    timestamp: 1700000000,
    // 仅 assistant 有：
    thinking: [             // Agent 思考步骤列表
      { type: 'thinking', text: '正在检索...' },
      { type: 'memory', text: '已加载 20 条消息', extra: { message_count: 20, token_usage: 45.2 } },
      { type: 'tool_call', tool: 'search_docs', input: {...} },
      { type: 'tool_result', text: '文档片段...' },
      { type: 'tool_end', text: '找到 5 篇文档', sources: ['redis-cache.md'] },
      { type: 'compressed', text: '压缩 12 条消息', extra: { compressed_count: 12 } },
    ],
    sources: [],            // 引用文档来源列表
    isStreaming: false,     // 是否还在接收 SSE 流
    error: null,            // 错误信息
  }
]

// UI 状态
isLoading: false            // 是否正在等待响应
isStreaming: false          // 是否正在流式接收
```

actions：

```javascript
// sendMessage(question) - 核心函数
//   1. 生成 sessionId（如不存在）
//   2. 创建 user message 追加到 messages
//   3. 创建空的 assistant message（isStreaming=true）
//   4. fetch POST /chat，ReadableStream 逐行解析 SSE
//   5. 根据 event 类型更新 assistant message 的 content/thinking/sources
//   6. done 时设置 isStreaming=false，保存 sessionId 到 localStorage

// generateSessionId() - 生成随机 session_id（uuid v4 或 crypto.randomUUID()）
// loadSession() - 从 localStorage 恢复 sessionId
// clearMessages() - 清空消息（可选）
```

---

## 4. 组件实现

### 4.1 `App.vue` — 根布局

```
┌────────────────────────────────────────────┐
│  ChatHeader（固定顶部）                     │
├────────────────────────────────────────────┤
│  ChatArea（flex: 1, overflow-y: auto）      │
│    ├ 空状态提示（无消息时）                   │
│    └ ChatBubble × N                        │
├────────────────────────────────────────────┤
│  ChatInput（固定底部）                       │
└────────────────────────────────────────────┘
```

结构：
```html
<div class="app-container">
  <ChatHeader />
  <ChatArea :messages="chatStore.messages" />
  <ChatInput @send="chatStore.sendMessage" :disabled="chatStore.isLoading" />
</div>
```

高度 100vh，flex column 布局。

### 4.2 `ChatHeader.vue` — 顶部栏

- 左侧：标题 "文档 AI 助手" + 小字 "基于 156 篇芋道官方文档"
- 右侧：Session ID（截断显示前 8 位）+ 复制按钮 + 新对话按钮
- 高度 ~56px，底部细线分隔

### 4.3 `ChatArea.vue` — 消息列表

- 接收 `messages` props
- 自动滚到底部（消息更新时 `scrollTop = scrollHeight`）
- 空状态：
  ```
  💬
  向你的技术文档 AI 助手提问
  例如：Redis 缓存怎么配置？
  ```
- 新消息出现时平滑滚动（`scroll-behavior: smooth`）

### 4.4 `ChatBubble.vue` — 单条消息

Props：
- `message` — 消息对象
- `role` — 'user' | 'assistant'

**用户消息**（右对齐）：
- 黑底白字圆角气泡
- 显示时间戳
- 最大宽度 70%

**助手消息**（左对齐）：
- 包含两个区域：

**A. 思考过程区**（可折叠，默认展开，done 后自动折叠）：
```
┌──────────────────────────────────┐
│ 🧠 Agent 思考过程         [收起] │
│ ┌──────────────────────────────┐ │
│ │ 💭 正在分析问题意图...        │ │
│ │ 📚 已加载 20 条历史消息       │ │
│ │ 🔧 调用 search_docs          │ │
│ │   └ "Redis 缓存配置"         │ │
│ │ 📄 找到文档片段 (300字)      │ │
│ │   └ 展开/收起                 │ │
│ │ ✅ 检索到 5 篇相关文档        │ │
│ │ 💭 正在基于文档生成回答...    │ │
│ └──────────────────────────────┘ │
└──────────────────────────────────┘
```

- `thinking` 事件：灰色文字 + 旋转圆点动画
- `memory` 事件：📚 图标 + 数据展示
- `cache_hit` 事件：⚡ 绿色高亮
- `tool_call` 事件：🔧 图标 + 工具名 + 参数（代码样式）
- `tool_result` 事件：📄 可展开文本（截断显示前 150 字 + "点击展开"）
- `tool_end` 事件：✅ 图标 + 来源数
- `compressed` 事件：🗜 图标 + 压缩统计

**B. 回答内容区**：
- Markdown 渲染（用 marked 库）
- 代码块深色背景 + 语法高亮（可用简单的 CSS 模拟）
- 引用标注 `[来源: xxx.md]` 和 `[推断]` 不同颜色（来源绿色，推断灰色）
- 流式输出时最后有闪烁光标 `▊`

**C. 底部来源区**：
- 标签形式展示 `sources` 列表
- 每个标签 "📎 redis-cache.md"

### 4.5 `ChatInput.vue` — 输入框

- Textarea（自动增高，最大 4 行）
- 发送按钮（右侧，圆角黑底白字箭头）
- Enter 发送（Shift+Enter 换行）
- 空内容不允许发送
- loading 时禁用输入 + 按钮显示 loading 动画
- placeholder："输入你的技术问题..."

### 4.6 `AgentSteps.vue` — 思考步骤列表（子组件）

在 ChatBubble 内部使用，专门渲染 Agent 思考步骤。
接收 `steps` 数组，每种 type 渲染不同样式：

```javascript
// 步骤类型 → 展示
const stepRenderers = {
  thinking: (step) => `<span class="step-thinking">💭 ${step.text}</span>`,
  memory:   (step) => `<span class="step-memory">📚 ${step.text}</span>`,
  cache_hit: (step) => `<span class="step-cache">⚡ ${step.text}</span>`,
  tool_call: (step) => `<span class="step-tool">🔧 <code>${step.tool}</code>(${step.input.query})</span>`,
  tool_result: (step) => `<details><summary>📄 检索结果</summary>${step.text}</details>`,
  tool_end: (step) => `<span class="step-end">✅ ${step.text}</span>`,
  compressed: (step) => `<span class="step-compress">🗜 ${step.text}</span>`,
}
```

---

## 5. SSE 流解析（核心逻辑，放在 `src/utils/sse.js`）

```javascript
/**
 * 发送消息并建立 SSE 连接
 * @param {string} question - 用户问题
 * @param {string} sessionId - 会话 ID
 * @param {object} callbacks - 事件回调 { onThinking, onMemory, onToolCall, ... }
 * @returns {AbortController} - 用于取消请求
 */
export async function connectSSE(question, sessionId, callbacks) {
  const controller = new AbortController();

  try {
    const response = await fetch('http://localhost:8000/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, session_id: sessionId }),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    // 获取 ReadableStream reader
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';  // 缓冲区——处理跨 chunk 的不完整行

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE 事件以 \n\n 分隔
      const parts = buffer.split('\n\n');
      buffer = parts.pop(); // 最后一部分可能不完整，留着下次拼

      for (const part of parts) {
        if (!part.trim()) continue;

        const lines = part.split('\n');
        let eventType = '';
        let data = '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            data = line.slice(6);
          }
        }

        if (eventType && data) {
          dispatchEvent(eventType, data, callbacks);
        }
      }
    }
  } catch (err) {
    if (err.name === 'AbortError') return;
    if (callbacks.onError) callbacks.onError(err.message);
  }

  return controller;
}

function dispatchEvent(type, data, callbacks) {
  switch (type) {
    case 'thinking':
      callbacks.onThinking?.(data);
      break;
    case 'memory':
      callbacks.onMemory?.(JSON.parse(data));
      break;
    case 'cache_hit':
      callbacks.onCacheHit?.(data);
      break;
    case 'tool_call':
      callbacks.onToolCall?.(JSON.parse(data));
      break;
    case 'tool_result':
      callbacks.onToolResult?.(JSON.parse(data));
      break;
    case 'tool_end':
      callbacks.onToolEnd?.(JSON.parse(data));
      break;
    case 'compressed':
      callbacks.onCompressed?.(JSON.parse(data));
      break;
    case 'answer':
      callbacks.onAnswer?.(data);       // data 直接是文本，不用 JSON.parse
      break;
    case 'sources':
      callbacks.onSources?.(JSON.parse(data));
      break;
    case 'done':
      callbacks.onDone?.();
      break;
    case 'error':
      callbacks.onError?.(JSON.parse(data).message || data);
      break;
  }
}
```

**关键坑点**：
- `answer` 事件的 data 是**纯文本**，不是 JSON，不要用 `JSON.parse()`
- 其他事件都是 JSON 字符串
- `buffer` 处理：TCP 流可能把一行切成两个 chunk，用 split('\n\n') + pop() 处理不完整事件

---

## 6. 样式规范（极简黑白风）

### 颜色系统
```css
:root {
  --bg-primary: #ffffff;
  --bg-secondary: #f8f8f8;
  --bg-dark: #1a1a1a;
  --text-primary: #1a1a1a;
  --text-secondary: #6b6b6b;
  --text-light: #ffffff;
  --border: #e5e5e5;
  --accent: #1a1a1a;
  --error: #d32f2f;
  --success: #2e7d32;
  --thinking: #6b6b6b;
  --tool: #1a1a1a;
}
```

### 字体
```css
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC',
             'Microsoft YaHei', sans-serif;
```

### 风格要点
- 不要圆角过大（4-6px），不要彩色渐变，不要阴影过重
- 用户气泡：深色背景（`#1a1a1a`），白色文字
- 助手气泡：白色背景，细微边框（`1px solid #e5e5e5`）
- 代码块：`#1e1e1e` 背景，等宽字体，圆角 4px
- 思考步骤：左侧细竖线（类似 GitHub 引用块），灰色文字
- 输入区：顶部细线分隔，输入框无边框只底部横线
- 过渡动画：`transition: all 0.2s ease`

---

## 7. 文件清单（按创建顺序）

```
frontend/
├── index.html                    ← 修改标题为"文档 AI 助手"
├── src/
│   ├── main.js                   ← 注册 Pinia
│   ├── App.vue                   ← 根布局（重新写）
│   ├── style.css                 ← 全局样式 + CSS 变量（重新写）
│   ├── utils/
│   │   └── sse.js                ← SSE 流解析（新建）
│   ├── stores/
│   │   └── chat.js               ← Pinia store（新建）
│   └── components/
│       ├── ChatHeader.vue        ← 顶部栏（新建）
│       ├── ChatArea.vue          ← 消息列表容器（新建）
│       ├── ChatBubble.vue        ← 单条消息气泡（新建）
│       ├── AgentSteps.vue        ← Agent 思考步骤（新建，ChatBubble 内部使用）
│       └── ChatInput.vue         ← 输入框（新建）
```

---

## 8. 实施顺序（按文件）

### Step 1：脚手架清理
- 修改 `index.html`：标题、meta
- 清空 `src/style.css`，写入 CSS 变量和全局样式
- 修改 `src/main.js`：引入 Pinia
- 清理 `src/assets/`

### Step 2：SSE 工具（`src/utils/sse.js`）
- 按第 5 节实现 `connectSSE` 函数
- 这是最核心的底层，实现后 store 和组件才能用

### Step 3：Pinia Store（`src/stores/chat.js`）
- 按第 3 节实现状态管理
- `sendMessage` action 调用 `connectSSE`，在回调里更新 reactive 数据

### Step 4：组件逐个实现
1. `ChatInput.vue`（先做输入，可以测试发送）
2. `ChatHeader.vue`（顶部栏）
3. `AgentSteps.vue`（思考步骤子组件）
4. `ChatBubble.vue`（消息气泡，引用 AgentSteps）
5. `ChatArea.vue`（消息列表 + 空状态）
6. `App.vue`（拼装所有组件）

### Step 5：联调测试
```bash
cd frontend
npm run dev
```
确保后端 `http://localhost:8000` 已启动，用浏览器打开前端测试完整流程。

---

## 9. 注意事项

1. **跨域**：后端已配 CORS `allow_origins=["*"]`，开发时 `localhost:5173` 调 `localhost:8000` 没问题
2. **后端地址**：开发时写 `http://localhost:8000`，部署时改成环境变量 `VITE_API_BASE_URL`
3. **answer 事件特殊**：data 是纯文本不是 JSON，和其他事件不同
4. **buffer 处理**：SSE 流可能把一行切成两个 TCP 包，必须用 buffer+split+pop 处理
5. **错误处理**：fetch 失败（后端挂了、网络断了）要有友好提示，而不是空白页
6. **Markdown 安全**：marked 只渲染，不要执行 `<script>`（marked 默认 escape HTML）
7. **session_id 生成**：用 `crypto.randomUUID()` 或手动 uuid v4
