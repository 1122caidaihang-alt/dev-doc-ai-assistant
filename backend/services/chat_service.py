"""
核心对话服务 — 编排整个问答流程
当前 Phase 2: 基础 RAG + LLM（无 Agent、无缓存、无记忆）
后续 Phase 会逐步加入 Agent 决策、记忆管理、检索增强、缓存
"""
import json
import httpx
from typing import List, Dict
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_CHAT_MODEL
from services.rag_service import search_documents, hybrid_search


def call_deepseek_chat(messages: List[Dict], stream: bool = True, max_tokens: int = 2048):
    """
    调 DeepSeek Chat API

    messages 格式:
      [{"role": "system", "content": "你是技术文档助手..."},
       {"role": "user",   "content": "如何配置数据库连接？"}]

    返回:
      stream=True  → httpx 的流式响应对象（逐行读取）
      stream=False → JSON 响应体
    """
    if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == "sk-your-key-here":
        raise RuntimeError("DEEPSEEK_API_KEY 未设置，请在 backend/.env 文件中配置")

    url = f"{DEEPSEEK_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": DEEPSEEK_CHAT_MODEL,
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
    这个 messages 列表直接传给 DeepSeek Chat API
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
    from services.cache_service import check_cache, store_cache

    # ============================================
    # 第 0 步：检查语义缓存（Phase 6）
    # ============================================
    cached_answer = check_cache(session_id, question)
    if cached_answer:
        yield {"type": "thinking", "content": "检测到相似问题，直接返回缓存答案"}
        yield {"type": "cache_hit", "content": "缓存命中"}

        for char in cached_answer:
            yield {"type": "answer", "content": char}

        yield {"type": "done", "content": ""}
        return

    # 拼装并推送 thinking 事件到 SSE 流
    thinking_steps = [
        ("thinking", "正在分析问题意图..."),
        ("thinking", "正在混合检索知识库（语义搜索 + BM25 + Reranker）..."),
    ]
    for event_type, message in thinking_steps:
        yield {"type": event_type, "content": message}

    # Step 4: RAG 混合检索（Phase 5 增强版）
    docs = hybrid_search(question, top_k=5)

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

    full_answer = ""  # 收集完整答案用于缓存

    try:
        response = call_deepseek_chat(messages, stream=True)

        # 逐行解析 DeepSeek 返回的 SSE 流
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
                        full_answer += content
                except json.JSONDecodeError:
                    continue

    except Exception as e:
        yield {"type": "error", "content": f"AI 服务暂时不可用: {str(e)}"}
        return

    # Phase 6: 缓存本次答案
    if full_answer:
        store_cache(session_id, question, full_answer)

    # 推送引用来源
    yield {"type": "sources", "sources": list(set(doc["source"] for doc in docs))}
    yield {"type": "done", "content": ""}


