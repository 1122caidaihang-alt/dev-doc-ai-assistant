"""
核心对话服务 — 编排整个问答流程
当前 Phase 2: 基础 RAG + LLM（无 Agent、无缓存、无记忆）
后续 Phase 会逐步加入 Agent 决策、记忆管理、检索增强、缓存
"""
import json
import httpx
from typing import List, Dict
from config import KIMI_API_KEY, KIMI_BASE_URL, KIMI_CHAT_MODEL
from services.rag_service import search_documents


def call_kimi_chat(messages: List[Dict], stream: bool = True, max_tokens: int = 2048):
    """
    调 Kimi Chat API

    messages 格式:
      [{"role": "system", "content": "你是技术文档助手..."},
       {"role": "user",   "content": "如何配置数据库连接？"}]

    返回:
      stream=True  → httpx 的流式响应对象（逐行读取）
      stream=False → JSON 响应体
    """
    if not KIMI_API_KEY or KIMI_API_KEY == "sk-your-key-here":
        raise RuntimeError("KIMI_API_KEY 未设置，请在 backend/.env 文件中配置")

    url = f"{KIMI_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {KIMI_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": KIMI_CHAT_MODEL,
        "messages": messages,
        "temperature": 0.3,      # 低温度 = 更精确，少自由发挥
        "max_tokens": max_tokens,
        "stream": stream,
    }

    response = httpx.post(url, headers=headers, json=body, timeout=60.0)
    response.raise_for_status()
    return response


def build_prompt(question: str, retrieved_docs: List[Dict]) -> List[Dict]:
    """
    拼装 Prompt — STEP 7（上下文拼装）的具体实现

    把检索到的文档片段 + 角色指令 + 用户问题拼成 messages 列表
    这个 messages 列表直接传给 Kimi Chat API
    """
    # 拼文档片段
    docs_text = ""
    for i, doc in enumerate(retrieved_docs):
        docs_text += f"\n[文档{i+1}] 来源: {doc['source']} (相似度: {doc['similarity']})\n{doc['content']}\n"

    # System Prompt — 角色设定 + 行为约束
    system_prompt = f"""你是技术文档助手。请基于以下提供的文档片段回答用户问题。

规则：
1. 只能基于提供的文档片段回答，绝对不要编造不存在于文档中的信息
2. 如果文档中没有相关答案，明确说"当前文档库未收录相关内容，建议去 GitHub Issues 搜索或提交新 Issue"
3. 回答末尾列出参考的文档来源
4. 回答格式用 Markdown，代码块标注语言

参考文档片段：
{docs_text}"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]


def ask(question: str, session_id: str = "default"):
    """
    核心问答函数 — 返回一个生成器（generator），逐块产出内容

    流程:
      STEP 4: RAG 检索 → STEP 7: 拼 Prompt → STEP 8: LLM 流式生成

    调用方式:
      for chunk in ask("如何配置数据库"):
          if chunk["type"] == "answer":
              print(chunk["content"], end="")

    这是一个 Python generator（生成器函数），用 yield 逐个产出数据块。
    调用方迭代它来消费流式结果。
    """
    # 拼装并推送 thinking 事件到 SSE 流
    thinking_steps = [
        ("thinking", "正在分析问题意图..."),
        ("thinking", "正在搜索知识库..."),
    ]
    for event_type, message in thinking_steps:
        yield {"type": event_type, "content": message}

    # Step 4: RAG 检索
    docs = search_documents(question, top_k=5)

    if not docs:
        yield {"type": "thinking", "content": "知识库中未找到相关内容。"}
        yield {"type": "answer", "content": "当前文档库未收录相关内容。"}
        yield {"type": "done", "content": ""}
        return

    yield {"type": "tool_end", "tool": "search_docs",
           "result_count": len(docs),
           "sources": list(set(d["source"] for d in docs))}

    # Step 7: 拼装 Prompt
    messages = build_prompt(question, docs)

    # Step 8: 调 LLM 流式生成
    yield {"type": "thinking", "content": "正在基于文档生成回答..."}

    try:
        response = call_kimi_chat(messages, stream=True)

        # 逐行解析 Kimi 返回的 SSE 流
        for line in response.iter_lines():
            if line.startswith("data: "):
                data = line[6:]  # 去掉 "data: " 前缀
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        # 每个 token 作为一个 event 推送
                        yield {"type": "answer", "content": content}
                except json.JSONDecodeError:
                    continue

    except Exception as e:
        yield {"type": "error", "content": f"AI 服务暂时不可用: {str(e)}"}
        return

    # 推送引用来源
    yield {"type": "sources", "sources": list(set(doc["source"] for doc in docs))}
    yield {"type": "done", "content": ""}


def ask_with_agent(question: str, session_id: str = "default"):
    """
    带 Agent 决策的问答 — Phase 3 新增
    跟 ask() 的区别：LLM 通过 ReAct 循环自己决定要不要查文档、查几次

    流程:
      Agent 收到问题 → Thought: 需要查文档
      → Action: search_docs("权限注解配置")
      → Observation: [检索结果]
      → Thought: 信息够了
      → Final Answer: 输出答案
    """
    from services.agent_service import get_agent
    agent = get_agent()

    # 推送初始思考步骤
    yield {"type": "thinking", "content": "Agent 正在分析问题意图..."}

    try:
        # AgentExecutor.invoke() 执行完整的 ReAct 循环
        # 返回: {"input": "...", "output": "最终答案", "intermediate_steps": [...]}
        result = agent.invoke({"input": question})

        # intermediate_steps 包含每一步的 (AgentAction, observation)
        # AgentAction 有 .tool 和 .tool_input 属性
        if "intermediate_steps" in result:
            for step in result["intermediate_steps"]:
                action = step[0]  # AgentAction 对象
                observation = step[1]  # 工具返回的字符串

                # 推送工具调用信息
                yield {"type": "tool_call",
                       "tool": action.tool,
                       "input": action.tool_input}
                yield {"type": "tool_result",
                       "content": observation[:300] + ("..." if len(observation) > 300 else "")}

            yield {"type": "tool_end",
                   "tool": "Agent 推理完成",
                   "result_count": len(result["intermediate_steps"]),
                   "sources": []}

        # 推送答案 — 模拟流式效果（逐字符）
        # Agent.invoke 是一次性返回的，不是真流式
        # 但我们可以按字符分块推送，前端看起来还是流式的
        answer = result.get("output", "")
        yield {"type": "thinking", "content": "正在组织回答..."}

        for char in answer:
            yield {"type": "answer", "content": char}

        yield {"type": "done", "content": ""}

    except Exception as e:
        yield {"type": "error", "content": f"Agent 执行失败: {str(e)}"}
