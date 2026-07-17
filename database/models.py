"""导入层使用的类型，不将缺失统计值伪装成 0。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path


@dataclass(frozen=True)
class ArticleImportRow:
    source_key: str
    title: str
    publish_time: datetime
    stat_date: date
    url: str | None = None
    digest: str | None = None
    category: str | None = None
    external_id: str | None = None
    views: int | None = None
    read_users: int | None = None
    likes: int | None = None
    recommendations: int | None = None
    shares: int | None = None
    comments: int | None = None
    new_followers: int | None = None

    @property
    def has_stats(self) -> bool:
        return any(
            value is not None
            for value in (
                self.views,
                self.read_users,
                self.likes,
                self.recommendations,
                self.shares,
                self.comments,
                self.new_followers,
            )
        )


@dataclass(frozen=True)
class UserImportRow:
    stat_date: date
    new_followers: int | None = None
    cancel_followers: int | None = None
    net_followers: int | None = None


@dataclass(frozen=True)
class ImportBatch:
    source_file: Path
    file_hash: str
    articles: list[ArticleImportRow] = field(default_factory=list)
    user_stats: list[UserImportRow] = field(default_factory=list)

    @property
    def total_rows(self) -> int:
        return len(self.articles) + len(self.user_stats)
