"""
LangChain Agent 服务 — 管理工具调度和 Agent 循环
面试核心模块：AgentExecutor 内部工作机制

2026-06-18: 从 ReAct 文本格式切换到 OpenAI Function Calling
原因：DeepSeek 不遵循 ReAct 的 Thought/Action/Final Answer 文本格式，
输出常出现 "Missing 'Action:' after 'Thought:'" 解析错误。
Function Calling 是结构化 JSON，DeepSeek 原生支持，不再依赖文本解析。
"""
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain.tools import Tool
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.callbacks.base import BaseCallbackHandler
from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_CHAT_MODEL,
    MAX_REACT_ITERATIONS,
)
from tools.search_docs import search_docs


class AgentStreamCallback(BaseCallbackHandler):
    """
    LangChain 回调 — 在 Agent ReAct 循环中实时捕获 LLM 输出 token
    用于向前端推送"正在思考"的进度，解决 agent.invoke() 阻塞期间前端无反馈的问题
    """

    def __init__(self):
        self.events = []           # [(type, data), ...] 累积事件列表
        self._lock = threading.Lock()

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        """每次 LLM 输出一个新 token 时触发"""
        with self._lock:
            self.events.append(("token", token))

    def on_agent_action(self, action, **kwargs) -> None:
        """Agent 决定调用工具时触发"""
        with self._lock:
            self.events.append(("tool_call", {
                "tool": action.tool,
                "input": action.tool_input,
            }))

    def on_tool_end(self, output: str, **kwargs) -> None:
        """工具执行完成时触发"""
        with self._lock:
            self.events.append(("tool_result", output))

    def get_new_events(self, since_index: int):
        """获取 since_index 之后的新事件，线程安全"""
        with self._lock:
            new = self.events[since_index:]
            return new, len(self.events)


def invoke_agent_with_progress(agent: AgentExecutor, input_data: dict, poll_interval: float = 0.5):
    """
    在后台线程运行 agent.invoke()，主线程轮询进度 — 生成器

    解决 agent.invoke() 阻塞 30-60 秒期间前端无反馈的问题：
    - 后台线程：跑 agent.invoke()（支持 streaming=True，LLM 逐 token 输出）
    - 主线程：每 poll_interval 秒检查一次回调事件，有新事件就 yield
    - invoke 完成后再 yield 最终结果

    Yields:
        {"type": "thinking", "content": "Agent 正在推理（已收到 N token）..."}  — 进度更新
        {"type": "tool_call", "tool": ..., "input": ...}                         — 工具调用
        {"type": "tool_result", "content": ...}                                  — 工具结果
        {"type": "result", "data": {...}}                                        — 最终结果
    """
    callback = AgentStreamCallback()

    # 在后台线程执行 agent.invoke（阻塞操作）
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(
        agent.invoke,
        input_data,
        {"callbacks": [callback]},
    )

    last_event_idx = 0
    start_time = __import__("time").time()
    last_report_time = 0  # 上次推送进度的时间戳
    poll_count = 0

    try:
        while not future.done():
            poll_count += 1

            # 检查新事件（tool_call / tool_result）— 这些不依赖 streaming
            new_events, last_event_idx = callback.get_new_events(last_event_idx)

            for event_type, data in new_events:
                if event_type == "tool_call":
                    yield {"type": "tool_call", "tool": data["tool"], "input": data["input"]}
                elif event_type == "tool_result":
                    yield {"type": "tool_result", "content": data}

            # 推送进度 — 每 3 秒推一次，避免前端思考面板刷屏
            now = __import__("time").time()
            elapsed = int(now - start_time)
            if now - last_report_time >= 3:
                yield {"type": "thinking", "content": f"Agent 正在推理中（已运行 {elapsed} 秒）..."}
                last_report_time = now

            # 等待一小段时间再检查
            # 只捕获 TimeoutError（还没完成），其他异常说明 agent.invoke() 报错了
            try:
                future.result(timeout=poll_interval)
            except FutureTimeoutError:
                pass  # 超时正常，继续轮询

        # 获取最终结果 — 如果后台线程抛了异常，这里会重新抛出
        result = future.result()
        yield {"type": "result", "data": result}

    except Exception as e:
        yield {"type": "result", "data": {"output": "", "error": str(e), "intermediate_steps": []}}
    finally:
        executor.shutdown(wait=False)
        # 确保 done 事件后也推送最终结果（如果还没推送的话）