def ask_with_agent(question: str, session_id: str = "default"):
    """
    带 Agent 决策的问答 — Phase 3 Agent + Phase 4 记忆

    完整流程:
      1. 加载对话历史（摘要 + 最近原文）
      2. 拼入 Agent 输入 → Agent 带着"记忆"理解问题
      3. Agent ReAct 循环（Thought→Action→Observation→...→Final Answer）
      4. 保存本轮 Q&A 到对话历史
      5. 检查是否需要摘要压缩（超阈值即压缩旧消息）
      6. 推送答案 + 工具过程

    面试重点：步骤 1-5 构成了完整的 Agent 记忆系统
    """
    from services.agent_service import get_agent, invoke_agent_with_progress
    from services.memory_service import (
        add_message, build_context, has_history,
        should_compress, compress_history, get_history_token_usage,
    )
    from services.cache_service import check_cache, store_cache

    agent = get_agent()

    # ============================================
    # 第 0 步：检查语义缓存（Phase 6）
    # ============================================
    cached_answer = check_cache(session_id, question)
    if cached_answer:
        yield {"type": "thinking", "content": "检测到相似问题，直接返回缓存答案"}
        yield {"type": "cache_hit", "content": "缓存命中"}

        # 逐字符推送缓存答案（跟正常流程一致的流式体验）
        for char in cached_answer:
            yield {"type": "answer", "content": char}

        yield {"type": "done", "content": ""}
        return  # 直接返回，跳过 Agent 链路

    # ============================================
    # 第 1 步：加载对话记忆
    # ============================================
    yield {"type": "thinking", "content": "Agent 正在分析问题意图..."}

    if has_history(session_id):
        token_info = get_history_token_usage(session_id)
        yield {
            "type": "memory",
            "content": f"已加载对话上下文",
            "message_count": token_info["message_count"],
            "token_usage": token_info["percent"],
        }
        yield {"type": "thinking", "content": f"正在结合历史上下文分析（{token_info['message_count']} 条历史消息）..."}

    # 第 2 步：构建带记忆的 Agent 输入
    # build_context 把摘要 + 最近对话 + 当前问题拼成一个完整输入
    enriched_input = build_context(session_id, question)

    try:
        # ============================================
        # 第 3 步：Agent ReAct 循环（带进度推送）
        # ============================================
        # 原来 agent.invoke() 是阻塞调用，30-60秒内前端无反馈
        # invoke_agent_with_progress() 在后台线程跑 invoke，主线程轮询进度
        # 通过 LangChain callback 实时捕获 LLM token 和 tool call，前端看到实时反馈
        yield {"type": "thinking", "content": "Agent 启动完成，正在调用 LLM 推理（通常需要 30-60 秒）..."}

        # 用于收集工具调用事件（回调中已实时推送，这里记录以供 tool_end 统计）
        tool_call_count = 0

        # invoke_agent_with_progress 是一个生成器，逐个 yield 进度事件
        final_result = None
        for progress in invoke_agent_with_progress(agent, {"input": enriched_input}):
            ptype = progress.get("type", "")

            if ptype == "thinking":
                # 实时推理进度 → 前端展示"LLM 正在推理中（已生成 N token）"
                yield {"type": "thinking", "content": progress["content"]}

            elif ptype == "tool_call":
                # Agent 决定调用工具 → 推送工具调用事件
                tool_call_count += 1
                yield {
                    "type": "tool_call",
                    "tool": progress["tool"],
                    "input": progress["input"],
                }

            elif ptype == "tool_result":
                # 工具返回结果 → 推送检索结果
                obs = progress.get("content", "")
                yield {
                    "type": "tool_result",
                    "content": obs[:300] + ("..." if len(obs) > 300 else ""),
                }

            elif ptype == "result":
                # Agent invoke 完成 → 拿到最终结果
                final_result = progress["data"]

        # 最终结果校验
        if final_result is None:
            yield {"type": "error", "content": "Agent 执行失败：未返回结果"}
            return

        # 检查 Agent 执行过程中是否有错误（限流、网络等）
        agent_error = final_result.get("error", "")
        if agent_error:
            yield {"type": "error", "content": f"AI 服务暂时不可用: {agent_error}"}
            return

        answer = final_result.get("output", "")
        if not answer:
            yield {"type": "error", "content": "Agent 未生成有效回答，请稍后重试"}
            return

        # ============================================
        # 第 4 步：保存本轮对话到历史 + 缓存
        # ============================================
        add_message(session_id, "user", question)
        add_message(session_id, "assistant", answer)
        store_cache(session_id, question, answer)

        # ============================================
        # 第 5 步：检查是否需要摘要压缩
        # ============================================
        if should_compress(session_id):
            yield {"type": "thinking", "content": "对话历史较长，正在压缩早期记忆..."}

            compress_result = compress_history(session_id)
            yield {
                "type": "compressed",
                "compressed_count": compress_result.get("compressed_count", 0),
                "summary_length": compress_result.get("summary_length", 0),
            }

            if compress_result.get("error"):
                yield {"type": "thinking", "content": f"记忆压缩失败: {compress_result['error']}"}
            else:
                yield {"type": "thinking", "content": "记忆压缩完成，可以继续对话"}

        # ============================================
        # 第 6 步：推送工具调用总结 + 答案
        # ============================================

        # 推送工具调用总结
        if tool_call_count > 0:
            yield {"type": "tool_end",
                   "tool": "Agent 推理完成",
                   "result_count": tool_call_count,
                   "sources": []}

        # 推送 intermediate_steps 中的来源文档
        if "intermediate_steps" in final_result and final_result["intermediate_steps"]:
            sources = []
            for step in final_result["intermediate_steps"]:
                observation = step[1]  # 字符串，包含文档片段
                # 从 observation 里抽文档来源名（格式: [source: xxx.md]）
                for line in observation.split("\n"):
                    if "[source:" in line or "来源" in line:
                        sources.append(line.strip())
            if sources:
                yield {"type": "sources", "sources": sources}

        # 推送答案 — 逐字符流式
        yield {"type": "thinking", "content": "正在组织回答..."}

        for char in answer:
            yield {"type": "answer", "content": char}

        yield {"type": "done", "content": ""}

    except Exception as e:
        yield {"type": "error", "content": f"Agent 执行失败: {str(e)}"}
