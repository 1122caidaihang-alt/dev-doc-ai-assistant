"""
把 sentence-transformers 模型转成 ONNX 格式
运行: .venv\Scripts\python.exe export_onnx.py
"""
import os
import torch
from sentence_transformers import SentenceTransformer

MODEL_PATH = "data/models/all-MiniLM-L6-v2"
OUTPUT_DIR = "data/models/all-MiniLM-L6-v2-onnx"

os.makedirs(OUTPUT_DIR, exist_ok=True)

print("加载模型...")
model = SentenceTransformer(MODEL_PATH)

# 拿底层 transformer 模型（去掉 pooling 层）
transformer = model._first_module().auto_model
tokenizer = model.tokenizer

# 用 dummy 输入导出 ONNX
dummy = tokenizer("warmup test", return_tensors="pt", padding=True, truncation=True)

print("导出 ONNX...")
torch.onnx.export(
    transformer,
    (dummy["input_ids"], dummy["attention_mask"]),
    os.path.join(OUTPUT_DIR, "model.onnx"),
    input_names=["input_ids", "attention_mask"],
    output_names=["last_hidden_state"],
    dynamic_axes={
        "input_ids": {0: "batch", 1: "sequence"},
        "attention_mask": {0: "batch", 1: "sequence"},
        "last_hidden_state": {0: "batch", 1: "sequence"},
    },
    opset_version=14,
)

# 保存 tokenizer 文件（ONNX 推理时需要）
tokenizer.save_pretrained(OUTPUT_DIR)

# 复制 config
import shutil
shutil.copy(
    os.path.join(MODEL_PATH, "config.json"),
    os.path.join(OUTPUT_DIR, "config.json"),
)
shutil.copy(
    os.path.join(MODEL_PATH, "tokenizer_config.json"),
    os.path.join(OUTPUT_DIR, "tokenizer_config.json"),
)
# 词汇表文件
for f in ["vocab.txt", "special_tokens_map.json"]:
    src = os.path.join(MODEL_PATH, f)
    if os.path.exists(src):
        shutil.copy(src, os.path.join(OUTPUT_DIR, f))

print(f"完成 → {OUTPUT_DIR}")
