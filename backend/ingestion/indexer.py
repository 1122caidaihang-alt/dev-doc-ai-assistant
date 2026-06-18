"""
向量化索引器 — 把文档 chunk Embedding 后存入 Chroma
这是"离线索引"阶段的最后一步
"""
import time
import hashlib
import chromadb
from typing import List, Dict
from config import (
    EMBEDDING_MODEL, CHROMA_PERSIST_DIR, CHROMA_COLLECTION_NAME, HF_ENDPOINT,
)
from chromadb.config import Settings
from logger import get_logger

logger = get_logger("indexer")

# 全局单例 — 模型只加载一次，后续复用
_embedding_model = None
_model_lock = None  # 线程锁，懒初始化


def _get_model_lock():
    """懒初始化线程锁（避免 import 时创建）"""
    global _model_lock
    if _model_lock is None:
        import threading
        _model_lock = threading.Lock()
    return _model_lock


def get_embedding_model():
    """
    懒加载 sentence-transformers 模型（线程安全）
    第一次调用时下载模型（~80MB），之后走缓存
    通过 HF_ENDPOINT 环境变量控制镜像源（国内用 hf-mirror.com，国外不设）
    """
    global _embedding_model
    if _embedding_model is None:
        with _get_model_lock():
            # 双重检查：拿到锁后再确认一次，防止等锁期间别的线程已加载完
            if _embedding_model is not None:
                return _embedding_model
            import os
            if HF_ENDPOINT:
                os.environ["HF_ENDPOINT"] = HF_ENDPOINT
            from sentence_transformers import SentenceTransformer
            effective_endpoint = HF_ENDPOINT or "huggingface.co（默认）"
            logger.info(f"正在加载模型 {EMBEDDING_MODEL}（{effective_endpoint}）...")
            _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
            logger.info("模型加载完成")
    return _embedding_model


def get_embedding(text: str) -> List[float]:
    """
    用本地 sentence-transformers 模型把文字转成向量
    返回 384 个 float 的列表（all-MiniLM-L6-v2 的输出维度）

    这是整个 RAG 系统最基础的操作 — 文字 → 向量
    不需要 API Key，不需要网络，本地 CPU 即可运行
    """
    model = get_embedding_model()
    # encode() 返回 numpy array，转成 Python list
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


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
                logger.info(f"进度: {i+1}/{total}")

        except Exception as e:
            logger.error(f"索引 {chunk['id']} 失败: {e}")
            continue

    elapsed = time.time() - start_time
    logger.info(f"索引完成: {indexed_count} 个 chunk, 耗时 {elapsed:.1f}s")
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
