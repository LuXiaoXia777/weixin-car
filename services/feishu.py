"""生成表格化运营日报并通过飞书自定义机器人推送。"""

from __future__ import annotations

import requests

from services.ai_analysis import AnalysisResult
from services.metrics import ReportMetrics


INSUFFICIENT = "数据不足，暂无法判断"


def _cell(value: object) -> str:
    return str(value).replace("|", "/").replace("\n", " ").strip()


def _table(headers: list[str], rows: list[list[object]]) -> str:
    header = "| " + " | ".join(headers) + " |"
    divider = "|" + "|".join("---" for _ in headers) + "|"
    body = "\n".join("| " + " | ".join(_cell(value) for value in row) + " |" for row in rows)
    return "\n".join((header, divider, body))


def _lookup(items: list, key: str, value: str, result: str) -> str:
    match = next((item for item in items if getattr(item, key) == value), None)
    return getattr(match, result) if match else INSUFFICIENT


def build_report(metrics: ReportMetrics, analysis: AnalysisResult) -> str:
    overview = _table(
        ["指标", "数据", "环比", "分析"],
        [[row["metric"], row["value"], row["change"], row["analysis"]] for row in metrics.overview],
    )

    ranking_rows = []
    for rank, item in enumerate(metrics.rankings, start=1):
        article = item.article
        judgment = _lookup(analysis.article_judgments, "title", article.title, "judgment")
        ranking_rows.append(
            [
                rank,
                article.title,
                item.content_type,
                f"{article.views:,}",
                article.likes,
                article.shares,
                article.new_followers,
                f"{item.score:.1f}",
                judgment,
            ]
        )
    rankings = _table(
        ["排名", "标题", "类型", "阅读", "点赞", "分享", "涨粉", "评分", "AI判断"],
        ranking_rows,
    )

    category_rows = []
    for row in metrics.categories:
        content_type = row["content_type"]
        category_rows.append(
            [
                content_type,
                row["article_count"],
                f"{row['average_views']:,}",
                f"{row['average_interaction_rate'] * 100:.2f}%",
                f"篇均 {row['average_new_followers']:.1f} 粉",
                _lookup(analysis.category_judgments, "content_type", content_type, "judgment"),
            ]
        )
    categories = _table(
        ["内容类型", "文章数量", "平均阅读", "平均互动率", "涨粉效果", "判断"],
        category_rows,
    )

    blockbuster = _table(
        ["分析项", "结果"],
        [
            ["标题结构", analysis.blockbuster.title_structure],
            ["用户痛点", analysis.blockbuster.user_pain],
            ["点击原因", analysis.blockbuster.click_reason],
            ["内容价值", analysis.blockbuster.content_value],
            ["可复制公式", analysis.blockbuster.replicable_formula],
        ],
    )
    trends = _table(
        ["趋势", "数据依据", "判断"],
        [[item.trend, item.data_basis, item.judgment] for item in analysis.trends],
    )
    suggestions = _table(
        ["优先级", "选题标题", "对应用户需求", "推荐原因"],
        [[item.priority, item.title, item.user_need, item.reason] for item in analysis.suggestions],
    )
    advice = _table(
        ["建议", "原因"],
        [[item.advice, item.reason] for item in analysis.advice],
    )

    return f"""# 🚗 车事人话｜公众号运营日报

**日期：{metrics.report_date.isoformat()}**

## 1. 今日数据概览

{overview}

---

## 2. 文章表现排行

评分：阅读量40%｜互动率30%｜涨粉效率30%

{rankings}

---

## 3. 内容类型分析（近7天）

{categories}

---

## 4. 爆款因素拆解

**最佳文章：{analysis.best_article}**

{blockbuster}

---

## 5. 用户兴趣变化

{trends}

---

## 6. 下周选题推荐

{suggestions}

---

## 7. 最终运营建议

{advice}"""


def send_report(webhook_url: str, markdown: str, *, timeout: int = 15) -> None:
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": "🚗 车事人话公众号运营日报"},
            },
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": markdown}}],
        },
    }
    response = requests.post(webhook_url, json=payload, timeout=timeout)
    response.raise_for_status()
    result = response.json()
    if result.get("code", result.get("StatusCode", 0)) != 0:
        raise RuntimeError(f"飞书推送失败：{result}")
