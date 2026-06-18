"""
芋道官方文档爬虫 — 从 doc.iocoder.cn 拉取所有文档页面

用法: python scrape_docs.py
输出: ./data/docs/ruoyi-vue-pro-official/{section}/{page}.md

VuePress 1.x 预渲染站点，curl 拉 HTML → 从 <main> 提取内容 → 存 .md
"""
import re
import os
import time
import httpx
from typing import Optional, Tuple
from pathlib import Path
from html import unescape


BASE_URL = "https://doc.iocoder.cn"
OUTPUT_DIR = "./data/docs/ruoyi-vue-pro-official"
DELAY_SECONDS = 0.5  # 请求间隔，礼貌爬取
REQUEST_TIMEOUT = 20


# ============================================================
# 所有待爬取的页面（从站点 HTML 导航中提取）
# ============================================================
PAGE_PATHS = [
    # === 框架核心功能（Tier 1：最值钱）===
    "/intro", "/quick-start", "/quick-start-front", "/project-intro",
    "/technology", "/feature", "/new-feature", "/sql-update",
    "/redis-cache", "/remove-redis", "/local-cache",
    "/mybatis", "/mybatis-pro", "/dynamic-datasource",
    "/validator", "/vo", "/util", "/exception",
    "/distributed-lock", "/rate-limiter", "/idempotent",
    "/oauth2", "/social-user", "/captcha",
    "/api-encrypt", "/http-sign", "/api-doc",
    "/file", "/sms", "/mail", "/notify", "/webhook",
    "/job", "/async-task",
    "/data-permission", "/resource-permission",
    "/sensitive-word", "/desensitize", "/system-log",
    "/server-monitor", "/server-protection",
    "/config-center", "/area-and-ip", "/dev-env", "/dev-hot-swap",
    "/websocket", "/https",
    "/excel-import-and-export", "/db-doc",
    "/delete-code", "/module-new", "/migrate-module",
    "/page-feature", "/project-rename",
    "/unit-test", "/interview", "/video",
    "/saas-tenant", "/saas-tenant/dynamic",
    "/xinchuang-db", "/natapp", "/waibao", "/qun",
    # 消息队列
    "/message-queue/event", "/message-queue/kafka", "/message-queue/rabbitmq",
    "/message-queue/redis", "/message-queue/rocketmq",
    # 部署
    "/deployment-docker", "/deployment-linux", "/deployment-war",
    "/deployment-baota", "/deployment-1panel", "/deployment-jenkins",

    # === 业务模块（Tier 2）===
    # BPM 工作流
    "/bpm", "/bpm/assignee", "/bpm/dameng", "/bpm/expression",
    "/bpm/listener", "/bpm/message", "/bpm/model-designer-bpmn",
    "/bpm/model-designer-dingding", "/bpm/model-designer-feel",
    "/bpm/sign", "/bpm/simple", "/bpm/start-user", "/bpm/tree",
    # 支付
    "/pay/build", "/pay/alipay-pay-demo", "/pay/alipay-transfer-demo",
    "/pay/wx-lite-pay-demo", "/pay/wx-pub-pay-demo",
    "/pay/refund-demo", "/pay/mock", "/pay/wallet",
    # 会员
    "/member/build", "/member/user", "/member/level",
    "/member/weixin-lite-login", "/member/weixin-lite-qrcode",
    "/member/weixin-lite-subscribe-message", "/member/weixin-mp-login",
    # CRM
    "/crm/build", "/crm/business", "/crm/clue", "/crm/contract",
    "/crm/customer", "/crm/follow-up", "/crm/permission", "/crm/product",
    # ERP
    "/erp/build", "/erp/product", "/erp/purchase", "/erp/sale",
    "/erp/stock", "/erp/stock-in-out", "/erp/stock-move-check",
    # 公众号
    "/mp/build", "/mp/account", "/mp/article", "/mp/auto-reply",
    "/mp/material", "/mp/menu", "/mp/message", "/mp/message-template",
    "/mp/publish", "/mp/statistics", "/mp/user",

    # === 内容精选（Tier 3：AI + 运维 + 前端核心页）===
    # AI (选其中跟框架配置强相关的)
    "/ai/build", "/ai/chat", "/ai/image", "/ai/knowledge",
    "/ai/mcp-client", "/ai/mcp-server", "/ai/midjourney",
    "/ai/mindmap", "/ai/music", "/ai/video",
    "/ai/workflow", "/ai/writing",
    # 前端核心
    "/vue3/dev-spec", "/vue3/crud-schema", "/vue3/dict",
    "/vue3/format", "/vue3/i18n", "/vue3/config-center",
    "/vue2/dev-spec", "/vue2/dict",
    # 预览页
    "/ai-preview", "/bpm-preview", "/crm-preview",
    "/erp-preview", "/im-preview", "/mall-preview",
    "/mes-preview", "/wms-preview",
    # 新功能
    "/new-feature/admin-uniapp", "/new-feature/master-sub", "/new-feature/tree",
    # 报表
    "/report", "/report/screen",
    # IM
    "/im/build",
    # 用户中心
    "/user-center",
]


def fetch_page(path: str) -> Optional[str]:
    """获取页面 HTML"""
    url = f"{BASE_URL}{path}"
    try:
        response = httpx.get(url, timeout=REQUEST_TIMEOUT, follow_redirects=True)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"  [ERROR] 获取失败: {url} — {e}")
        return None


