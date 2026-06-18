"""
查询重写服务 — 把用户口语化问题转成更适合搜索的关键词

Phase 5 Step A：在检索前调用，提高 Embedding 匹配精度

面试重点：
  不是简单传原始问题，而是先让 LLM 提炼关键词再搜索。
  对比：直接搜"redis那个缓存怎么配啊" vs 搜"Redis 缓存配置 spring.cache"
  Embedding 模型对关键词的向量表示更精确，对口语噪音敏感。
"""
import httpx
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_CHAT_MODEL
from logger import get_logger

logger = get_logger("rewriter")


# 重写 Prompt — 让 DeepSeek 把口语问题转成搜索关键词
REWRITE_PROMPT = """你是一个搜索关键词提取器。把用户的技术问题转成适合搜索文档的关键词短语。

规则：
1. 只输出关键词短语，不要回答问题，不要解释
2. 保留专有名词（类名、注解名、配置项名）原样
3. 技术术语用中英文混合形式（如 "Redis 缓存" 而非 "redis 缓存"）
4. 去除口语词（"怎么"、"那个"、"啊"、"呢"、"一下"）
5. 输出长度控制在 30 字以内

示例：
用户: redis那个缓存怎么配啊
输出: Redis 缓存配置 spring.cache

用户: 多数据源读写分离怎么搞
输出: 多数据源 读写分离 spring.datasource.dynamic

用户: @PreAuthorize这个注解怎么用的
输出: @PreAuthorize Spring Security 权限注解

用户: {}
输出:"""


def rewrite_query(original_question: str) -> str:
    """
    用 DeepSeek 把口语化问题转成搜索关键词

    参数:
        original_question: 用户原始问题（可能口语化）

    返回:
        重写后的搜索关键词（如果失败，返回原始问题作为降级）

    调用时机：
        rag_service.search_documents() 内部，检索前自动调用
    """
    if not DEEPSEEK_API_KEY:
        # 没有 API Key 时直接返回原问题（降级）
        return original_question

    try:
        url = f"{DEEPSEEK_BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "model": DEEPSEEK_CHAT_MODEL,
            "messages": [{
                "role": "user",
                "content": REWRITE_PROMPT.format(original_question),
            }],
            "temperature": 0.1,   # 低温度 = 确定性输出，不做创造性改写
            "max_tokens": 50,     # 只要关键词，不需要长输出
        }

        response = httpx.post(url, headers=headers, json=body, timeout=10.0)
        response.raise_for_status()

        data = response.json()
        rewritten = data["choices"][0]["message"]["content"].strip()

        # 防御：如果 LLM 返回空或太长，用原始问题
        if not rewritten or len(rewritten) > 100:
            logger.warning(f"重写结果异常（len={len(rewritten)}），降级用原文")
            return original_question

        logger.info(f"查询重写: '{original_question}' → '{rewritten}'")
        return rewritten

    except Exception as e:
        logger.warning(f"查询重写失败: {e}，降级用原文")
        return original_question
