"""
Pydantic 数据模型 — 定义请求和响应的"形状"
FastAPI 用这些模型自动做数据校验和 JSON 序列化
"""
from pydantic import BaseModel


class ChatRequest(BaseModel):
    """POST /chat 的请求体"""
    question: str
    session_id: str = "default"


class IngestRequest(BaseModel):
    """POST /ingest 的请求体"""
    doc_path: str = "./data/docs/ruoyi-vue-pro/"


class IngestResponse(BaseModel):
    """POST /ingest 的响应体"""
    status: str
    chunks_indexed: int
    elapsed_seconds: float


class HealthResponse(BaseModel):
    """GET /health 的响应体"""
    status: str
    chroma: str = "unknown"
    deepseek_api: str = "unknown"
    indexed_docs: int = 0
