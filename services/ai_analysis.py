"""调用 DeepSeek Chat Completions API 生成结构化运营分析。"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field
import requests

from services.data_loader import Article


class AnalysisResult(BaseModel):
    summary: str = Field(description="过去7天整体表现总结")
    best_article: str = Field(description="表现最好文章的标题")
    reason: str = Field(description="最佳文章成为爆款或领先的原因")
    trend: str = Field(description="用户兴趣和内容方向变化")
    suggestions: list[str] = Field(min_length=3, max_length=5, description="明日选题建议")


def analyze_articles(
    articles: list[Article],
    *,
    api_key: str,
    model: str,
    base_url: str,
    prompt_file: Path,
    timeout: int = 60,
) -> AnalysisResult:
    prompt = prompt_file.read_text(encoding="utf-8")
    article_data = [article.to_dict() for article in articles]
    report_date = max(article.date for article in articles).isoformat()
    user_prompt = (
        f"请分析以下过去7天的公众号文章数据。日报日期为 {report_date}。"
        "best_article 必须从日报日期的文章中选择。"
        "只依据给定数据判断，不要虚构热点、车型信息或指标。"
        "请严格返回 JSON，字段必须为 summary、best_article、reason、trend、suggestions。\n"
        + json.dumps(article_data, ensure_ascii=False, indent=2)
    )
    response = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
            "max_tokens": 1200,
            "stream": False,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()

    try:
        content = payload["choices"][0]["message"]["content"]
        if not content:
            raise ValueError("响应内容为空")
        return AnalysisResult.model_validate_json(content)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError(f"DeepSeek 返回内容无法解析：{payload}") from exc
