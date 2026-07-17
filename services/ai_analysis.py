"""调用 OpenAI Responses API 生成结构化运营分析。"""

from __future__ import annotations

import json
from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel, Field

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
    prompt_file: Path,
) -> AnalysisResult:
    prompt = prompt_file.read_text(encoding="utf-8")
    article_data = [article.to_dict() for article in articles]
    report_date = max(article.date for article in articles).isoformat()
    client = OpenAI(api_key=api_key)

    response = client.responses.parse(
        model=model,
        instructions=prompt,
        input=(
            f"请分析以下过去7天的公众号文章数据。日报日期为 {report_date}。"
            "best_article 必须从日报日期的文章中选择。"
            "只依据给定数据判断，不要虚构热点、车型信息或指标。\n"
            + json.dumps(article_data, ensure_ascii=False, indent=2)
        ),
        text_format=AnalysisResult,
    )
    if response.output_parsed is None:
        raise RuntimeError("OpenAI 未返回可解析的分析结果")
    return response.output_parsed
