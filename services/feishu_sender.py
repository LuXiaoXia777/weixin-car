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
from services.report_visualizer import generate_report_charts


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


def _image(image_key: str, alt: str) -> dict[str, Any]:
    return {
        "tag": "img",
        "img_key": image_key,
        "alt": {"tag": "plain_text", "content": alt},
        "mode": "fit_horizontal",
    }


def _score_icon(score: int) -> str:
    return "🟢" if score >= 70 else "🟡" if score >= 50 else "🔴"


def build_card(
    report: dict[str, Any],
    analysis: AIAnalysisResult,
    *,
    chart_image_keys: dict[str, str] | None = None,
) -> dict[str, Any]:
    """生成可直接发送给飞书群机器人的卡片请求体。"""
    overview = report.get("overview") or {}
    score = report.get("account_score") or {"score": 0, "level": "数据不足"}
    hot = report.get("hot_article_analysis") or {}
    top5 = report.get("top5_articles") or []
    chart_image_keys = chart_image_keys or {}
    suggestions = "\n\n".join(
        f"**{index}. {_clean(item.title)}**\n"
        f"为什么推荐：{_clean(item.reason)}\n"
        f"参考数据：{_clean(item.reference_data)}\n"
        f"预计表现：{_clean(item.expected_performance)}"
        for index, item in enumerate(analysis.tomorrow_suggestions, start=1)
    )
    best_content = (
        f"🔥 **{_clean(hot.get('title') or analysis.best_article.title)}**\n"
        f"阅读人数：{_clean(hot.get('views'))}\n"
        f"超过文章平均：{_clean(hot.get('multiple'))}\n"
        f"主要流量：{_clean(hot.get('traffic_source'))}\n\n"
        f"**爆款原因**\n"
        + "\n".join(f"{index}. {_clean(reason)}" for index, reason in enumerate(hot.get("reason") or [], 1))
        + f"\n可复用公式：{_clean(hot.get('formula'))}"
    )
    top5_content = "\n".join(
        f"**TOP{index}**　{_clean(row.get('title'))}\n"
        f"阅读 {_clean(row.get('views'))}｜{_clean(row.get('category'))}"
        for index, row in enumerate(top5, 1)
    )
    pattern_content = "\n".join(
        f"{index}. {_clean(pattern)}"
        for index, pattern in enumerate(analysis.weekly_content_patterns, 1)
    )

    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "plain_text",
                "content": f"数据日期：{_clean(report.get('date'))}",
            },
        },
        {"tag": "hr"},
        _heading("① 今日健康度"),
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**{score.get('score', 0)}分 {_score_icon(score.get('score', 0))}**　{_clean(score.get('level'))}",
            },
        },
        {"tag": "hr"},
        _heading("② 核心指标"),
        {
            "tag": "div",
            "fields": [
                _field("阅读", _metric(overview.get("views"))),
                _field("分享", _metric(overview.get("shares"))),
                _field("收藏", _metric(overview.get("favorites"))),
                _field("发布", _metric(overview.get("publish_count"))),
            ],
        },
        {"tag": "hr"},
        _heading("③ 近7天阅读趋势"),
    ]
    if chart_image_keys.get("trend"):
        elements.append(_image(chart_image_keys["trend"], "近7天阅读趋势图"))
    else:
        trend_text = "　".join(
            f"{str(row.get('date', ''))[5:]}：{_clean(row.get('views'))}"
            for row in report.get("daily_trend") or []
        )
        elements.append({"tag": "div", "text": {"tag": "plain_text", "content": trend_text or "数据不足"}})
    elements.extend(
        [
            {"tag": "hr"},
            _heading("④ 今日爆款"),
            {"tag": "div", "text": {"tag": "lark_md", "content": best_content}},
            {"tag": "hr"},
            _heading("⑤ TOP5文章排行"),
        ]
    )
    if chart_image_keys.get("top5"):
        elements.append(_image(chart_image_keys["top5"], "TOP5文章排行图"))
    elements.extend(
        [
            {"tag": "div", "text": {"tag": "lark_md", "content": top5_content or "数据不足"}},
            {"tag": "hr"},
            _heading("⑥ AI运营建议"),
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**本周内容规律**\n{pattern_content}"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**当前问题**\n{_clean(analysis.problems)}"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**明日建议**\n\n{suggestions}"}},
        ]
    )

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True, "enable_forward": True},
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": "🚗 车事人话公众号运营日报 2.0",
                },
            },
            "elements": elements,
        },
    }


def upload_card_image(app_id: str, app_secret: str, image_path: Path, *, timeout: int = 30) -> str:
    """使用飞书应用凭证上传卡片图片并返回 image_key。"""
    token_response = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=timeout,
    )
    token_response.raise_for_status()
    token_payload = token_response.json()
    if token_payload.get("code") != 0 or not token_payload.get("tenant_access_token"):
        raise RuntimeError(f"获取飞书 tenant_access_token 失败：{token_payload.get('msg', '未知错误')}")
    with image_path.open("rb") as image_file:
        response = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/images",
            headers={"Authorization": f"Bearer {token_payload['tenant_access_token']}"},
            data={"image_type": "message"},
            files={"image": (image_path.name, image_file, "image/png")},
            timeout=timeout,
        )
    response.raise_for_status()
    payload = response.json()
    image_key = (payload.get("data") or {}).get("image_key")
    if payload.get("code") != 0 or not image_key:
        raise RuntimeError(f"上传飞书卡片图片失败：{payload.get('msg', '未知错误')}")
    return image_key


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
    charts = generate_report_charts(report, Path("data/charts"))
    image_keys: dict[str, str] = {}
    if settings.feishu_app_id and settings.feishu_app_secret:
        image_keys = {
            name: upload_card_image(
                settings.feishu_app_id,
                settings.feishu_app_secret,
                path,
            )
            for name, path in charts.items()
        }
    else:
        LOGGER.warning(
            "未配置 FEISHU_APP_ID/FEISHU_APP_SECRET，本地图表已生成，"
            "飞书卡片将使用文字版趋势和排行"
        )
    send_card(
        settings.feishu_webhook_url,
        build_card(report, analysis, chart_image_keys=image_keys),
    )
    print(f"飞书日报推送成功：{report['date']}")


if __name__ == "__main__":
    main()
