"""
会话语义缓存 — 相似问题命中缓存 → 跳过完整检索链，直接返回答案

Phase 6：用户短时间内反复问同一个问题（或换说法问同一件事），
不重复调 Agent + RAG + LLM，直接用上一次的答案。

为什么是语义缓存而不是字符串匹配？
  "Redis缓存怎么配置" 和 "redis的cache怎么配" 字符串不同，但语义一致。
  用 Embedding 做近似匹配，cosine 相似度 > 0.95 判定为同一问题。

为什么不用 Redis？
  单实例部署，Python dict + Embedding 足够。
  Redis 多一个故障点，免费托管未必支持。

面试重点：
  语义缓存比关键词缓存命中率更高——"同一问题不同问法"是真实用户行为。
"""
from typing import Dict, List, Tuple, Optional
from ingestion.indexer import get_embedding
from config import CACHE_SIMILARITY_THRESHOLD, CACHE_MAX_SIZE
from logger import get_logger

logger = get_logger("cache")


# ============================================================
# 缓存存储 — session_id → [(question_embedding, question_text, answer_text), ...]
# ============================================================
# 用列表而非 dict —— 因为需要遍历所有缓存项算相似度，顺序遍历足够
# CACHE_MAX_SIZE=100，遍历 100 个 384 维向量 < 1ms
_cache: Dict[str, List[Tuple[List[float], str, str]]] = {}


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """两个向量的余弦相似度"""
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(a * a for a in vec1) ** 0.5
    norm2 = sum(b * b for b in vec2) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def check_cache(session_id: str, question: str) -> Optional[str]:
    """
    检查是否有语义相似的缓存问题

    参数:
        session_id: 会话 ID
        question: 当前用户问题

    返回:
        命中 → 缓存中的答案文本
        未命中 → None

    算法：
        1. 计算当前问题的 Embedding
        2. 遍历该 session 的所有缓存项，算余弦相似度
        3. 最高分 > CACHE_SIMILARITY_THRESHOLD → 命中
        4. 否则返回 None
    """
    if session_id not in _cache or not _cache[session_id]:
        return None

    try:
        question_emb = get_embedding(question)
    except Exception as e:
        logger.warning(f"Embedding 失败: {e}")
        return None

    best_score = 0.0
    best_answer = None

    for cached_emb, cached_q, cached_ans in _cache[session_id]:
        score = _cosine_similarity(question_emb, cached_emb)
        if score > best_score:
            best_score = score
            best_answer = cached_ans

    if best_score >= CACHE_SIMILARITY_THRESHOLD and best_answer:
        logger.info(f"命中! 相似度 {best_score:.3f} > {CACHE_SIMILARITY_THRESHOLD}")
        logger.info(f"  缓存问题: '{_cache[session_id][0][1][:60]}...'")
        return best_answer

    logger.info(f"未命中 (最高相似度 {best_score:.3f} < {CACHE_SIMILARITY_THRESHOLD})")
    return None


def store_cache(session_id: str, question: str, answer: str):
    """
    将问答对存入缓存

    参数:
        session_id: 会话 ID
        question: 用户问题
        answer: 助手回答

    缓存策略：
        - 存储 Embedding 向量（而非原文）以加速后续相似度计算
        - 超过 CACHE_MAX_SIZE 时移除最旧的条目（FIFO）
        - Embedding 失败时不缓存（静默跳过）
    """
    if not question or not answer:
        return

    try:
        question_emb = get_embedding(question)
    except Exception as e:
        logger.warning(f"缓存 Embedding 失败: {e}")
        return

    if session_id not in _cache:
        _cache[session_id] = []

    # 检查是否已有高度相似的缓存（去重）
    for i, (cached_emb, cached_q, _) in enumerate(_cache[session_id]):
        score = _cosine_similarity(question_emb, cached_emb)
        if score >= CACHE_SIMILARITY_THRESHOLD:
            # 已有相似缓存，更新为最新答案（覆盖旧答案）
            _cache[session_id][i] = (question_emb, question, answer)
            logger.info(f"已有相似缓存 (相似度 {score:.3f})，更新答案")
            return

    # 新增缓存项
    _cache[session_id].append((question_emb, question, answer))

    # 超过上限时移除最旧的
    while len(_cache[session_id]) > CACHE_MAX_SIZE:
        removed = _cache[session_id].pop(0)
        logger.info(f"超出上限，移除最旧缓存: '{removed[1][:50]}...'")

    logger.info(f"已缓存 (session={session_id[:8]}..., 当前 {len(_cache[session_id])} 条)")


def get_cache_stats(session_id: str) -> Dict:
    """
    返回 session 的缓存统计信息

    返回:
        {"cached_count": 缓存条目数, "max_size": 上限}
    """
    return {
        "cached_count": len(_cache.get(session_id, [])),
        "max_size": CACHE_MAX_SIZE,
    }


def clear_cache(session_id: str):
    """清除指定 session 的所有缓存"""
    if session_id in _cache:
        count = len(_cache[session_id])
        del _cache[session_id]
        logger.info(f"已清除 session {session_id[:8]}... 的 {count} 条缓存")
