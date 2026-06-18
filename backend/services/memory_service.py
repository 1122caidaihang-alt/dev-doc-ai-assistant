"""
记忆管理服务 — 对话历史存储 + 摘要压缩
Phase 4 核心模块：解决上下文窗口有限问题

三层记忆结构（参考 OpenAI 四层，针对技术文档问答定制）：
  Layer 3  摘要缓存 → LLM 把早期对话压缩成语义摘要（累积追加，不覆盖）
  Layer 2  近期原文 → 最近 5 轮完整对话（保证精确性）
  Layer 1  工作记忆 → 当前所有消息，压缩的原材料

持久化方案（两层文件）：
  ① JSON 文件（./data/sessions/{session_id}.json）→ 当前状态快照
     每次写操作后覆写，服务启动时恢复。压缩后旧消息原文被丢弃。
  ② .log 文件（./data/sessions/{session_id}.log）→ 完整消息总账
     append-only，只追加不删除，永久保留每一条消息原文。
     用于 RAGAS 评测回溯、用户提问分析、Agent 行为调试。
  为什么不用 Redis？  单机单用户，Redis 多一个故障点。
  为什么不用 SQLite？ JSON 天然适配 dict，零依赖。
  为什么不用向量库存历史？ 向量库做随机检索，技术问答要时序连贯。

面试重点：
  不是简单的"滑动窗口丢弃旧消息"，也不是照搬"向量数据库搜历史"，
  而是参考 OpenAI 四层架构，只保留需要的层，并在 Layer 3 做了改进
  （累积摘要而非直接丢弃）。
"""
import json
import os
import threading
import httpx
from datetime import datetime
from typing import List, Dict, Optional
from collections import defaultdict
from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_CHAT_MODEL,
    MAX_CONTEXT_TOKENS, SUMMARY_TRIGGER_RATIO, RECENT_ROUNDS_KEPT,
    MAX_MESSAGES_PER_SESSION,
)
from logger import get_logger

logger = get_logger("memory")


# ============================================================
# 持久化路径 — JSON 文件存放目录


# ============================================================
SESSIONS_DIR = "./data/sessions"


# ============================================================
# 内存存储 — 服务运行时的高速读写层
# 对话历史和摘要先读入内存，写操作同步落盘（JSON 文件）
# ============================================================

# 对话历史: session_id → [{"role": "user", "content": "..."}, ...]
# 每条消息记录角色和内容，按时间顺序排列
_conversations: Dict[str, List[Dict]] = defaultdict(list)

# 压缩摘要: session_id → "用户问了 A，助手回答了 B。然后用户追问了 C..."
# 累积摘要——每次压缩追加到已有摘要后面，不覆盖
_summaries: Dict[str, str] = {}

# 线程锁 — 保证并发写入安全
# threading.Lock（线程锁）：同一时刻只有一个线程能操作 dict + 写入 JSON
# 为什么不用 asyncio.Lock？因为 add_message/compress_history 是同步函数（def 而非 async def）
# 面试时说："Python 的 threading.Lock 保证并发写入安全"
_write_lock = threading.Lock()

# ============================================================
# JSON 文件持久化 — 每次写操作后自动落盘，重启恢复
# 面试重点：持久化方案的选择理由（为什么不用 Redis/SQLite/向量库）
# ============================================================

def _session_file(session_id: str) -> str:
    """
    安全地获取 session 对应的 JSON 文件路径

    session_id 可能来自用户输入（恶意构造），用 os.path.basename
    防止路径穿越攻击（如 session_id = "../../etc/passwd"）
    """
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    safe_name = os.path.basename(session_id) or "default"
    return os.path.join(SESSIONS_DIR, f"{safe_name}.json")


