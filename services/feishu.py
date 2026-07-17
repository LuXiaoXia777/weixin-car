"""构建并发送飞书 Interactive Card 公众号运营日报。"""

from __future__ import annotations

from typing import Any

import requests

from services.ai_analysis import AnalysisResult
from services.metrics import ReportMetrics


INSUFFICIENT = "数据不足，暂无法判断"


def _clean(value: object) -> str:
    return str(value).replace("\n", " ").strip()


def _lookup(items: list, key: str, value: str, result: str) -> str:
    match = next((item for item in items if getattr(item, key) == value), None)
    return _clean(getattr(match, result)) if match else INSUFFICIENT


def _section_title(text: str) -> dict[str, Any]:
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": f"**{text}**"},
    }


def _field(label: str, value: str) -> dict[str, Any]:
    return {
        "is_short": True,
        "text": {
            "tag": "lark_md",
            "content": f"**{label}**\n{_clean(value)}",
        },
    }


def _overview_element(metrics: ReportMetrics) -> dict[str, Any]:
    values = {row["metric"]: row["value"] for row in metrics.overview}
    labels = ("发布文章", "总阅读", "平均阅读", "点赞率", "分享率", "新增粉丝")
    return {
        "tag": "div",
        "fields": [_field(label, values.get(label, "—")) for label in labels],
    }


def _article_element(rank: int, item: Any, analysis: AnalysisResult) -> dict[str, Any]:
    article = item.article
    interaction_rate = (article.likes + article.shares + article.comments) / article.views
    judgment = _lookup(analysis.article_judgments, "title", article.title, "judgment")
    content = (
        f"**{rank}. {_clean(article.title)}**\n"
        f"类型：{item.content_type}　｜　阅读：{article.views:,}\n"
        f"互动率：{interaction_rate * 100:.2f}%　｜　涨粉：{article.new_followers:+d}\n"
        f"AI评价：{judgment}"
    )
    return {"tag": "div", "text": {"tag": "lark_md", "content": content}}


def _blockbuster_element(analysis: AnalysisResult) -> dict[str, Any]:
    detail = analysis.blockbuster
    content = (
        f"**最佳文章：{_clean(analysis.best_article)}**\n"
        f"标题结构：{_clean(detail.title_structure)}\n"
        f"用户痛点：{_clean(detail.user_pain)}\n"
        f"点击原因：{_clean(detail.click_reason)}\n"
        f"内容价值：{_clean(detail.content_value)}\n"
        f"可复制公式：{_clean(detail.replicable_formula)}"
    )
    return {"tag": "div", "text": {"tag": "lark_md", "content": content}}


def _trend_element(analysis: AnalysisResult) -> dict[str, Any]:
    lines = []
    for item in analysis.trends:
        lines.append(f"{_clean(item.trend)}：{_clean(item.data_basis)}；{_clean(item.judgment)}")
    return {
        "tag": "div",
        "text": {"tag": "plain_text", "content": "\n".join(lines)},
    }


def _suggestions_element(analysis: AnalysisResult) -> dict[str, Any]:
    lines = []
    for index, item in enumerate(analysis.suggestions, start=1):
        lines.append(
            f"{index}. **{_clean(item.title)}**\n"
            f"   用户需求：{_clean(item.user_need)}｜推荐原因：{_clean(item.reason)}"
        )
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": "\n".join(lines)},
    }


def build_report(metrics: ReportMetrics, analysis: AnalysisResult) -> dict[str, Any]:
    """返回可直接提交给飞书 Webhook 的 Interactive Card 请求体。"""
    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "plain_text",
                "content": f"数据日期：{metrics.report_date.isoformat()}",
            },
        },
        _section_title("📊 数据概览"),
        _overview_element(metrics),
        {"tag": "hr"},
        _section_title("🔥 文章排行"),
    ]

    for rank, item in enumerate(metrics.rankings, start=1):
        elements.append(_article_element(rank, item, analysis))
        if rank < len(metrics.rankings):
            elements.append({"tag": "hr"})

    elements.extend(
        [
            {"tag": "hr"},
            _section_title("🏆 爆款分析"),
            _blockbuster_element(analysis),
            {"tag": "hr"},
            _section_title("📈 7天内容趋势"),
            _trend_element(analysis),
            {"tag": "hr"},
            _section_title("💡 选题建议"),
            _suggestions_element(analysis),
        ]
    )

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": "🚗 车事人话｜公众号运营日报",
                },
            },
            "elements": elements,
        },
    }


def send_report(webhook_url: str, card_payload: dict[str, Any], *, timeout: int = 15) -> None:
    if card_payload.get("msg_type") != "interactive":
        raise ValueError("飞书消息必须使用 interactive 类型")
    response = requests.post(webhook_url, json=card_payload, timeout=timeout)
    response.raise_for_status()
    result = response.json()
    if result.get("code", result.get("StatusCode", 0)) != 0:
        raise RuntimeError(f"飞书推送失败：{result}")
