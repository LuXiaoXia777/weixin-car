"""公众号数据读取层，未来可替换成微信公众号 API 数据源。"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path


@dataclass(frozen=True)
class Article:
    date: date
    title: str
    category: str
    views: int
    likes: int
    shares: int
    comments: int
    new_followers: int

    def to_dict(self) -> dict:
        result = asdict(self)
        result["date"] = self.date.isoformat()
        return result


INTEGER_FIELDS = ("views", "likes", "shares", "comments", "new_followers")
REQUIRED_FIELDS = ("date", "title", "category", *INTEGER_FIELDS)


def load_articles(path: Path) -> list[Article]:
    if not path.exists():
        raise FileNotFoundError(f"找不到数据文件：{path}")

    articles: list[Article] = []
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        missing = set(REQUIRED_FIELDS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV 缺少字段：{', '.join(sorted(missing))}")

        for line_number, row in enumerate(reader, start=2):
            try:
                articles.append(
                    Article(
                        date=date.fromisoformat(row["date"].strip()),
                        title=row["title"].strip(),
                        category=row["category"].strip(),
                        **{field: int(row[field]) for field in INTEGER_FIELDS},
                    )
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(f"CSV 第 {line_number} 行格式错误：{exc}") from exc

    if not articles:
        raise ValueError("CSV 中没有文章数据")
    return sorted(articles, key=lambda item: item.date)


def latest_seven_days(articles: list[Article]) -> list[Article]:
    """以 CSV 最新日期为截止日，返回最近 7 个自然日的数据。"""
    latest_date = max(article.date for article in articles)
    start_date = latest_date - timedelta(days=6)
    return [article for article in articles if start_date <= article.date <= latest_date]


def daily_totals(articles: list[Article], target_date: date) -> dict[str, int]:
    daily = [article for article in articles if article.date == target_date]
    return {
        "articles": len(daily),
        "views": sum(article.views for article in daily),
        "likes": sum(article.likes for article in daily),
        "shares": sum(article.shares for article in daily),
        "comments": sum(article.comments for article in daily),
        "new_followers": sum(article.new_followers for article in daily),
    }