# ============================================================
# System Prompt — Function Calling 只需要一段角色指令
# 工具以 JSON Schema 形式发给 LLM，LLM 返回结构化 function call
# 不需要 ReAct 那种 "Thought:/Action:/Action Input:" 文本格式
# ============================================================
SYSTEM_PROMPT = """你是技术文档助手。你可以使用工具搜索知识库来回答问题。

重要规则：
1. 先查文档再回答，永远不要凭记忆直接给答案
2. 搜索 1-2 次就够了，拿到结果就立即回答，不要重复搜索同一个问题
3. 如果工具返回"未找到"，诚实告知用户
4. 回答用 Markdown 格式，末尾列出参考的文档来源"""

# ChatPromptTemplate — Function Calling Agent 要求的格式
# agent_scratchpad 是 LangChain 内部存储 function call 历史的位置
AGENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("user", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])


def create_agent() -> AgentExecutor:
    """
    创建 LangChain Agent 实例（OpenAI Function Calling 模式）

    返回一个 AgentExecutor，调用 agent.invoke({"input": "问题"}) 触发循环

    工作流程（面试重点）：
    1. 把 System Prompt + 用户问题 + 工具 JSON Schema 发给 LLM
    2. LLM 返回 function call（结构化 JSON，不是文本）或最终回答
    3. 如果是 function call → 执行工具 → 结果返回 LLM → 回到第 2 步
    4. 如果是最终回答 → 返回答案，循环结束
    5. 循环最多 MAX_REACT_ITERATIONS 次

    跟 ReAct 的区别：工具调用是 OpenAI 原生 Function Calling 格式，
    LLM 不需要手写 "Thought:/Action:" 文本，DeepSeek 完全兼容。
    """

    # 1. 创建 LLM 实例
    # DeepSeek API 兼容 OpenAI 接口格式，包括 Function Calling
    llm = ChatOpenAI(
        model=DEEPSEEK_CHAT_MODEL,
        openai_api_key=DEEPSEEK_API_KEY,
        openai_api_base=DEEPSEEK_BASE_URL,
        temperature=0.3,
        max_tokens=2048,
    )

    # 2. 定义工具列表
    # 每个 Tool: name + func + description
    # Function Calling 模式下，description 自动转为 JSON Schema 的 description 字段
    tools = [
        Tool(
            name="search_docs",
            func=search_docs,
            description="搜索技术文档知识库。当需要查找配置方法、API 说明、"
                        "使用示例、报错解决方案时使用此工具。输入为搜索关键词字符串。",
        ),
    ]

    # 3. 创建 Tool Calling Agent（DeepSeek 原生支持）
    agent = create_tool_calling_agent(
        llm=llm,
        tools=tools,
        prompt=AGENT_PROMPT,
    )

    # 4. 包装为 AgentExecutor — 管理循环、工具调度、异常处理
    agent_executor = AgentExecutor.from_agent_and_tools(
        agent=agent,
        tools=tools,
        verbose=False,                        # 关闭 verbose，避免 StdOutCallbackHandler 冲突
        max_iterations=MAX_REACT_ITERATIONS,  # 最多 5 轮
        handle_parsing_errors=True,           # 输出格式错误时自动重试
    )

    return agent_executor


# 全局单例 — 复用同一个 Agent，不需要每次请求都初始化 LLM 连接
_agent_executor = None


def get_agent() -> AgentExecutor:
    """获取全局 Agent 单例"""
    global _agent_executor
    if _agent_executor is None:
        _agent_executor = create_agent()
    return _agent_executor
