"""
Reranker 重排序服务 — 多路召回后的精排

Phase 5 Step C：把 semantic + BM25 的结果合并去重，用 DeepSeek 成对打分

为什么需要 Reranker？
  - Cosine similarity = (query, doc) 各自独立的向量距离
  - Cross-encoder = (query, doc) 成对理解，能判断"文档回答了多少问题"
  - 例：cosine 可能给"Redis 概述"打 0.85，给"Redis 配置详解"打 0.78
         Reranker 会把后者排到前面，因为它更直接回答"怎么配置"

为什么用 DeepSeek 而不是 BGE Reranker？
  初版不引入新模型/新依赖。DeepSeek 的交叉打分能力足以覆盖初期需求。
  后续可切到 BGE Reranker（开源免费、延迟更低）但需要下载模型（~1GB）。

面试重点：
  Reranker 做精排——初召各自独立打分粗糙，Reranker 成对比较更准。
"""
import json
import httpx
from typing import List, Dict, Optional
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_CHAT_MODEL, RERANKER_TOP_K
from logger import get_logger

logger = get_logger("reranker")


# Reranker Prompt — 让 DeepSeek 对文档逐条打分
RERANK_PROMPT = """你是一个搜索质量评估专家。请根据用户问题，对下面的候选文档片段逐一打分。

打分规则（0~10 分）：
- 10 分：直接完整地回答了问题，包含具体配置/代码/步骤
- 7-9 分：部分回答或高度相关，但缺一些细节
- 4-6 分：低度相关，只有部分内容沾边
- 1-3 分：几乎不相关
- 0 分：完全不相关

输出格式：每行一个分数，格式为"序号: 分数 - 简短理由"
只输出打分结果，不要输出其他内容。

用户问题：{question}

候选文档：
{candidates}

打分结果："""


def rerank(
    question: str,
    candidates: List[Dict],
    top_k: int = RERANKER_TOP_K,
) -> List[Dict]:
    """
    对候选文档列表用 DeepSeek 交叉打分，按分数重排后取 top_k

    参数:
        question: 用户原始问题
        candidates: 合并去重后的候选文档列表
                    [{"id": "...", "content": "...", "source": "...", "similarity": 0.8}, ...]
        top_k: 精排后保留数量

    返回:
        按 Reranker 分数降序排列的前 top_k 个文档
        每个文档新增 "_reranker_score" 字段

    容错：
        - DeepSeek 调用失败 → 按 original similarity 排序返回（降级）
        - candidates 数量 ≤ top_k → 直接返回，不需要 Reranker
    """
    if not DEEPSEEK_API_KEY:
        # 没有 API Key → 按原始 similarity 降级排序
        logger.warning("无 API Key，按原始 similarity 排序（降级）")
        return sorted(candidates, key=lambda d: d.get("similarity", 0), reverse=True)[:top_k]

    if len(candidates) <= top_k:
        logger.info(f"候选数 ({len(candidates)}) <= top_k ({top_k})，跳过重排")
        return candidates

    try:
        # 1. 构造候选文档列表文本
        candidates_text = ""
        for i, doc in enumerate(candidates):
            # 截断每个候选的前 300 字，避免 Prompt 过长
            snippet = doc["content"][:300].replace("\n", " ")
            candidates_text += f"[{i+1}] 来源: {doc['source']} | 相似度: {doc.get('similarity', 0)}\n"
            candidates_text += f"    {snippet}\n\n"

        # 2. 调 DeepSeek 打分
        url = f"{DEEPSEEK_BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "model": DEEPSEEK_CHAT_MODEL,
            "messages": [{
                "role": "user",
                "content": RERANK_PROMPT.format(
                    question=question,
                    candidates=candidates_text,
                ),
            }],
            "temperature": 0.1,
            "max_tokens": 500,
        }

        response = httpx.post(url, headers=headers, json=body, timeout=30.0)
        response.raise_for_status()

        data = response.json()
        scores_text = data["choices"][0]["message"]["content"].strip()

        # 3. 解析分数
        # 格式：每行 "序号: 分数 - 理由"
        rerank_scores = _parse_scores(scores_text, len(candidates))

        # 4. 把分数写入每个候选文档
        for i, doc in enumerate(candidates):
            doc["_reranker_score"] = rerank_scores.get(i, 0)

        # 5. 按 Reranker 分数降序排列，取 top_k
        reranked = sorted(
            candidates,
            key=lambda d: d.get("_reranker_score", 0),
            reverse=True,
        )

        top = reranked[:top_k]
        avg_score = sum(d.get("_reranker_score", 0) for d in top) / len(top) if top else 0
        logger.info(f"重排完成: {len(candidates)} 候选 → top {len(top)}, 平均分 {avg_score:.1f}")

        return top

    except Exception as e:
        logger.warning(f"重排失败: {e}，按原始 similarity 降级排序")
        return sorted(candidates, key=lambda d: d.get("similarity", 0), reverse=True)[:top_k]


def _parse_scores(text: str, expected_count: int) -> Dict[int, float]:
    """
    解析 DeepSeek 返回的打分文本

    输入示例:
        "1: 8 - 直接回答了Redis配置"
        "2: 5 - 部分相关但不够具体"
        ...

    返回: {0: 8.0, 1: 5.0, ...}
    """
    scores: Dict[int, float] = {}

    import re
    # 匹配 "序号: 分数" 或 "序号: 分数 - 理由"
    pattern = r'(\d+)\s*[:：]\s*(\d+(?:\.\d+)?)'
    matches = re.findall(pattern, text)

    for match in matches:
        idx = int(match[0]) - 1  # 转为 0-based
        score = float(match[1])
        # 分数归一化到 0~1
        normalized = min(1.0, max(0.0, score / 10.0))
        scores[idx] = round(normalized, 4)

    # 如果解析结果太少（DeepSeek 可能没按格式输出），
    # 对缺失的候选给最低分的一半（给予基本存在感）
    if len(scores) < expected_count:
        default = 0.3
        for i in range(expected_count):
            if i not in scores:
                scores[i] = default

    return scores
