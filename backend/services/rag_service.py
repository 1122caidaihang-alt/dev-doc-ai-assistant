"""
RAG 检索服务 — 问题 Embedding → Chroma 语义搜索 → 返回 Top-K 文档
这是检索链路的核心入口，后续 Phase 5 会加入 BM25 + Reranker + 二次检索
"""
from typing import List, Dict
import chromadb
from chromadb.config import Settings
from ingestion.indexer import get_embedding
from config import (
    CHROMA_PERSIST_DIR, CHROMA_COLLECTION_NAME,
    RETRIEVAL_INITIAL_TOP_K,
)


def search_documents(query: str, top_k: int = RETRIEVAL_INITIAL_TOP_K) -> List[Dict]:
    """
    语义搜索 — 把问题 Embedding，在 Chroma 里找最相似的文档

    参数:
        query: 用户问题（已查询重写后的）
        top_k: 返回数量

    返回:
        [{"id": "md5hash", "content": "文档片段...", "source": "xx.md", "similarity": 0.89}, ...]
    """
    # 1. 问题 → 向量（用本地 sentence-transformers 模型）
    query_embedding = get_embedding(query)

    # 2. 连接 Chroma
    client = chromadb.PersistentClient(
        path=CHROMA_PERSIST_DIR,
        settings=Settings(anonymized_telemetry=False),
    )
    collection = client.get_collection(name=CHROMA_COLLECTION_NAME)

    # 3. 搜索最相似的 top_k 条记录
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, collection.count()),  # 不超过总数
        include=["documents", "metadatas", "distances"],
    )

    # 4. 整理返回格式
    documents = []
    if results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            distance = results["distances"][0][i] if results["distances"] else 0
            # Chroma 默认用 cosine distance (0~2)
            # distance=0 表示完全相同, distance=2 表示完全相反
            # 转成 similarity = 1 - distance/2
            similarity = 1.0 - (distance / 2.0)

            documents.append({
                "id": doc_id,
                "content": results["documents"][0][i],
                "source": results["metadatas"][0][i].get("source", "unknown"),
                "similarity": round(similarity, 4),
            })

    return documents
