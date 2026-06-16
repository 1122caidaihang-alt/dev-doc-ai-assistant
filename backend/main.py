"""
FastAPI 入口 — 整个后端的启动文件
运行命令: uvicorn main:app --reload --port 8000
"""
import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from models.schemas import IngestRequest, IngestResponse, HealthResponse, ChatRequest
from ingestion.loader import load_documents
from ingestion.splitter import split_documents
from ingestion.indexer import build_index, get_collection_stats
from services.chat_service import ask
from config import CHUNK_SIZE, CHUNK_OVERLAP, KIMI_API_KEY

app = FastAPI(title="开发者文档 AI 知识助手", version="0.1.0")

# CORS 跨域配置 — 前端 Vercel 调后端 Railway 需要这个
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查接口 — 确认后端和 Chroma 状态"""
    stats = get_collection_stats()
    return {
        "status": "ok",
        "chroma": "connected" if stats["count"] > 0 else "empty",
        "kimi_api": "configured" if KIMI_API_KEY and KIMI_API_KEY != "sk-your-key-here" else "missing_key",
        "indexed_docs": stats["count"],
    }


@app.post("/ingest", response_model=IngestResponse)
async def ingest_docs(request: IngestRequest):
    """
    知识库导入接口 — 扫描目录 → 切片 → Embedding → 入库
    手动调用一次即可，更新文档后重新调用重建索引
    """
    import time
    start = time.time()

    try:
        # 1. 加载文档
        docs = load_documents(request.doc_path)
        if not docs:
            return {"status": "error", "chunks_indexed": 0, "elapsed_seconds": 0}

        # 2. 切片
        chunks = split_documents(docs, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)

        # 3. 向量化 + 入库
        count = build_index(chunks)

        elapsed = time.time() - start
        return {
            "status": "completed",
            "chunks_indexed": count,
            "elapsed_seconds": round(elapsed, 1),
        }
    except Exception as e:
        return {
            "status": "error",
            "chunks_indexed": 0,
            "elapsed_seconds": 0,
        }


@app.post("/chat")
async def chat(request: ChatRequest):
    """
    核心问答接口 — 接收问题，SSE 流式返回答案

    前端用 EventSource/fetch 接这个接口，每收到一个 event 就追加显示
    事件类型:
      event: thinking   → 思考步骤提示
      event: tool_end   → 检索完成（文档数 + 来源）
      event: answer     → 逐 token 答案文本
      event: sources    → 引用文档列表
      event: done       → 传输完成
      event: error      → 出错信息
    """

    async def generate():
        """SSE 生成器 — 把 ask() 的输出转成 SSE 格式的字节流"""
        try:
            for chunk in ask(request.question, request.session_id):
                chunk_type = chunk.get("type", "")
                content = chunk.get("content", "")

                if chunk_type == "thinking":
                    # 思考步骤提示
                    yield f"event: thinking\ndata: {content}\n\n"
                elif chunk_type == "tool_end":
                    # 工具调用完成
                    yield f"event: tool_end\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                elif chunk_type == "answer":
                    # 逐 token 推送答案
                    yield f"event: answer\ndata: {content}\n\n"
                elif chunk_type == "sources":
                    yield f"event: sources\ndata: {json.dumps(chunk.get('sources', []), ensure_ascii=False)}\n\n"
                elif chunk_type == "done":
                    yield "event: done\ndata: {}\n\n"
                elif chunk_type == "error":
                    yield f"event: error\ndata: {json.dumps({'message': content}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
