"""
RAG 检索服务 — 混合检索统一入口

Phase 5：在原始语义搜索基础上，加入查询重写 + BM25 + Reranker + 二次检索

流水线：
  用户问题 → 查询重写(A) → 语义搜索(B1) + BM25(B2) → 合并去重
  → Reranker 精排(C) → 低置信度二次检索(D) → 返回 top_k

调用方式：
  docs = hybrid_search("Redis缓存怎么配置")  # 推荐，包含全部增强
  docs = search_documents("Redis缓存怎么配置")  # 降级方案，纯语义搜索
"""
from typing import List, Dict
import chromadb
from chromadb.config import Settings
from ingestion.indexer import get_embedding
from services.query_rewriter import rewrite_query
from services.bm25_service import get_bm25_retriever
from services.reranker import rerank
from config import (
    CHROMA_PERSIST_DIR, CHROMA_COLLECTION_NAME,
    RETRIEVAL_INITIAL_TOP_K, RERANKER_TOP_K,
    SIMILARITY_THRESHOLD, LOW_CONFIDENCE_FALLBACK,
)
from logger import get_logger

logger = get_logger("rag")


def search_documents(query: str, top_k: int = RETRIEVAL_INITIAL_TOP_K) -> List[Dict]:
    """
    纯语义搜索 — 保留作为降级方案和 hybrid_search 的内部调用

    参数:
        query: 用户问题（已查询重写后的）
        top_k: 返回数量

    返回:
        [{"id": "md5hash", "content": "...", "source": "xx.md", "similarity": 0.89}, ...]
    """
    query_embedding = get_embedding(query)

    client = chromadb.PersistentClient(
        path=CHROMA_PERSIST_DIR,
        settings=Settings(anonymized_telemetry=False),
    )
    collection = client.get_collection(name=CHROMA_COLLECTION_NAME)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    documents = []
    if results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            distance = results["distances"][0][i] if results["distances"] else 0
            similarity = 1.0 - (distance / 2.0)

            documents.append({
                "id": doc_id,
                "content": results["documents"][0][i],
                "source": results["metadatas"][0][i].get("source", "unknown"),
                "similarity": round(similarity, 4),
            })

    return documents


def _deduplicate_by_id(docs: List[Dict]) -> List[Dict]:
    """按 id 去重，保留第一次出现的（语义搜索的 similarity 通常更可靠）"""
    seen = set()
    unique = []
    for doc in docs:
        if doc["id"] not in seen:
            seen.add(doc["id"])
            unique.append(doc)
    return unique


def _generate_alt_queries(question: str) -> List[str]:
    """
    用 LLM 生成替代查询词（低置信度二次检索用）

    当首次检索结果分数都偏低时，换个说法重新搜。
    """
    try:
        import httpx
        from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_CHAT_MODEL

        if not DEEPSEEK_API_KEY:
            return []

        prompt = f"""请为以下技术问题生成 2 个不同的搜索关键词，帮助在文档中查找答案。
每个关键词用不同角度描述同一问题。直接输出关键词，每行一个，不要解释。

原始问题: {question}
替代关键词:"""

        url = f"{DEEPSEEK_BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "model": DEEPSEEK_CHAT_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 80,
        }

        response = httpx.post(url, headers=headers, json=body, timeout=15.0)
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"].strip()

        # 按行拆分，过滤空行
        queries = [q.strip() for q in text.split("\n") if q.strip()]
        # 只取前 2 个（节约 API 调用）
        return queries[:2]

    except Exception as e:
        logger.warning(f"生成替代查询失败: {e}")
        return []


