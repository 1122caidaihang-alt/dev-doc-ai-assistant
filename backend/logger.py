"""
统一日志配置 — 替换所有 print() 为结构化日志

格式: [2026-06-18 14:30:01] [INFO] [module] message
输出: 控制台（开发调试）+ 文件（./data/logs/app.log，持久化）

用法:
    from logger import get_logger
    logger = get_logger("memory")
    logger.info("消息内容")
    logger.error("错误内容")
"""
import logging
import os
from datetime import datetime


# 日志目录
LOG_DIR = "./data/logs"
os.makedirs(LOG_DIR, exist_ok=True)

# 日志格式
LOG_FORMAT = "[%(asctime)s] [%(levelname)-5s] [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 根 logger 配置
_root_handler_configured = False


def _setup_root_logger():
    """配置根 logger（只执行一次）"""
    global _root_handler_configured
    if _root_handler_configured:
        return

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # 控制台 handler
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root.addHandler(console)

    # 文件 handler（按日期命名，保留最近 7 天）
    log_file = os.path.join(LOG_DIR, "app.log")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root.addHandler(file_handler)

    _root_handler_configured = True
    logging.getLogger("logger").info("日志系统初始化完成")


def get_logger(name: str) -> logging.Logger:
    """
    获取模块级 logger

    参数:
        name: 模块名，如 "memory", "rag", "bm25", "reranker"

    返回:
        配置好的 logger 实例

    用法:
        logger = get_logger("memory")
        logger.info("保存 session abc123: 5 条消息")
    """
    _setup_root_logger()
    return logging.getLogger(name)
