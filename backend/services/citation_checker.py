"""
引用核查服务 — 逐句比对 LLM 答案与检索文档，标注来源

Phase 5 Step E：RAG 应用最大的风险是 LLM 编造——
用户看到"根据文档，Redis 配置需要..."，但可能文档里根本没这句话。

引用核查做的事：
1. 把 LLM 答案按句拆分
2. 每句话做 Embedding
3. 跟所有检索到的文档做相似度比对
4. 相似度 > 阈值 → 找到来源，标注 [来源: xxx.md]
5. 相似度 < 阈值 → 没找到依据，标注 [推断]

面试重点：
  诚实标注——让用户知道哪句话来自文档、哪句话是 LLM 自由发挥。
  不做标注的话，用户无法区分"可靠信息"和"编造信息"。
"""
import re
from typing import List, Dict, Tuple
from ingestion.indexer import get_embedding
from logger import get_logger

logger = get_logger("citation")


# 引用匹配阈值：句子跟文档片段的相似度超过此值 → 认为有来源
CITATION_THRESHOLD = 0.75

# 最低置信度：句子跟所有文档的最高相似度都低于此值 → 完全无依据
MIN_CITATION_THRESHOLD = 0.50


def _split_sentences(text: str) -> List[str]:
    """
    把文本拆成句子

    中英文混排场景：用句号、问号、感叹号、换行作为分隔
    """
    # 预处理：Markdown 标题和列表符号保留，但在前面加换行
    text = re.sub(r'(\n#{1,6}\s)', r'\n\1', text)

    # 按句尾标点拆分
    sentences = re.split(r'(?<=[。！？\.\!\?\n])\s*', text)

    # 过滤空句和纯空白
    sentences = [s.strip() for s in sentences if s.strip()]
    return sentences


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """两个向量的余弦相似度"""
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(a * a for a in vec1) ** 0.5
    norm2 = sum(b * b for b in vec2) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def check_citations(
    answer: str,
    retrieved_docs: List[Dict],
    threshold: float = CITATION_THRESHOLD,
) -> str:
    """
    对 LLM 答案做引用核查，标注每句话的来源或推断

    参数:
        answer: LLM 生成的答案文本
        retrieved_docs: 检索到的文档列表
                        [{"id": "...", "content": "...", "source": "...", "similarity": 0.8}, ...]
        threshold: 判定"有来源"的相似度阈值

    返回:
        标注后的答案文本，每句末尾加 [来源: xx.md] 或 [推断]

    算法：
        for each 句子:
            句子 Embedding → 跟所有文档 chunk 的 Embedding 比余弦相似度
            取最高分 → 高于阈值 → 标 [来源]
                      → 低于阈值 → 标 [推断]

    时间复杂度：O(句子数 × 文档数 × 384维向量的余弦计算)
    对典型场景（5句 × 5文档 = 25次比对），在 CPU 上 < 50ms。
    """
    if not answer or not retrieved_docs:
        return answer

    # 1. 拆句
    sentences = _split_sentences(answer)

    # 2. 预计算所有文档 chunk 的 Embedding（避免重复计算）
    doc_embeddings: List[Tuple[Dict, List[float]]] = []
    for doc in retrieved_docs:
        try:
            emb = get_embedding(doc["content"])
            doc_embeddings.append((doc, emb))
        except Exception as e:
            logger.warning(f"Embedding 失败 for {doc.get('source', '?')}: {e}")

    if not doc_embeddings:
        return answer  # 全部 Embedding 失败，保留原答案

    # 3. 逐句比对
    annotated_parts = []
    for sentence in sentences:
        if len(sentence) < 5:
            # 太短的句子（如纯标点、序号）跳过
            annotated_parts.append(sentence)
            continue

        try:
            sent_emb = get_embedding(sentence)
        except Exception:
            annotated_parts.append(sentence)
            continue

        # 找最匹配的文档
        best_score = 0.0
        best_source = ""
        for doc, doc_emb in doc_embeddings:
            score = _cosine_similarity(sent_emb, doc_emb)
            if score > best_score:
                best_score = score
                best_source = doc.get("source", "unknown")

        # 4. 标注
        if best_score >= threshold:
            annotated_parts.append(f"{sentence} [来源: {best_source}]")
        elif best_score >= MIN_CITATION_THRESHOLD:
            # 中等置信度：可能是相关但非直接引用
            annotated_parts.append(f"{sentence} [推断: 近 {best_source} ({best_score:.0%})]")
        else:
            annotated_parts.append(f"{sentence} [推断]")

        logger.info(f"'{sentence[:50]}...' → {best_score:.2f} / {best_source}")

    return "\n\n".join(annotated_parts)


def get_citation_stats(answer: str, retrieved_docs: List[Dict]) -> Dict:
    """
    返回引用统计，不修改答案原文

    用于前端展示引用率（如 "12 句中有 8 句有来源，引用率 67%"）

    返回:
        {
            "total_sentences": 12,
            "cited_count": 8,
            "inferred_count": 3,
            "uncited_count": 1,
            "citation_rate": 0.67,
        }
    """
    if not answer or not retrieved_docs:
        return {"total_sentences": 0, "cited_count": 0, "inferred_count": 0,
                "uncited_count": 0, "citation_rate": 0.0}

    sentences = _split_sentences(answer)
    total = len(sentences)
    cited = 0
    inferred = 0
    uncited = 0

    # 预计算文档 Embedding
    doc_embeddings = []
    for doc in retrieved_docs:
        try:
            doc_embeddings.append((doc, get_embedding(doc["content"])))
        except Exception:
            pass

    if not doc_embeddings:
        return {"total_sentences": total, "cited_count": 0, "inferred_count": 0,
                "uncited_count": total, "citation_rate": 0.0}

    for sentence in sentences:
        if len(sentence) < 5:
            cited += 1  # 短句不计入推断
            continue

        try:
            sent_emb = get_embedding(sentence)
        except Exception:
            uncited += 1
            continue

        best_score = max(
            _cosine_similarity(sent_emb, doc_emb)
            for _, doc_emb in doc_embeddings
        )

        if best_score >= CITATION_THRESHOLD:
            cited += 1
        elif best_score >= MIN_CITATION_THRESHOLD:
            inferred += 1
        else:
            uncited += 1

    return {
        "total_sentences": total,
        "cited_count": cited,
        "inferred_count": inferred,
        "uncited_count": uncited,
        "citation_rate": round(cited / total, 2) if total > 0 else 0.0,
    }
