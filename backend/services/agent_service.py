"""
LangChain Agent 服务 — 管理 ReAct 循环和工具调度
面试核心模块：AgentExecutor 内部工作机制
"""
from langchain.agents import create_react_agent, AgentExecutor
from langchain.tools import Tool
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from config import (
    KIMI_API_KEY, KIMI_BASE_URL, KIMI_CHAT_MODEL,
    MAX_REACT_ITERATIONS,
)
from tools.search_docs import search_docs


# ReAct Prompt 模板
# 格式: Thought → Action → Action Input → Observation → ... → Final Answer
# {tools} 和 {tool_names} 由 LangChain 自动填充
# {input} 是用户问题, {agent_scratchpad} 是 LangChain 内部记录循环状态
REACT_PROMPT = PromptTemplate.from_template("""你是技术文档助手。你可以使用工具搜索知识库来回答问题。

可用工具:
{tools}

工具名称: {tool_names}

使用以下格式回答:

Question: 用户的问题
Thought: 我应该查什么？怎么回答？
Action: 工具名称（必须是 [{tool_names}] 之一）
Action Input: 搜索关键词
Observation: 工具返回的结果
... (这个 Thought/Action/Action Input/Observation 可以重复)
Thought: 我现在有足够的信息来回答了
Final Answer: 基于文档的最终答案

重要规则：
1. 只能使用上面的工具，不要编造工具名
2. 先查文档再回答，永远不要凭记忆直接给答案
3. 如果工具返回"未找到"，诚实告知用户
4. Final Answer 用 Markdown 格式，末尾列出参考的文档来源

开始!

Question: {input}
Thought: {agent_scratchpad}
""")


def create_agent() -> AgentExecutor:
    """
    创建 LangChain Agent 实例

    返回一个 AgentExecutor，调用 agent.invoke({"input": "问题"}) 即可触发 ReAct 循环

    AgentExecutor 内部工作流程（面试重点）：
    1. 接收用户问题
    2. 把问题 + 工具列表 + ReAct Prompt 发给 LLM
    3. LLM 返回 Thought + Action 或 Final Answer
    4. 如果是 Action → ToolDispatcher 找到对应工具 → 执行 → 结果拼回 Prompt → 回第 3 步
    5. 如果是 Final Answer → 返回答案，循环结束
    6. 循环最多 MAX_REACT_ITERATIONS 次（防止 LLM 死循环）
    """

    # 1. 创建 LLM 实例
    # Kimi API 兼容 OpenAI 接口格式，所以用 ChatOpenAI 客户端
    llm = ChatOpenAI(
        model=KIMI_CHAT_MODEL,
        openai_api_key=KIMI_API_KEY,
        openai_api_base=KIMI_BASE_URL,
        temperature=0.3,
        max_tokens=2048,
    )

    # 2. 定义工具列表
    # 每个 Tool: name(LLM 用这个名字调用), func(实际执行的函数), description(LLM 靠这个判断何时用)
    tools = [
        Tool(
            name="search_docs",
            func=search_docs,
            description="搜索技术文档知识库。当需要查找配置方法、API 说明、"
                        "使用示例、报错解决方案时使用此工具。输入为搜索关键词字符串。",
        ),
    ]

    # 3. 创建 ReAct Agent
    agent = create_react_agent(
        llm=llm,
        tools=tools,
        prompt=REACT_PROMPT,
    )

    # 4. 包装为 AgentExecutor — 管理 ReAct 循环、工具调度、异常处理
    agent_executor = AgentExecutor.from_agent_and_tools(
        agent=agent,
        tools=tools,
        verbose=True,                         # 打印详细 ReAct 步骤日志
        max_iterations=MAX_REACT_ITERATIONS,  # 最多 5 轮
        handle_parsing_errors=True,           # LLM 输出格式错误时自动重试
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
