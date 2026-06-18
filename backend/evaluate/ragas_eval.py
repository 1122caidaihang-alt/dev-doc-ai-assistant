"""
RAG 检索质量评测 — 消融实验

Phase 7: 量化验证 Phase 5 每个增强组件的贡献

用法: python evaluate/ragas_eval.py

指标:
  Hit Rate  — top-K 结果中至少命中 1 个相关文档的比例
  MRR       — 第一个相关文档排名的倒数均值 (Mean Reciprocal Rank)

消融实验设计:
  基线:     纯语义搜索 (Chroma only)
  +BM25:    语义 + BM25 双路召回
  +Reranker: 语义 + BM25 + Reranker 精排
  全链路:   语义 + BM25 + Reranker + 查询重写 + 二次检索

时间: 约 2-4 分钟 (20 题 × 4 组 × API 调用)
"""
import json
import time
import sys
import os

# 确保能 import backend 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.rag_service import search_documents, hybrid_search
from services.bm25_service import get_bm25_retriever
from services.cache_service import clear_cache


def load_questions(path: str = None):
    """加载测试问题集"""
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "test_questions.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def hit_rate(results, relevant_sources, top_k=5):
    """
    计算单条查询的 Hit Rate

    Hit Rate = 1 if top-K 结果中至少包含 1 个相关来源, else 0
    """
    result_sources = set(r["source"] for r in results[:top_k])
    relevant = set(relevant_sources)
    hits = result_sources & relevant
    return 1 if hits else 0, list(hits)


def mrr(results, relevant_sources):
    """
    计算单条查询的 MRR

    MRR = 1 / (第一个相关结果的排名)
    排名从 1 开始，没找到则为 0
    """
    for rank, r in enumerate(results, start=1):
        if r["source"] in relevant_sources:
            return 1.0 / rank
    return 0.0


def run_experiment(name: str, search_fn, questions, **search_kwargs):
    """
    对一组问题跑指定检索函数，计算平均指标

    参数:
        name: 实验组名称
        search_fn: 检索函数 (search_documents 或 hybrid_search)
        questions: 测试问题列表
        **search_kwargs: 传给 search_fn 的额外参数 (如 enable_bm25=False)
    """
    print(f"\n{'='*60}")
    print(f"  实验组: {name}")
    print(f"{'='*60}")

    total_hits = 0
    total_mrr = 0.0
    total_time = 0.0
    details = []

    for i, q in enumerate(questions):
        question = q["question"]
        relevant = q["relevant_sources"]

        # 清除缓存（避免缓存干扰消融实验）
        clear_cache(f"eval-{i}")

        start = time.time()
        results = search_fn(question, top_k=5, **search_kwargs)
        elapsed = time.time() - start
        total_time += elapsed

        h, hit_sources = hit_rate(results, relevant)
        m = mrr(results, relevant)
        total_hits += h
        total_mrr += m

        status = "HIT" if h else "MISS"
        print(f"  [{i+1:2d}] {status} | MRR={m:.2f} | {elapsed:.1f}s | {question[:40]}...")
        details.append({
            "question": question,
            "hit": h,
            "mrr": m,
            "sources_found": hit_sources,
            "time": elapsed,
        })

    n = len(questions)
    avg_hit = total_hits / n
    avg_mrr = total_mrr / n
    avg_time = total_time / n

    print(f"  ---")
    print(f"  Hit Rate:  {avg_hit:.1%} ({total_hits}/{n})")
    print(f"  MRR:       {avg_mrr:.3f}")
    print(f"  Avg time:  {avg_time:.2f}s")

    return {
        "name": name,
        "hit_rate": round(avg_hit, 3),
        "mrr": round(avg_mrr, 3),
        "avg_time": round(avg_time, 2),
        "details": details,
    }


def main():
    """主评测流程：四组消融实验"""
    print("=" * 60)
    print("  RAG 检索质量评测 — 消融实验")
    print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    questions = load_questions()
    print(f"\n已加载 {len(questions)} 条测试问题")

    results = []

    # ============================================================
    # 实验 1: 基线 — 纯语义搜索
    # ============================================================
    r1 = run_experiment(
        "基线: 纯语义搜索",
        search_documents,
        questions,
    )
    results.append(r1)

    # ============================================================
    # 实验 2: 语义 + BM25
    # ============================================================
    r2 = run_experiment(
        "语义 + BM25",
        hybrid_search,
        questions,
        enable_rewrite=False,
        enable_reranker=False,
        enable_fallback=False,
    )
    results.append(r2)

    # ============================================================
    # 实验 3: 语义 + BM25 + Reranker
    # ============================================================
    r3 = run_experiment(
        "语义 + BM25 + Reranker",
        hybrid_search,
        questions,
        enable_rewrite=False,
        enable_fallback=False,
    )
    results.append(r3)

    # ============================================================
    # 实验 4: 全链路
    # ============================================================
    r4 = run_experiment(
        "全链路: 重写 + BM25 + Reranker + 二次检索",
        hybrid_search,
        questions,
    )
    results.append(r4)

    # ============================================================
    # 汇总报告
    # ============================================================
    print(f"\n{'='*60}")
    print(f"  消融实验汇总")
    print(f"{'='*60}")
    print(f"  {'实验组':<40} {'Hit Rate':>8} {'MRR':>8} {'Avg Time':>10}")
    print(f"  {'-'*66}")

    baseline = results[0]
    for r in results:
        name = r["name"]
        hr = f"{r['hit_rate']:.1%}"
        mrr = f"{r['mrr']:.3f}"
        t = f"{r['avg_time']:.1f}s"

        # 相对基线的提升
        hr_delta = r['hit_rate'] - baseline['hit_rate']
        mrr_delta = r['mrr'] - baseline['mrr']
        delta_str = f" (HR+{hr_delta:.0%}, MRR+{mrr_delta:.0%})" if r != baseline else ""
        print(f"  {name:<40} {hr:>8} {mrr:>8} {t:>10}{delta_str}")

    print(f"\n  结论:")
    hr_gain = results[-1]['hit_rate'] - baseline['hit_rate']
    mrr_gain = results[-1]['mrr'] - baseline['mrr']
    print(f"    全链路 vs 基线: Hit Rate 提升 {hr_gain:.0%}, MRR 提升 {mrr_gain:.0%}")


if __name__ == "__main__":
    main()