def extract_content(html: str) -> Tuple[str, str]:
    """
    从 VuePress HTML 提取标题和正文

    返回: (title, content_markdown)
    """
    # 提取页面标题
    title_match = re.search(r'<title>(.*?)(?:\s*\|\s*ruoyi-vue-pro.*?)?</title>', html, re.IGNORECASE)
    title = unescape(title_match.group(1).strip()) if title_match else ""

    # 提取 <main> 标签内的内容（VuePress 预渲染的主内容区）
    main_match = re.search(r'<main[^>]*>(.*?)</main>', html, re.DOTALL)
    if not main_match:
        return title, ""

    content_html = main_match.group(1)

    # ============================================================
    # HTML → Markdown 转换
    # ============================================================

    # 去掉导航/侧边栏/页脚等非内容元素
    # VuePress 侧边栏 class="sidebar"
    content_html = re.sub(r'<aside[^>]*>.*?</aside>', '', content_html, flags=re.DOTALL)
    # 页面导航链接 "编辑此页" "最后更新"
    content_html = re.sub(r'<div[^>]*class="[^"]*page-edit[^"]*"[^>]*>.*?</div>', '', content_html, flags=re.DOTALL)
    content_html = re.sub(r'<div[^>]*class="[^"]*last-updated[^"]*"[^>]*>.*?</div>', '', content_html, flags=re.DOTALL)
    # 目录 (Table of Contents)
    content_html = re.sub(r'<div[^>]*class="[^"]*table-of-contents[^"]*"[^>]*>.*?</div>', '', content_html, flags=re.DOTALL)

    # 代码块：<pre><code> → 保留为 markdown 代码块
    content_html = re.sub(
        r'<pre[^>]*><code[^>]*class="[^"]*language-(\w+)[^"]*"[^>]*>(.*?)</code></pre>',
        lambda m: f"\n```{m.group(1)}\n{unescape(m.group(2))}\n```\n",
        content_html, flags=re.DOTALL
    )
    content_html = re.sub(
        r'<pre[^>]*><code[^>]*>(.*?)</code></pre>',
        lambda m: f"\n```\n{unescape(m.group(1))}\n```\n",
        content_html, flags=re.DOTALL
    )

    # 行内代码 <code> → `code`
    content_html = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', content_html)

    # 标题 <h1>~<h6> → #
    for level in range(1, 7):
        content_html = re.sub(
            f'<h{level}[^>]*>(.*?)</h{level}>',
            f'\n{"#" * level} \\1\n',
            content_html,
            flags=re.DOTALL
        )

    # 段落 <p> → 换行
    content_html = re.sub(r'<p[^>]*>', '\n', content_html)
    content_html = content_html.replace('</p>', '\n')

    # <br> → 换行
    content_html = re.sub(r'<br\s*/?>', '\n', content_html)

    # 链接 <a href="...">text</a> → [text](href)
    content_html = re.sub(
        r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        lambda m: f"[{m.group(2)}]({m.group(1)})" if not m.group(1).startswith('#') else m.group(2),
        content_html
    )

    # 粗体/斜体
    content_html = re.sub(r'<(?:strong|b)[^>]*>(.*?)</(?:strong|b)>', r'**\1**', content_html)
    content_html = re.sub(r'<(?:em|i)[^>]*>(.*?)</(?:em|i)>', r'*\1*', content_html)

    # 列表项 <li> → - / 1.
    content_html = re.sub(r'<li[^>]*>\s*', '- ', content_html)
    content_html = content_html.replace('</li>', '\n')

    # 去掉所有剩余 HTML 标签
    content_html = re.sub(r'<[^>]+>', '', content_html)

    # HTML 实体解码
    content_html = unescape(content_html)

    # 清理多余空行
    content_html = re.sub(r'\n{3,}', '\n\n', content_html)
    content_html = content_html.strip()

    return title, content_html


def scrape_all():
    """主函数：爬取所有页面"""
    total = len(PAGE_PATHS)
    success = 0
    failed = 0
    skipped = 0

    print(f"开始爬取 {total} 个页面到 {OUTPUT_DIR}/")
    print(f"请求间隔: {DELAY_SECONDS}s\n")

    for i, path in enumerate(PAGE_PATHS):
        # 确定输出文件路径
        # /redis-cache → redis-cache.md (根目录下的单页面)
        # /message-queue/kafka → message-queue/kafka.md (子目录)
        clean_path = path.strip("/")
        output_file = os.path.join(OUTPUT_DIR, f"{clean_path}.md")
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        # 跳过已下载的
        if os.path.exists(output_file):
            skipped += 1
            continue

        print(f"[{i+1}/{total}] {path} ...", end=" ", flush=True)

        html = fetch_page(path)
        if not html:
            failed += 1
            time.sleep(DELAY_SECONDS)
            continue

        title, content = extract_content(html)
        if not content:
            print("no content")
            failed += 1
            time.sleep(DELAY_SECONDS)
            continue

        # 写入文件
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n")
            f.write(f"> 来源: {BASE_URL}{path}\n\n")
            f.write(content)

        print(f"OK ({len(content)} chars)")
        success += 1
        time.sleep(DELAY_SECONDS)

    print(f"\n=== Done ===")
    print(f"OK: {success}, Failed: {failed}, Skipped: {skipped}")


if __name__ == "__main__":
    scrape_all()
