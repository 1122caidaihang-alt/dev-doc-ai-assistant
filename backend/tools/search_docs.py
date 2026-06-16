"""
search_docs 工具 — 给 LangChain Agent 调用的文档搜索工具
Agent 通过 Function Calling 调用这个函数来搜索知识库
"""
from services.rag_service import search_documents


def search_docs(query: str) -> str:
    """
    Agent 工具函数 — 搜索技术文档知识库

    参数:
        query: 搜索查询（Agent 从用户问题中提炼的关键词）

    返回:
        搜索结果文本，Agent 能直接读取并用于生成答案
    """
    try:
        results = search_documents(query, top_k=5)

        if not results:
            return "未在当前知识库中找到相关内容。"

        # 格式化成 Agent 容易理解的结构
        output_parts = [f"搜索 '{query}' 找到 {len(results)} 个相关文档片段:\n"]
        for i, doc in enumerate(results):
            output_parts.append(
                f"[{i+1}] 来源: {doc['source']} (相似度: {doc['similarity']})\n"
                f"内容: {doc['content'][:500]}\n"
            )

        return "\n".join(output_parts)

    except Exception as e:
        return f"文档搜索失败: {str(e)}"
