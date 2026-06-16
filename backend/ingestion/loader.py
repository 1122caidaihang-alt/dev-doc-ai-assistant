"""
文档加载器 — 扫描指定目录下所有 .md 文件，读取内容
"""
import os
from typing import List, Dict


def load_documents(doc_path: str) -> List[Dict[str, str]]:
    """
    递归扫描 doc_path 目录，读取所有 .md 文件
    返回列表，每个元素是 {"filename": "相对路径/xxx.md", "content": "文件内容"}
    """
    documents = []

    # os.walk 递归遍历目录 — 会进入所有子文件夹
    for root, dirs, files in os.walk(doc_path):
        for file in files:
            if file.endswith(".md"):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    # 记录相对路径，比如 "guide/config.md"，方便溯源
                    rel_path = os.path.relpath(filepath, doc_path)
                    documents.append({
                        "filename": rel_path,
                        "content": content,
                    })
                except Exception as e:
                    print(f"[WARN] 读取 {filepath} 失败: {e}")

    print(f"[loader] 扫描完成: {len(documents)} 个 .md 文件")
    return documents
