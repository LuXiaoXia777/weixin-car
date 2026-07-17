"""将指标报告和 DeepSeek 分析组装成飞书 Interactive Card。"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any

import requests
from pydantic import ValidationError

from config import Settings
from services.ai_analyzer import AIAnalysisResult, load_report


LOGGER = logging.getLogger(__name__)


def load_ai_analysis(path: Path) -> AIAnalysisResult:
    """读取并校验 DeepSeek 结构化分析结果。"""
    try:
        return AIAnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"找不到 DeepSeek 分析结果：{path.resolve()}") from exc
    except (ValidationError, ValueError) as exc:
        raise ValueError(f"DeepSeek 分析结果 JSON 无效：{path.resolve()}：{exc}") from exc


def _clean(value: Any) -> str:
    if value is None:
        return "—"
    return str(value).replace("\n", " ").strip() or "—"


def _metric(metric: dict[str, Any] | None) -> str:
    """格式化当前值和环比箭头。"""
    if not metric:
        return "—（环比数据不足）"
    value = metric.get("value")
    change = metric.get("change_rate")
    value_text = f"{value:,}" if isinstance(value, (int, float)) else _clean(value)
    if change is None:
        return f"{value_text}（环比数据不足）"
    if change > 0:
        arrow = "↑"
    elif change < 0:
        arrow = "↓"
    else:
        arrow = "→"
    return f"{value_text}　{arrow}{abs(change) * 100:.1f}%"


def _field(label: str, content: str) -> dict[str, Any]:
    return {
        "is_short": True,
        "text": {"tag": "lark_md", "content": f"**{label}**\n{content}"},
    }


def _heading(title: str) -> dict[str, Any]:
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": f"**{title}**"},
    }


def build_card(report: dict[str, Any], analysis: AIAnalysisResult) -> dict[str, Any]:
    """生成可直接发送给飞书群机器人的卡片请求体。"""
    overview = report.get("overview") or {}
    top_articles = report.get("top_articles") or []
    best = next(
        (row for row in top_articles if row.get("title") == analysis.best_article.title),
        top_articles[0] if top_articles else {},
    )
    suggestions = "\n".join(
        f"{index}. {_clean(item)}"
        for index, item in enumerate(analysis.tomorrow_suggestions, start=1)
    )
    best_content = (
        f"**{_clean(analysis.best_article.title)}**\n"
        f"阅读人数：{_clean(best.get('read_users'))}\n"
        f"AI分析：{_clean(analysis.best_article.reason)}"
    )
    trend_content = (
        f"{_clean(analysis.content_trend)}\n"
        f"**当前问题：** {_clean(analysis.problems)}"
    )

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True, "enable_forward": True},
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": "🚗 车事人话公众号运营日报",
                },
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "plain_text",
                        "content": f"数据日期：{_clean(report.get('date'))}",
                    },
                },
                {"tag": "hr"},
                _heading("📊 今日数据概览"),
                {
                    "tag": "div",
                    "fields": [
                        _field("阅读人数", _metric(overview.get("views"))),
                        _field("分享人数", _metric(overview.get("shares"))),
                        _field("收藏人数", _metric(overview.get("favorites"))),
                        _field("发布篇数", _metric(overview.get("publish_count"))),
                    ],
                },
                {"tag": "hr"},
                _heading("🔥 今日最佳文章"),
                {"tag": "div", "text": {"tag": "lark_md", "content": best_content}},
                {"tag": "hr"},
                _heading("📈 内容趋势"),
                {"tag": "div", "text": {"tag": "lark_md", "content": trend_content}},
                {"tag": "hr"},
                _heading("💡 明日选题建议"),
                {"tag": "div", "text": {"tag": "lark_md", "content": suggestions}},
            ],
        },
    }


def send_card(
    webhook_url: str,
    card_payload: dict[str, Any],
    *,
    timeout: int = 15,
    max_attempts: int = 3,
    retry_delay: float = 1.0,
) -> dict[str, Any]:
    """发送卡片；仅网络失败重试，HTTP错误立即记录并抛出。"""
    if not webhook_url.strip():
        raise ValueError("飞书 Webhook URL 不能为空")
    if card_payload.get("msg_type") != "interactive":
        raise ValueError("飞书消息必须使用 interactive 类型")
    if max_attempts < 1:
        raise ValueError("max_attempts 必须大于等于 1")

    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(webhook_url, json=card_payload, timeout=timeout)
        except requests.RequestException as exc:
            if attempt == max_attempts:
                LOGGER.error("飞书 Webhook 网络请求失败，已尝试 %d 次：%s", attempt, exc)
                raise RuntimeError(f"飞书 Webhook 网络请求失败，已重试{attempt}次：{exc}") from exc
            LOGGER.warning(
                "飞书 Webhook 网络请求失败，第 %d/%d 次：%s",
                attempt,
                max_attempts,
                exc,
            )
            if retry_delay > 0:
                time.sleep(retry_delay)
            continue

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            LOGGER.error("飞书 Webhook HTTP错误：status=%s", response.status_code)
            raise RuntimeError(f"飞书 Webhook HTTP错误：{response.status_code}") from exc

        try:
            result = response.json()
        except ValueError as exc:
            raise RuntimeError("飞书 Webhook 返回内容不是有效 JSON") from exc
        code = result.get("code", result.get("StatusCode", 0))
        if code != 0:
            message = result.get("msg", result.get("StatusMessage", "未知错误"))
            LOGGER.error("飞书 Webhook 业务错误：code=%s, message=%s", code, message)
            raise RuntimeError(f"飞书 Webhook 推送失败：code={code}, message={message}")
        return result

    raise RuntimeError("飞书 Webhook 推送失败")  # pragma: no cover


def main() -> None:
    parser = argparse.ArgumentParser(description="发送公众号运营日报到飞书")
    parser.add_argument("--report", type=Path, default=Path("report.json"))
    parser.add_argument("--analysis", type=Path, default=Path("ai_analysis.json"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env(require_feishu=True)
    report = load_report(args.report)
    analysis = load_ai_analysis(args.analysis)
    send_card(settings.feishu_webhook_url, build_card(report, analysis))
    print(f"飞书日报推送成功：{report['date']}")


if __name__ == "__main__":
    main()
