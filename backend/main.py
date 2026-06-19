"""
FastAPI 入口 — 整个后端的启动文件
运行命令: uvicorn main:app --reload --port 8000
"""
import json
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from models.schemas import IngestRequest, IngestResponse, HealthResponse, ChatRequest
from ingestion.loader import load_documents
from ingestion.splitter import split_documents
from ingestion.indexer import build_index, get_collection_stats
from services.chat_service import ask, ask_with_agent
from config import CHUNK_SIZE, CHUNK_OVERLAP, DEEPSEEK_API_KEY

app = FastAPI(title="开发者文档 AI 知识助手", version="0.1.0")


@app.on_event("startup")
async def startup():
    """
    服务启动：恢复持久化 session + 后台加载 embedding 模型

    ChromaDB 已本地预建并提交到 git（12MB），部署时直接加载，不需入库。
    模型已提交到 git（88MB），后台线程加载避免阻塞端口绑定。
    前端请求时如模型未就绪，会发心跳事件保持 SSE 连接不断。
    """
    import logging
    import threading
    logger = logging.getLogger("uvicorn")

    from services.memory_service import load_all_sessions
    load_all_sessions()

    # 后台线程加载模型，不阻塞端口绑定
    def _warmup():
        from ingestion.indexer import get_embedding, _set_model_ready
        logger.info("后台加载 embedding 模型（本地磁盘）...")
        get_embedding("warmup")
        _set_model_ready()
        logger.info("embedding 模型加载完成")

    threading.Thread(target=_warmup, daemon=True).start()
    logger.info("服务已启动（模型后台加载中...）")

# CORS 跨域配置 — 前端 Vercel 调后端 Railway 需要这个
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,   # 不用 cookie，True 跟 allow_origins=["*"] 冲突
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
        "deepseek_api": "configured" if DEEPSEEK_API_KEY and DEEPSEEK_API_KEY != "sk-your-key-here" else "missing_key",
        "indexed_docs": stats["count"],
    }


@app.get("/sessions")
async def list_sessions():
    """
    获取所有历史会话列表 — 给前端历史对话栏用

    返回 [{session_id, title, message_count, last_updated}, ...]
    按最后更新时间倒序排列
    """
    from services.memory_service import list_sessions_info
    return list_sessions_info()


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """
    获取指定会话的完整消息历史 — 前端切换历史对话时调用

    返回 {session_id, messages: [...], summary: "..."}
    如果 session 不存在返回 404
    """
    from services.memory_service import get_session_messages
    result = get_session_messages(session_id)
    if result is None:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"detail": "Session not found"})
    return result


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """
    删除指定会话 — 清除内存 + JSON 文件 + .log 文件

    返回 {"status": "deleted"} 或 404
    """
    from services.memory_service import clear_session, get_session_messages
    # 先检查是否存在
    existing = get_session_messages(session_id)
    if existing is None:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"detail": "Session not found"})
    clear_session(session_id)
    return {"status": "deleted", "session_id": session_id}


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
      event: memory     → 已加载对话历史（消息数 + token 使用率）
      event: cache_hit  → 语义缓存命中，跳过检索链直接返回
      event: thinking   → 思考步骤提示
      event: tool_call  → Agent 调用工具（工具名 + 输入参数）
      event: tool_result → 工具返回结果（截断显示前 300 字符）
      event: tool_end   → 检索完成（文档数 + 来源）
      event: compressed → 记忆压缩完成（压缩消息数 + 摘要字数）
      event: answer     → 逐 token 答案文本
      event: sources    → 引用文档列表
      event: done       → 传输完成
      event: error      → 出错信息
    """

    def _sse_safe(text: str) -> str:
        """
        SSE data 字段中不能出现裸换行符 \n，会破坏 event/data 格式
        把 \n 替换为空格，确保事件不跨行
        """
        return text.replace('\n', ' ').replace('\r', '')

    async def generate():
        """
        SSE 生成器 — 把 ask_with_agent() 的输出转成 SSE 格式的字节流

        SSE (Server-Sent Events) 格式:
          event: <事件类型>\n
          data: <JSON 数据>\n\n

        前端用 EventSource 监听对应事件类型即可实时更新 UI
        """
        try:
            for chunk in ask_with_agent(request.question, request.session_id):
                chunk_type = chunk.get("type", "")
                content = chunk.get("content", "")

                if chunk_type == "thinking":
                    # 思考步骤提示
                    yield f"event: thinking\ndata: {_sse_safe(content)}\n\n"

                elif chunk_type == "memory":
                    # Phase 4: 记忆加载事件 → 前端展示"已加载历史上下文"
                    yield f"event: memory\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"

                elif chunk_type == "cache_hit":
                    # Phase 6: 缓存命中 → 前端展示"缓存命中"
                    yield f"event: cache_hit\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"

                elif chunk_type == "compressed":
                    # Phase 4: 记忆压缩完成 → 前端展示压缩统计
                    yield f"event: compressed\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"

                elif chunk_type == "tool_call":
                    yield f"event: tool_call\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"

                elif chunk_type == "tool_result":
                    yield f"event: tool_result\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"

                elif chunk_type == "tool_end":
                    # 工具调用完成
                    yield f"event: tool_end\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"

                elif chunk_type == "answer":
                    # 逐 token 推送答案，换行符替换为空格防止破坏 SSE 格式
                    yield f"event: answer\ndata: {_sse_safe(content)}\n\n"

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
