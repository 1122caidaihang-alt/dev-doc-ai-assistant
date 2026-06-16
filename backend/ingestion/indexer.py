"""
向量化索引器 — 把文档 chunk Embedding 后存入 Chroma
这是"离线索引"阶段的最后一步
"""
import time
import hashlib
import httpx
import chromadb
from typing import List, Dict
from config import (
    KIMI_API_KEY, KIMI_BASE_URL, KIMI_EMBEDDING_MODEL,
    CHROMA_PERSIST_DIR, CHROMA_COLLECTION_NAME,
)
from chromadb.config import Settings


def get_embedding(text: str) -> List[float]:
    """
    调 Kimi Embedding API，把文字转成向量
    返回 1024 个 float 的列表

    这是整个 RAG 系统最基础的操作 — 文字 → 向量
    """
    if not KIMI_API_KEY or KIMI_API_KEY == "sk-your-key-here":
        raise RuntimeError("KIMI_API_KEY 未设置，请在 backend/.env 文件中配置真实的 API Key")

    url = f"{KIMI_BASE_URL}/embeddings"
    headers = {
        "Authorization": f"Bearer {KIMI_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": KIMI_EMBEDDING_MODEL,
        "input": text,
    }

    try:
        response = httpx.post(url, headers=headers, json=body, timeout=30.0)
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]
    except httpx.HTTPError as e:
        raise RuntimeError(f"Embedding API 调用失败: {e}")


def compute_md5_id(text: str) -> str:
    """
    计算文本的 MD5 哈希值作为文档 ID
    同一段内容永远产生相同的 ID → 用于去重
    """
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def build_index(chunks: List[Dict[str, str]]) -> int:
    """
    对所有 chunk 做 Embedding 并存入 Chroma

    参数:
        chunks: 切片器输出的 chunk 列表
    返回:
        入库的 chunk 数量
    """
    start_time = time.time()

    # 连接 Chroma（持久化模式，数据存硬盘）
    client = chromadb.PersistentClient(
        path=CHROMA_PERSIST_DIR,
        settings=Settings(anonymized_telemetry=False),
    )

    # 获取或创建 collection（类似 MySQL 的 CREATE TABLE IF NOT EXISTS）
    collection = client.get_or_create_collection(name=CHROMA_COLLECTION_NAME)

    indexed_count = 0
    total = len(chunks)

    for i, chunk in enumerate(chunks):
        try:
            # 1. 调 Embedding API 得到向量
            embedding = get_embedding(chunk["content"])

            # 2. 生成唯一 ID
            doc_id = compute_md5_id(chunk["content"])

            # 3. 存入 Chroma
            # embeddings: 向量数组
            # documents: 原文（Chroma 会一起存，搜的时候直接返回）
            # metadatas: 附加信息（来源文件名、序号）
            # ids: 唯一标识符
            collection.add(
                embeddings=[embedding],
                documents=[chunk["content"]],
                metadatas=[{
                    "source": chunk["source"],
                    "chunk_index": chunk["chunk_index"],
                }],
                ids=[doc_id],
            )
            indexed_count += 1

            if (i + 1) % 10 == 0:
                print(f"[indexer] 进度: {i+1}/{total}")

        except Exception as e:
            print(f"[indexer] 索引 {chunk['id']} 失败: {e}")
            continue

    elapsed = time.time() - start_time
    print(f"[indexer] 索引完成: {indexed_count} 个 chunk, 耗时 {elapsed:.1f}s")
    return indexed_count


def get_collection_stats():
    """返回当前 Chroma collection 的统计信息"""
    try:
        client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
        collection = client.get_collection(name=CHROMA_COLLECTION_NAME)
        return {"count": collection.count()}
    except Exception:
        return {"count": 0}
