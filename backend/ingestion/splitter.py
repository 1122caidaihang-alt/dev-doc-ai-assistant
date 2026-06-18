"""
文本切片器 — 把长文档切成固定大小的 chunk
每个 chunk 是 Chroma 里的一条记录
"""
from typing import List, Dict
from config import CHUNK_SIZE, CHUNK_OVERLAP
from logger import get_logger

logger = get_logger("splitter")


def split_text(text: str, chunk_size: int = CHUNK_SIZE,
               overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    把一段长文本切成多个 chunk，相邻 chunk 有重叠
    重叠的目的是防止一句话刚好被切在两段之间，语义丢失

    例如：chunk_size=500, overlap=50
    第1段：字符 0-500
    第2段：字符 450-950   ← 跟第1段重叠 50 个字符
    第3段：字符 900-1400  ← 跟第2段重叠 50 个字符
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start += (chunk_size - overlap)  # 下一次起点 = 当前起点 + (块大小 - 重叠)
    return chunks


def split_documents(documents: List[Dict[str, str]],
                    chunk_size: int = CHUNK_SIZE,
                    overlap: int = CHUNK_OVERLAP) -> List[Dict[str, str]]:
    """
    对所有文档逐一切片，返回所有 chunk
    每个 chunk 带上来源文件名和序号，便于追溯
    """
    all_chunks = []
    for doc in documents:
        text = doc["content"]
        filename = doc["filename"]

        # 跳过空文件
        if not text.strip():
            continue

        chunks = split_text(text, chunk_size=chunk_size, overlap=overlap)
        for i, chunk in enumerate(chunks):
            all_chunks.append({
                "id": f"{filename}#chunk_{i}",          # 唯一 ID，用于去重
                "source": filename,                      # 来源文件
                "chunk_index": i,                        # 在原文中的序号
                "content": chunk,
            })

    logger.info(f"切片完成: {len(documents)} 份文档 → {len(all_chunks)} 个 chunk")
    return all_chunks
