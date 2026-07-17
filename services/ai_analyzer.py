"""读取确定性指标报告，并调用 DeepSeek 生成中文运营分析。"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel, Field, ValidationError

from config import Settings


LOGGER = logging.getLogger(__name__)


class BestArticle(BaseModel):
    title: str
    reason: str


class AIAnalysisResult(BaseModel):
    summary: str
    best_article: BestArticle
    content_trend: str
    problems: str
    tomorrow_suggestions: list[str] = Field(min_length=3, max_length=3)


SYSTEM_PROMPT = """你是微信公众号运营分析师，服务于汽车公众号“车事人话”。
请根据输入的真实指标，分析今日数据、昨日环比、爆款文章排行、最近7天趋势和渠道来源。

规则：
1. 只使用输入中存在的数据，禁止编造数字、因果、用户画像或趋势。
2. 字段为 null、missing_metrics 中列出或证据不足时，必须明确写“数据不足，暂无法判断”。
3. 最佳文章必须来自 top_articles，理由必须引用真实标题和指标。
4. 明日建议必须结合输入中的具体文章、主题、渠道或数值，不能推荐泛泛新闻。
5. 使用简洁中文，不输出 Markdown，不输出 JSON 以外的内容。
"""


def load_report(report_path: Path) -> dict[str, Any]:
    """读取并检查 analysis_service 生成的报告。"""
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"找不到指标报告：{report_path.resolve()}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"指标报告不是有效 JSON：{report_path.resolve()}") from exc

    required = {"date", "overview", "top_articles", "trend_analysis", "channel_analysis"}
    missing = sorted(required - report.keys()) if isinstance(report, dict) else sorted(required)
    if missing:
        raise ValueError(f"指标报告缺少字段：{', '.join(missing)}")
    return report


def _extract_content(payload: Any) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("DeepSeek 响应缺少 choices[0].message.content") from exc
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("DeepSeek 响应内容为空")
    content = content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    return content


def analyze_report(
    report: dict[str, Any],
    *,
    api_key: str,
    model: str,
    base_url: str = "https://api.deepseek.com",
    timeout: int = 60,
) -> AIAnalysisResult:
    """调用 DeepSeek，并将结果验证为固定 JSON 结构。"""
    schema = AIAnalysisResult.model_json_schema()
    user_prompt = (
        "请生成运营分析。严格遵守以下 JSON Schema，并且只返回一个 JSON 对象：\n"
        f"{json.dumps(schema, ensure_ascii=False)}\n\n"
        "真实运营指标：\n"
        f"{json.dumps(report, ensure_ascii=False, indent=2)}"
    )
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
                "stream": False,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        LOGGER.exception("DeepSeek API 请求失败")
        raise RuntimeError(f"DeepSeek API 请求失败：{exc}") from exc
    except ValueError as exc:
        raise RuntimeError("DeepSeek API 返回的响应体不是有效 JSON") from exc

    content = _extract_content(payload)
    try:
        return AIAnalysisResult.model_validate_json(content)
    except (ValidationError, ValueError) as exc:
        raise RuntimeError(f"DeepSeek 分析结果 JSON 解析或字段校验失败：{exc}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="使用 DeepSeek 分析公众号指标报告")
    parser.add_argument("report", type=Path, help="analysis_service 生成的 report.json")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env(require_feishu=False)
    report = load_report(args.report)
    result = analyze_report(
        report,
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
    )
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