def hybrid_search(
    question: str,
    top_k: int = RERANKER_TOP_K,
    enable_rewrite: bool = True,
    enable_bm25: bool = True,
    enable_reranker: bool = True,
    enable_fallback: bool = True,
) -> List[Dict]:
    """
    混合检索统一入口 — 整合所有 Phase 5 增强

    流程:
      1. 查询重写 (A)：把口语问题转成搜索关键词
      2. 双路召回 (B1+B2)：语义搜索 + BM25 关键词搜索（并行概念）
      3. 合并去重
      4. Reranker 精排 (C)：用 DeepSeek 成对打分，取 top_k
      5. 低置信度二次检索 (D)：最高分 < 阈值 → 换说法重搜

    参数:
        question: 用户原始问题
        top_k: 最终返回的文档数量
        enable_*: 各阶段的开关（调试/RAGAS 评测时方便逐个关掉做消融实验）

    返回:
        [{"id", "content", "source", "similarity", "_reranker_score"}, ...]

    面试重点：消融实验 — 可以逐个关掉组件看每个贡献多少
    """
    # ============================================================
    # Step A: 查询重写
    # ============================================================
    search_query = question
    if enable_rewrite:
        search_query = rewrite_query(question)
        logger.info(f"原始问题: '{question}' → 搜索关键词: '{search_query}'")

    # ============================================================
    # Step B1: 语义搜索
    # ============================================================
    # RETRIEVAL_INITIAL_TOP_K=20 给 Reranker 留余量
    semantic_docs = search_documents(search_query, top_k=RETRIEVAL_INITIAL_TOP_K)
    logger.info(f"语义搜索: {len(semantic_docs)} 条")

    # ============================================================
    # Step B2: BM25 关键词搜索
    # ============================================================
    bm25_docs = []
    if enable_bm25:
        try:
            bm25 = get_bm25_retriever()
            bm25_docs = bm25.search(search_query, top_k=RETRIEVAL_INITIAL_TOP_K)
            logger.info(f"BM25 搜索: {len(bm25_docs)} 条")
        except Exception as e:
            logger.warning(f"BM25 搜索失败（降级跳过）: {e}")

    # ============================================================
    # 合并去重
    # ============================================================
    all_candidates = _deduplicate_by_id(semantic_docs + bm25_docs)
    logger.info(f"合并去重后: {len(all_candidates)} 条候选")

    if not all_candidates:
        logger.warning("无搜索结果")
        return []

    # ============================================================
    # Step C: Reranker 精排
    # ============================================================
    if enable_reranker and len(all_candidates) > top_k:
        all_candidates = rerank(question, all_candidates, top_k=top_k)
        logger.info(f"Reranker 精排后: {len(all_candidates)} 条")
    else:
        # 不启用 Reranker 时按 similarity 排序
        all_candidates = sorted(
            all_candidates,
            key=lambda d: d.get("similarity", 0),
            reverse=True,
        )[:top_k]

    best_score = all_candidates[0].get("similarity", 0) if all_candidates else 0

    # ============================================================
    # Step D: 低置信度二次检索
    # ============================================================
    if enable_fallback and LOW_CONFIDENCE_FALLBACK and best_score < SIMILARITY_THRESHOLD:
        logger.info(f"最高相似度 {best_score:.2f} < 阈值 {SIMILARITY_THRESHOLD}，触发二次检索")

        alt_queries = _generate_alt_queries(question)
        if alt_queries:
            alt_docs = []
            for alt_q in alt_queries:
                logger.info(f"替代查询: '{alt_q}'")
                alt_semantic = search_documents(alt_q, top_k=RETRIEVAL_INITIAL_TOP_K)
                alt_docs.extend(alt_semantic)

            if alt_docs:
                # 合并所有结果，重新 Reranker
                fallback_candidates = _deduplicate_by_id(all_candidates + alt_docs)
                all_candidates = rerank(question, fallback_candidates, top_k=top_k)
                new_best = all_candidates[0].get("similarity", 0) if all_candidates else 0
                logger.info(f"二次检索后: {len(all_candidates)} 条, 最高分 {new_best:.2f}")
            else:
                logger.warning("替代查询生成失败，用原结果")
        else:
            logger.info("无法生成替代查询，用原结果")

    return all_candidates
