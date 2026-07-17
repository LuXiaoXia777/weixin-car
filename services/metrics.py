"""确定性计算日报指标、文章评分和内容分类。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from services.data_loader import Article, daily_totals


CONTENT_CATEGORIES = ("新车上市", "横向对比", "买车建议", "技术趋势", "用车避坑")


@dataclass(frozen=True)
class ArticlePerformance:
    article: Article
    content_type: str
    interaction_rate: float
    follower_efficiency: float
    score: float

    def to_context(self) -> dict:
        return {
            **self.article.to_dict(),
            "content_type": self.content_type,
            "interaction_rate": round(self.interaction_rate, 4),
            "follower_efficiency": round(self.follower_efficiency, 4),
            "score": round(self.score, 1),
        }


@dataclass(frozen=True)
class ReportMetrics:
    report_date: date
    overview: list[dict]
    rankings: list[ArticlePerformance]
    categories: list[dict]

    def to_ai_context(self) -> dict:
        return {
            "report_date": self.report_date.isoformat(),
            "overview": self.overview,
            "article_rankings": [item.to_context() for item in self.rankings],
            "category_metrics": self.categories,
            "scoring_rule": "阅读量40%，互动率30%，涨粉效率30%；各项按近7天最大值归一化",
        }


def classify_content(article: Article) -> str:
    text = f"{article.title} {article.category}"
    if any(word in text for word in ("避坑", "坑", "故障", "保养", "费用")):
        return "用车避坑"
    if any(word in text for word in ("对比", "相比", "比", "差多少", "贵", "值不值")):
        return "横向对比"
    if any(word in text for word in ("上市", "发布", "首月", "新车")):
        return "新车上市"
    if any(word in text for word in ("技术", "智驾", "平台", "电池", "800V")):
        return "技术趋势"
    return "买车建议"


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _change(current: float, previous: float | None, *, points: bool = False) -> str:
    if previous is None:
        return "数据不足"
    if points:
        return f"{(current - previous) * 100:+.2f}个百分点"
    if previous == 0:
        return "上期为0" if current else "0.0%"
    return f"{(current - previous) / previous * 100:+.1f}%"


def _overview_analysis(current: float, previous: float | None) -> str:
    if previous is None:
        return "数据不足，暂无法判断"
    if current > previous:
        return "高于昨日"
    if current < previous:
        return "低于昨日"
    return "与昨日持平"


def _build_overview(articles: list[Article], report_date: date) -> list[dict]:
    current = daily_totals(articles, report_date)
    previous_date = report_date - timedelta(days=1)
    previous_articles = [item for item in articles if item.date == previous_date]
    previous = daily_totals(articles, previous_date) if previous_articles else None

    current_values = {
        "发布文章": float(current["articles"]),
        "总阅读": float(current["views"]),
        "平均阅读": current["views"] / current["articles"] if current["articles"] else 0.0,
        "点赞率": _rate(current["likes"], current["views"]),
        "分享率": _rate(current["shares"], current["views"]),
        "新增粉丝": float(current["new_followers"]),
    }
    previous_values = None
    if previous:
        previous_values = {
            "发布文章": float(previous["articles"]),
            "总阅读": float(previous["views"]),
            "平均阅读": previous["views"] / previous["articles"] if previous["articles"] else 0.0,
            "点赞率": _rate(previous["likes"], previous["views"]),
            "分享率": _rate(previous["shares"], previous["views"]),
            "新增粉丝": float(previous["new_followers"]),
        }

    rows = []
    for metric, value in current_values.items():
        old_value = previous_values[metric] if previous_values else None
        is_rate = metric in ("点赞率", "分享率")
        if is_rate:
            display = f"{value * 100:.2f}%"
        elif metric in ("发布文章", "新增粉丝"):
            display = f"{int(value):,}"
        else:
            display = f"{value:,.0f}"
        rows.append(
            {
                "metric": metric,
                "value": display,
                "change": _change(value, old_value, points=is_rate),
                "analysis": _overview_analysis(value, old_value),
            }
        )
    return rows


def _build_rankings(articles: list[Article]) -> list[ArticlePerformance]:
    raw = []
    for article in articles:
        interaction_rate = _rate(article.likes + article.shares + article.comments, article.views)
        follower_efficiency = _rate(article.new_followers, article.views)
        raw.append((article, interaction_rate, follower_efficiency))

    max_views = max((item[0].views for item in raw), default=1) or 1
    max_interaction = max((item[1] for item in raw), default=1.0) or 1.0
    max_followers = max((item[2] for item in raw), default=1.0) or 1.0
    rankings = [
        ArticlePerformance(
            article=article,
            content_type=classify_content(article),
            interaction_rate=interaction_rate,
            follower_efficiency=follower_efficiency,
            score=(
                article.views / max_views * 40
                + interaction_rate / max_interaction * 30
                + follower_efficiency / max_followers * 30
            ),
        )
        for article, interaction_rate, follower_efficiency in raw
    ]
    return sorted(rankings, key=lambda item: item.score, reverse=True)


def _build_categories(rankings: list[ArticlePerformance]) -> list[dict]:
    rows = []
    for category in CONTENT_CATEGORIES:
        items = [item for item in rankings if item.content_type == category]
        if not items:
            continue
        rows.append(
            {
                "content_type": category,
                "article_count": len(items),
                "average_views": round(sum(item.article.views for item in items) / len(items)),
                "average_interaction_rate": round(
                    sum(item.interaction_rate for item in items) / len(items), 4
                ),
                "average_new_followers": round(
                    sum(item.article.new_followers for item in items) / len(items), 1
                ),
            }
        )
    return rows


def build_report_metrics(articles: list[Article]) -> ReportMetrics:
    report_date = max(article.date for article in articles)
    rankings = _build_rankings(articles)
    return ReportMetrics(
        report_date=report_date,
        overview=_build_overview(articles, report_date),
        rankings=rankings,
        categories=_build_categories(rankings),
    )
