"""
全局配置 — 所有可调参数集中在这里
面试时被问"你的参数怎么选的"，直接打开这个文件解释
"""
import os
from dotenv import load_dotenv

load_dotenv()  # 从 .env 文件加载环境变量

# === DeepSeek API ===
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_CHAT_MODEL = "deepseek-chat"
# Embedding 模型 — 本地 sentence-transformers，不需要 API Key
# all-MiniLM-L6-v2: 384维，~80MB，CPU友好，中文支持良好
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# === Chroma 向量数据库 ===
CHROMA_PERSIST_DIR = "./data/chroma_db"  # 持久化存储路径，重启不丢
CHROMA_COLLECTION_NAME = "tech_docs"     # 集合名，类似 MySQL 的表名

# === 文档切片 ===
CHUNK_SIZE = 500       # 每段最大字符数
CHUNK_OVERLAP = 50     # 相邻段重叠字符数，防止一句话被切断

# === 检索 ===
RETRIEVAL_INITIAL_TOP_K = 20   # 混合检索初召数量（给 Reranker 留余量）
RERANKER_TOP_K = 5             # Reranker 精排后保留数量
SIMILARITY_THRESHOLD = 0.7     # 低于此值的触发二次检索
LOW_CONFIDENCE_FALLBACK = True # 是否启用低置信度二次检索

# === 缓存 ===
CACHE_SIMILARITY_THRESHOLD = 0.95  # 相似度 > 此值视为同一问题，直接返回缓存
CACHE_MAX_SIZE = 100                # 每个 session 最多缓存 100 个问题

# === 对话记忆 ===
MAX_CONTEXT_TOKENS = 28000       # 上下文超此值触发摘要压缩
SUMMARY_TRIGGER_RATIO = 0.8      # 窗口用掉 80% 就触发压缩
RECENT_ROUNDS_KEPT = 5           # 压缩时保留最近 N 轮原文
MAX_MESSAGES_PER_SESSION = 200   # 每个 session 最多保留的消息数（防内存无限增长）
MAX_REACT_ITERATIONS = 5         # Agent 循环上限，防死循环
