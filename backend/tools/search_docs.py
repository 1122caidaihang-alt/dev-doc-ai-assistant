"""
search_docs 工具 — 给 LangChain Agent 调用的文档搜索工具
Agent 通过 Function Calling 调用这个函数来搜索知识库

Phase 5：切换到混合检索（查询重写 + 语义搜索 + BM25 + Reranker）
"""
from services.rag_service import hybrid_search, search_documents
from logger import get_logger

logger = get_logger("search_docs")


def search_docs(query: str) -> str:
    """
    Agent 工具函数 — 搜索技术文档知识库（混合检索）

    参数:
        query: 搜索查询（Agent 从用户问题中提炼的关键词）

    返回:
        搜索结果文本，Agent 能直接读取并用于生成答案
    """
    try:
        # Agent 路径：关掉查询重写，开启 Reranker 精排
        # enable_rewrite=False → Agent（Function Calling）自己在 Thought 阶段提炼关键词，重写多余
        # enable_reranker=True  → DeepSeek 限额比 Kimi 高，Reranker 交叉精排提升结果质量
        results = hybrid_search(
            query, top_k=5,
            enable_rewrite=False,   # Agent 自己就是"改写器"
            enable_reranker=True,   # DeepSeek 限额够，精排提升质量
        )

        if not results:
            return "未在当前知识库中找到相关内容。建议：1) 换一种说法重试 2) 去 GitHub Issues 搜索 3) 提交新 Issue 询问"

        # 格式化成 Agent 容易理解的结构
        output_parts = [f"搜索 '{query}' 找到 {len(results)} 个相关文档片段:\n"]
        for i, doc in enumerate(results):
            rerank_info = ""
            if "_reranker_score" in doc:
                rerank_info = f", Reranker评分: {doc['_reranker_score']}"
            output_parts.append(
                f"[{i+1}] 来源: {doc['source']} (相似度: {doc['similarity']}{rerank_info})\n"
                f"内容: {doc['content'][:500]}\n"
            )

        return "\n".join(output_parts)

    except Exception as e:
        # 降级：混合检索失败时回退到纯语义搜索
        logger.warning(f"混合检索失败，降级到语义搜索: {e}")
        try:
            results = search_documents(query, top_k=5)
            if not results:
                return "未在当前知识库中找到相关内容。"
            output_parts = [f"搜索 '{query}' 找到 {len(results)} 个相关文档片段:\n"]
            for i, doc in enumerate(results):
                output_parts.append(
                    f"[{i+1}] 来源: {doc['source']} (相似度: {doc['similarity']})\n"
                    f"内容: {doc['content'][:500]}\n"
                )
            return "\n".join(output_parts)
        except Exception as e2:
            return f"文档搜索失败: {str(e2)}"