def _append_to_log(session_id: str, role: str, content: str):
    """
    内部函数：把每条消息追加写入 append-only 日志文件

    跟 _save_to_file 的区别：
      - JSON 文件 = 当前状态快照（压缩后会丢掉旧消息原文）
      - .log 文件  = 完整消息总账（只追加不删除，永久保留）

    用途：
      - RAGAS 评测回溯（需要原始对话做 ground truth）
      - 后期分析用户提问模式
      - 调试 Agent 行为

    JSON Lines 格式：每行一条 {"role":"user","content":"..."}
    追加写是 OS 级原子操作（行级别），不需要额外加锁。
    """
    try:
        log_path = os.path.join(SESSIONS_DIR, f"{os.path.basename(session_id) or 'default'}.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"role": role, "content": content}, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"追加日志失败 session={session_id}: {e}")


def _save_to_file(session_id: str):
    """
    内部函数：把内存中的对话历史 + 摘要写入 JSON 文件
    调用方必须已经持有 _write_lock，本函数不负责加锁

    每调用一次，整个 session 完整覆写（不是增量追加）。
    因为单 session 数据量小（几十条消息），全量覆写足够快。
    """
    try:
        data = {
            "session_id": session_id,
            "messages": _conversations.get(session_id, []),
            "summary": _summaries.get(session_id, ""),
        }
        with open(_session_file(session_id), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存 session {session_id} 失败: {e}")


def save_session(session_id: str):
    """
    外部接口：加锁后写入 JSON 文件

    如果调用方已经持有锁（如 add_message 内部），直接调 _save_to_file 避免死锁。
    这个函数给外部独立调用用（如手动触发保存）。
    """
    with _write_lock:
        _save_to_file(session_id)


def load_session(session_id: str) -> bool:
    """
    从 JSON 文件恢复一个 session 到内存

    返回 True 表示成功恢复，False 表示文件不存在
    """
    path = _session_file(session_id)
    if not os.path.exists(path):
        return False

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        _conversations[session_id] = data.get("messages", [])
        _summaries[session_id] = data.get("summary", "")

        msg_count = len(_conversations[session_id])
        summary_len = len(_summaries.get(session_id, ""))
        logger.info(f"已恢复 session {session_id}: {msg_count} 条消息, 摘要 {summary_len} 字")
        return True

    except Exception as e:
        logger.warning(f"恢复 session {session_id} 失败: {e}")
        return False


def load_all_sessions() -> int:
    """
    服务启动时调用 — 遍历 sessions 目录，恢复所有已持久化的 session

    返回恢复的 session 数量
    """
    if not os.path.exists(SESSIONS_DIR):
        logger.info("sessions 目录不存在，跳过恢复")
        return 0

    count = 0
    for filename in os.listdir(SESSIONS_DIR):
        if filename.endswith(".json"):
            session_id = filename[:-5]  # 去掉 .json 后缀
            if load_session(session_id):
                count += 1

    logger.info(f"启动恢复完成: {count} 个 session")
    return count


# ============================================================
# Token 估算
# ============================================================

def estimate_tokens(text: str) -> int:
    """
    粗略估算一段文本占多少 token

    中文一个字符 ≈ 1.5~2 token，英文一个单词 ≈ 1.3 token
    这里用 len(text) // 2 做保守估算（中英文混排场景）
    实际 token 数通常比这个估算少，所以用 // 2 保留安全余量
    """
    return max(1, len(text) // 2)


# ============================================================
# 对话历史读写
# ============================================================

def add_message(session_id: str, role: str, content: str):
    """
    向对话历史追加一条消息

    role: "user" 或 "assistant"
    content: 消息正文

    每轮对话调两次：一次存用户问题，一次存助手回答
    写入操作在 threading.Lock 保护下进行，防止并发写冲突
    """
    with _write_lock:
        _conversations[session_id].append({
            "role": role,
            "content": content,
        })
        _save_to_file(session_id)  # 自动落盘（锁内，不用再抢锁）

        # Phase 7: 消息上限——超过 MAX_MESSAGES_PER_SESSION 时截断最早的消息
        overflow = len(_conversations[session_id]) - MAX_MESSAGES_PER_SESSION
        if overflow > 0:
            _conversations[session_id] = _conversations[session_id][overflow:]
            logger.info(f"session {session_id[:8]}... 超上限，截断 {overflow} 条旧消息")

    # 追加写入完整日志（锁外——只追加不修改，OS 级原子操作，不需要锁保护）
    _append_to_log(session_id, role, content)


def get_recent_messages(session_id: str, rounds: int = None) -> List[Dict]:
    """
    获取最近 N 轮对话的原文

    一轮 = 用户问题 + 助手回答（2 条消息）
    返回扁平的消息列表，可直接在 Prompt 中使用

    参数:
        rounds: 保留轮数，默认用 RECENT_ROUNDS_KEPT (5 轮)
    """
    if rounds is None:
        rounds = RECENT_ROUNDS_KEPT

    history = _conversations[session_id]
    recent_count = rounds * 2  # 每轮 2 条消息
    return history[-recent_count:] if len(history) > recent_count else history[:]


def get_full_history(session_id: str) -> List[Dict]:
    """获取完整对话历史（不含摘要）"""
    return list(_conversations[session_id])


def get_history_message_count(session_id: str) -> int:
    """返回当前 session 的消息总数"""
    return len(_conversations[session_id])


# ============================================================
# 摘要管理
# ============================================================

def get_summary(session_id: str) -> Optional[str]:
    """获取当前 session 的压缩摘要，没有则返回 None"""
    return _summaries.get(session_id)


def has_history(session_id: str) -> bool:
    """判断是否有历史对话（含摘要）"""
    return bool(_summaries.get(session_id)) or bool(_conversations.get(session_id))


# ============================================================
# 压缩触发判断
# ============================================================

def should_compress(session_id: str) -> bool:
    """
    判断是否需要触发摘要压缩

    条件：历史消息的估算 token 数 > MAX_CONTEXT_TOKENS × SUMMARY_TRIGGER_RATIO
    默认: 28000 × 0.8 = 22400 tokens

    在窗口快满但还没满的时候就触发压缩，给 LLM 响应留空间
    """
    history = _conversations[session_id]
    if not history:
        return False

    # 把所有消息拼起来估算 token 数
    total_text = "".join(msg["content"] for msg in history)
    estimated_tokens = estimate_tokens(total_text)
    threshold = MAX_CONTEXT_TOKENS * SUMMARY_TRIGGER_RATIO

    return estimated_tokens > threshold


def get_history_token_usage(session_id: str) -> Dict:
    """
    返回当前 session 的 token 使用情况，用于前端展示或调试

    返回:
        {"estimated_tokens": 15000, "threshold": 22400, "percent": 67.0}
    """
    history = _conversations[session_id]
    total_text = "".join(msg["content"] for msg in history)
    estimated_tokens = estimate_tokens(total_text)
    threshold = MAX_CONTEXT_TOKENS * SUMMARY_TRIGGER_RATIO

    return {
        "estimated_tokens": estimated_tokens,
        "threshold": int(threshold),
        "percent": round(estimated_tokens / threshold * 100, 1) if threshold > 0 else 0,
        "message_count": len(history),
    }


# ============================================================
# 核心：摘要压缩
# ============================================================

def _build_compression_prompt(messages_to_summarize: List[Dict]) -> str:
    """
    构造摘要 Prompt — 让 LLM 把一段对话压缩成简短摘要

    要求 LLM 提取：关键问题 + 答案要点 + 技术术语
    输出控制在 200 字以内
    """
    dialogue = ""
    for msg in messages_to_summarize:
        role_label = "用户" if msg["role"] == "user" else "助手"
        dialogue += f"{role_label}: {msg['content']}\n"

    return f"""请将以下对话历史压缩成一段简短摘要（200 字以内）。
只保留关键的技术问题和答案要点，忽略客套话和冗余表述。

对话历史：
{dialogue}

摘要："""


def compress_history(session_id: str) -> Dict:
    """
    压缩对话历史 — 调 LLM 把早期对话压缩成摘要

    压缩策略（面试重点）：
    1. 找到切分点：保留最近 RECENT_ROUNDS_KEPT 轮，之前的全部压缩
    2. 调 LLM（低 temperature）把旧消息压缩成一段摘要（锁外，慢操作不阻塞其他请求）
    3. 摘要追加到已有摘要后面（累积摘要）
    4. 清理旧消息，只保留最近的消息
    5. 持久化保存

    并发安全：LLM 调用在锁外进行（不阻塞其他请求的写入），
    只有 dict 修改 + JSON 写入在锁内。

    返回:
        {"compressed_count": 压缩的消息数, "summary_length": 摘要字数}
        用于前端展示压缩结果
    """
    # 第 1 步：在锁内读取并拷贝历史（防止并发修改）
    with _write_lock:
        history_snapshot = list(_conversations[session_id])  # 拷贝一份
        old_summary_before = _summaries.get(session_id, "")

    total = len(history_snapshot)

    # 计算切分点：总共 N 条消息，保留最后 RECENT_ROUNDS_KEPT × 2 条
    keep_count = RECENT_ROUNDS_KEPT * 2  # 每轮 user + assistant
    split_at = max(0, total - keep_count)

    old_messages = history_snapshot[:split_at]

    if not old_messages:
        return {"compressed_count": 0, "summary_length": 0}

    # 第 2 步：调 LLM 生成摘要（锁外——这是网络调用，慢，不阻塞其他请求）
    prompt = _build_compression_prompt(old_messages)

    try:
        url = f"{DEEPSEEK_BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "model": DEEPSEEK_CHAT_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 300,
        }

        response = httpx.post(url, headers=headers, json=body, timeout=30.0)
        response.raise_for_status()

        data = response.json()
        new_summary = data["choices"][0]["message"]["content"].strip()

        # 第 3 步：在锁内修改 dict + 写入 JSON（快，只锁必要部分）
        with _write_lock:
            # 累积摘要：把新摘要拼到旧摘要后面
            if old_summary_before:
                _summaries[session_id] = f"{old_summary_before}\n{new_summary}"
            else:
                _summaries[session_id] = new_summary

            # 清理旧消息，只保留最近的消息
            _conversations[session_id] = history_snapshot[split_at:]

            # 落盘
            _save_to_file(session_id)

        logger.info(f"压缩完成: {len(old_messages)} 条消息 → {len(new_summary)} 字摘要 "
              f"(保留 {len(_conversations[session_id])} 条最近消息)")

        return {
            "compressed_count": len(old_messages),
            "summary_length": len(new_summary),
        }

    except Exception as e:
        logger.error(f"摘要压缩失败: {e}")
        return {"compressed_count": 0, "summary_length": 0, "error": str(e)}


# ============================================================
# 构建 Agent 上下文 — 这是记忆系统对外暴露的核心接口
# ============================================================

def build_context(session_id: str, question: str) -> str:
    """
    拼装传给 Agent 的完整上下文

    这是记忆系统对外的核心接口，chat_service 调用此函数获取
    带历史记忆的 Agent 输入

    拼装规则：
      如果有摘要 → [历史对话摘要] + "\n"
      如果有最近消息 → [最近对话] + "\n"
      总是追加 → [当前问题] + question

    返回示例:
      [历史对话摘要]
      用户问了数据库配置和多数据源问题，助手基于文档给出了配置示例。

      [最近对话]
      用户: 怎么配置多数据源？
      助手: 在 application.yml 中配置 spring.datasource.dynamic...

      [当前问题]
      那读写分离怎么配置？
    """
    summary = _summaries.get(session_id, "")
    recent = get_recent_messages(session_id)

    parts = []

    # 第一部分：历史摘要（如果有）
    if summary:
        parts.append(f"[历史对话摘要]\n{summary}")

    # 第二部分：最近对话原文
    if recent:
        recent_text = ""
        for msg in recent:
            role_label = "用户" if msg["role"] == "user" else "助手"
            recent_text += f"{role_label}: {msg['content']}\n"
        parts.append(f"[最近对话]\n{recent_text}")

    # 第三部分：当前问题
    parts.append(f"[当前问题]\n{question}")

    return "\n\n".join(parts)


# ============================================================
# 会话管理
# ============================================================

def clear_session(session_id: str):
    """清除指定 session 的所有数据（对话历史 + 摘要 + JSON 文件 + .log 文件）"""
    with _write_lock:
        _conversations.pop(session_id, None)
        _summaries.pop(session_id, None)
        # 删除 JSON 文件
        path = _session_file(session_id)
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                logger.warning(f"删除 session JSON 文件失败: {e}")
        # 删除 .log 文件
        safe_name = os.path.basename(session_id) or "default"
        log_path = os.path.join(SESSIONS_DIR, f"{safe_name}.log")
        if os.path.exists(log_path):
            try:
                os.remove(log_path)
            except Exception as e:
                logger.warning(f"删除 session log 文件失败: {e}")
    logger.info(f"已清除 session: {session_id}")


def get_all_sessions() -> List[str]:
    """返回所有活跃 session ID"""
    sessions = set(_conversations.keys()) | set(_summaries.keys())
    return list(sessions)


def get_session_stats(session_id: str) -> Dict:
    """
    返回 session 的统计信息，用于调试或前端展示

    返回:
        {
            "message_count": 对话消息数,
            "has_summary": 是否有摘要,
            "summary_length": 摘要字数,
            "token_usage": {token 估算信息},
        }
    """
    token_info = get_history_token_usage(session_id)
    return {
        "message_count": len(_conversations[session_id]),
        "has_summary": session_id in _summaries,
        "summary_length": len(_summaries.get(session_id, "")),
        "token_usage": token_info,
    }


def list_sessions_info() -> List[Dict]:
    """
    返回所有已持久化 session 的概要信息（给前端历史对话栏用）

    遍历 ./data/sessions/ 目录下的 JSON 文件，提取：
      - session_id: UUID
      - title: 第一条用户消息（截断 40 字）
      - message_count: 消息条数
      - last_updated: 文件最后修改时间（ISO 格式）

    返回按 last_updated 倒序排列（最近对话排最前）
    """
    sessions = []
    if not os.path.exists(SESSIONS_DIR):
        return sessions

    for filename in os.listdir(SESSIONS_DIR):
        if not filename.endswith(".json"):
            continue

        filepath = os.path.join(SESSIONS_DIR, filename)
        session_id = filename[:-5]  # 去掉 .json 后缀

        try:
            # 获取文件修改时间
            mtime = os.path.getmtime(filepath)
            last_updated = datetime.fromtimestamp(mtime).isoformat()

            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            messages = data.get("messages", [])
            msg_count = len(messages)

            # 取第一条用户消息作为标题
            title = ""
            for msg in messages:
                if msg.get("role") == "user":
                    title = msg.get("content", "")
                    break

            if not title:
                title = "(空对话)"

            # 截断过长标题
            if len(title) > 40:
                title = title[:40] + "..."

            sessions.append({
                "session_id": session_id,
                "title": title,
                "message_count": msg_count,
                "last_updated": last_updated,
            })
        except Exception as e:
            logger.warning(f"读取 session 文件失败 {filename}: {e}")
            continue

    # 按最后更新时间倒序
    sessions.sort(key=lambda s: s["last_updated"], reverse=True)
    return sessions


def get_session_messages(session_id: str):
    """
    返回指定 session 的完整消息列表（只返回 user/assistant 消息，不含内部事件）

    如果 session 不在内存中，尝试从 JSON 文件加载
    返回 {"messages": [...], "summary": "..."} 或 None（session 不存在）
    """
    # 如果不在内存中，尝试从文件加载
    if session_id not in _conversations:
        if not load_session(session_id):
            return None

    return {
        "session_id": session_id,
        "messages": _conversations.get(session_id, []),
        "summary": _summaries.get(session_id, ""),
    }
