"""调用 DeepSeek Chat Completions API 生成结构化运营分析。"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field
import requests

from services.data_loader import Article
from services.metrics import ReportMetrics


class ArticleJudgment(BaseModel):
    title: str
    judgment: str = Field(description="包含标题优势、点击原因、是否值得复制，60字以内")


class CategoryJudgment(BaseModel):
    content_type: str
    judgment: str = Field(description="必须引用该类型的具体指标，50字以内")


class BlockbusterAnalysis(BaseModel):
    title_structure: str
    user_pain: str
    click_reason: str
    content_value: str
    replicable_formula: str


class InterestTrend(BaseModel):
    trend: str
    data_basis: str
    judgment: str


class TopicSuggestion(BaseModel):
    priority: str
    title: str
    user_need: str
    reason: str


class OperatingAdvice(BaseModel):
    advice: str
    reason: str


class AnalysisResult(BaseModel):
    best_article: str = Field(description="表现最好文章的标题")
    article_judgments: list[ArticleJudgment]
    category_judgments: list[CategoryJudgment]
    blockbuster: BlockbusterAnalysis
    trends: list[InterestTrend] = Field(min_length=2, max_length=2)
    suggestions: list[TopicSuggestion] = Field(min_length=3, max_length=3)
    advice: list[OperatingAdvice] = Field(min_length=3, max_length=3)


def analyze_articles(
    articles: list[Article],
    *,
    api_key: str,
    model: str,
    base_url: str,
    prompt_file: Path,
    metrics: ReportMetrics,
    timeout: int = 60,
) -> AnalysisResult:
    prompt = prompt_file.read_text(encoding="utf-8")
    report_date = metrics.report_date.isoformat()
    schema = AnalysisResult.model_json_schema()
    user_prompt = (
        f"日报日期为 {report_date}。请根据下列已计算数据生成表格所需的短句。"
        "best_article 必须等于 article_rankings 第1名标题。"
        "所有判断必须引用输入中的标题或数字；证据不足时写‘数据不足，暂无法判断’。"
        "禁止使用‘用户关注度提升’‘热度增加’等无数据空话。"
        "article_judgments 要覆盖全部排行文章；category_judgments 要覆盖全部内容类型。"
        "advice 按继续增加、减少、测试新方向各1条。严格返回 JSON。\n"
        f"JSON Schema：{json.dumps(schema, ensure_ascii=False)}\n"
        f"运营数据：{json.dumps(metrics.to_ai_context(), ensure_ascii=False, indent=2)}"
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
            "max_tokens": 2600,
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
