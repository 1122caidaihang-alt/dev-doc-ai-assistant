"""
向量化索引器 — 把文档 chunk Embedding 后存入 Chroma
这是"离线索引"阶段的最后一步

Embedding 推理使用 ONNX Runtime（~15MB），不依赖 PyTorch。
Render 免费版 512MB 内存下可正常运行。
"""
import time
import hashlib
import numpy as np
import chromadb
from typing import List, Dict
from config import (
    EMBEDDING_MODEL, EMBEDDING_MODEL_ONNX, CHROMA_PERSIST_DIR, CHROMA_COLLECTION_NAME,
)
from chromadb.config import Settings
from logger import get_logger

logger = get_logger("indexer")

# 全局单例 — ONNX 模型和分词器只加载一次
_embedding_session = None
_tokenizer = None
_model_lock = None  # 线程锁，懒初始化
_model_ready = False  # 模型就绪信号

def _get_model_lock():
    """懒初始化线程锁"""
    global _model_lock
    if _model_lock is None:
        import threading
        _model_lock = threading.Lock()
    return _model_lock

def is_model_ready() -> bool:
    """模型是否已加载完成"""
    return _model_ready

def _set_model_ready():
    """标记模型就绪"""
    global _model_ready
    _model_ready = True


def get_embedding_model():
    """
    懒加载 ONNX Runtime 推理会话 + 分词器（线程安全）

    替代 sentence-transformers (PyTorch ~400MB)，
    用 ONNX Runtime (~15MB) + tokenizers (~1MB) 做同样的事。
    """
    global _embedding_session, _tokenizer
    if _embedding_session is None:
        with _get_model_lock():
            if _embedding_session is not None:
                return _embedding_session, _tokenizer

            import onnxruntime as ort
            from tokenizers import Tokenizer

            logger.info(f"加载 ONNX 模型: {EMBEDDING_MODEL_ONNX}...")
            model_path = f"{EMBEDDING_MODEL_ONNX}/model.onnx"
            _embedding_session = ort.InferenceSession(
                model_path,
                providers=['CPUExecutionProvider'],
            )

            logger.info("加载分词器...")
            _tokenizer = Tokenizer.from_file(f"{EMBEDDING_MODEL_ONNX}/tokenizer.json")

            global _model_ready
            _model_ready = True
            logger.info("ONNX 模型 + 分词器加载完成")

    return _embedding_session, _tokenizer


def get_embedding(text: str) -> List[float]:
    """
    用 ONNX Runtime 把文字转成向量（384 维）

    流程：分词 → ONNX 推理 → mean pooling → L2 归一化
    完全替代 sentence-transformers 的 model.encode()
    """
    session, tokenizer = get_embedding_model()

    # 1. 分词（padding 到合理长度，截断超长文本）
    encoded = tokenizer.encode(text)
    max_len = 512
    input_ids = encoded.ids[:max_len]
    attention_mask = [1] * len(input_ids)

    # Padding 到 max_len
    seq_len = len(input_ids)
    if seq_len < max_len:
        input_ids = input_ids + [0] * (max_len - seq_len)
        attention_mask = attention_mask + [0] * (max_len - seq_len)

    # 2. ONNX 推理
    inputs = {
        "input_ids": np.array([input_ids], dtype=np.int64),
        "attention_mask": np.array([attention_mask], dtype=np.int64),
    }
    outputs = session.run(None, inputs)
    token_embeddings = outputs[0]  # shape: [1, seq_len, 384]

    # 3. Mean pooling — 用 attention_mask 对有效 token 取平均
    attention_mask_np = np.array(attention_mask, dtype=np.float32)
    mask_expanded = np.expand_dims(attention_mask_np, axis=-1)  # [seq_len, 1]
    token_embeddings = token_embeddings[0]  # [seq_len, 384]
    summed = (token_embeddings * mask_expanded).sum(axis=0)  # [384]
    count = mask_expanded.sum()
    if count > 0:
        summed = summed / count

    # 4. L2 归一化（跟 sentence-transformers normalize_embeddings=True 一致）
    norm = np.linalg.norm(summed)
    if norm > 0:
        summed = summed / norm

    return summed.tolist()


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
