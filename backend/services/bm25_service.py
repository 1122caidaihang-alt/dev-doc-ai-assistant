"""
BM25 关键词检索服务 — 纯关键词匹配，弥补语义搜索对专有名词的盲区

Phase 5 Step B2：跟 Chroma 语义搜索并行执行，双路召回

为什么需要 BM25？
  Embedding 模型（all-MiniLM-L6-v2）对专有名词不敏感——
  "@PreAuthorize" 和 "权限注解" 语义上可能很接近，但 "@PreAuthorize"
  这个字符串本身在 Embedding 空间里可能没有很好的表示。
  BM25 直接做字符串匹配，精确命中专有名词。

为什么从 Chroma 加载文档？
  不需要额外存储，Chroma 已经是 source of truth。
  BM25 索引在每次 /ingest 后需要重建（或者首次搜索时懒加载）。

面试重点：
  双路召回 = 语义搜索（覆盖面）+ 关键词搜索（精确度）
  各取 top-10 → 合并去重 → 给 Reranker 精排
"""
from typing import List, Dict, Optional
import chromadb
from chromadb.config import Settings
from rank_bm25 import BM25Okapi
from config import CHROMA_PERSIST_DIR, CHROMA_COLLECTION_NAME
from logger import get_logger

logger = get_logger("bm25")


def _tokenize(text: str) -> List[str]:
    """
    中文分词 — 字符级分词 + 英文/数字保持连续

    BM25 需要 token 列表作为输入。对中文来说最可靠的做法是字符级分词——
    每个汉字一个 token，英文单词和数字保持连续。

    为什么不用 jieba？
      零依赖原则。字符级分词对 BM25 来说完全够用——
      专有名词如 "@PreAuthorize" 保持连续作为一个 token，
      中文如 "数据库连接池" 拆成 ["数","据","库","连","接","池"]
      虽不完美但实际效果可以——BM25 的 IDF 会对常见字降权。

    对比：如果用 jieba，"数据库连接池" → ["数据库", "连接池"]
    更好但多一个依赖。后续可以替换。
    """
    tokens = []
    current = ""

    for char in text:
        if char.isalnum() or char in "@._-:;#$%":
            # 英文/数字/特殊符号保持连续（如 @PreAuthorize, spring.cache）
            current += char
        else:
            if current:
                tokens.append(current.lower())
                current = ""
            if not char.isspace():
                # 中文字符、标点等每个单独作为 token
                tokens.append(char)
    if current:
        tokens.append(current.lower())

    return tokens


class BM25Retriever:
    """
    BM25 关键词检索器

    使用方式：
        retriever = BM25Retriever()
        retriever.build_index()  # 从 Chroma 加载全量文档建索引
        results = retriever.search("Redis 缓存配置", top_k=10)

    索引在内存中，服务重启后需要重建（首次搜索时自动触发）。
    """

    def __init__(self):
        self.corpus: List[str] = []          # 文档原文列表
        self.metadatas: List[Dict] = []      # 对应的 Chroma 元数据
        self.doc_ids: List[str] = []         # 对应的 Chroma doc id
        self.bm25: Optional[BM25Okapi] = None    # rank_bm25 索引实例
        self._built = False

    def build_index(self):
        """
        从 Chroma 拉全量文档，分词后建 BM25 索引

        调用时机：
          - 服务启动后首次搜索
          - /ingest 后手动调 rebuild
        """
        logger.info("正在从 Chroma 加载文档建 BM25 索引...")

        client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
        collection = client.get_collection(name=CHROMA_COLLECTION_NAME)

        # 拉全量文档（带上 metadata 和 id）
        all_data = collection.get(include=["documents", "metadatas"])

        self.corpus = []
        self.metadatas = []
        self.doc_ids = []
        tokenized_corpus = []

        if all_data["ids"]:
            for i, doc_id in enumerate(all_data["ids"]):
                content = all_data["documents"][i] or ""
                metadata = all_data["metadatas"][i] or {}

                if not content.strip():
                    continue

                self.corpus.append(content)
                self.metadatas.append(metadata)
                self.doc_ids.append(doc_id)

                # BM25 需要 token 化的文档
                tokenized_corpus.append(_tokenize(content))

        if tokenized_corpus:
            self.bm25 = BM25Okapi(tokenized_corpus)
            logger.info(f"索引构建完成: {len(tokenized_corpus)} 个文档")
        else:
            logger.warning("Chroma 中没有文档，BM25 索引为空")

        self._built = True

    def _ensure_index(self):
        """懒加载：首次搜索时自动建索引"""
        if not self._built:
            self.build_index()

    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        """
        BM25 关键词搜索

        参数:
            query: 搜索关键词（已查询重写后的）
            top_k: 返回数量

        返回:
            跟 search_documents() 同格式：
            [{"id": "md5hash", "content": "...", "source": "xx.md", "similarity": 0.89}, ...]

        注意：BM25 评分范围不是 0~1，这里做归一化处理让分数字面上
        跟 semantic 的 similarity 可比（虽然数值含义不同，合在一起后由 Reranker 统一打分）。
        """
        self._ensure_index()

        if not self.bm25 or not self.corpus:
            return []

        # 分词
        tokenized_query = _tokenize(query)

        # BM25 打分 — 返回每个文档的分数（越高越相关）
        scores = self.bm25.get_scores(tokenized_query)

        # 按分数排序，取 top_k
        # 创建 (index, score) 列表，按 score 降序排列
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        top_indices = ranked[:min(top_k, len(ranked))]

        results = []
        for idx, score in top_indices:
            if score <= 0:
                continue  # 跳过完全不匹配的

            # BM25 分数归一化到 0~1 区间
            # 用 scores 最大值做归一化（避免不同查询的分数不可比）
            max_score = scores.max() if hasattr(scores, 'max') else max(scores) if len(scores) > 0 else 1
            normalized_score = round(float(score) / float(max_score), 4) if max_score > 0 else 0.0

            results.append({
                "id": self.doc_ids[idx],
                "content": self.corpus[idx],
                "source": self.metadatas[idx].get("source", "unknown"),
                "similarity": normalized_score,  # 归一化后的 BM25 分数
                "_bm25_raw_score": float(score),  # 保留原始分数用于调试
            })

        return results


# ============================================================
# 全局单例 — 避免每次搜索都重建 BM25 索引
# ============================================================
_bm25_instance: Optional[BM25Retriever] = None


def get_bm25_retriever() -> BM25Retriever:
    """
    获取全局 BM25Retriever 单例

    首次调用时自动从 Chroma 加载文档建索引。
    后续 /ingest 后需要手动调 retriever.build_index() 重建。
    """
    global _bm25_instance
    if _bm25_instance is None:
        _bm25_instance = BM25Retriever()
        _bm25_instance.build_index()
    return _bm25_instance


def rebuild_bm25_index():
    """/ingest 后调用 — 重建 BM25 索引"""
    global _bm25_instance
    if _bm25_instance:
        _bm25_instance.build_index()
    else:
        _bm25_instance = BM25Retriever()
        _bm25_instance.build_index()
