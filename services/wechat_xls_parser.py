"""解析微信公众平台“内容分析 -> 下载数据明细”生成的 .xls。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import xlrd


SHANGHAI = ZoneInfo("Asia/Shanghai")
REGION_A_HEADERS = ("日期", "渠道", "阅读人数")
REGION_B_HEADERS = ("日期", "分享人数", "跳转阅读原文人数", "微信收藏人数", "发表篇数")
REGION_C_HEADERS = ("传播渠道", "发表日期", "内容标题", "阅读人数", "阅读人数占比")


def _clean_text(value: object) -> str | None:
    text = " ".join(str(value or "").split())
    return text or None


def _integer(value: object, field_name: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = float(str(value).replace(",", ""))
    except ValueError as exc:
        raise ValueError(f"{field_name}不是数字：{value}") from exc
    if not number.is_integer():
        raise ValueError(f"{field_name}不是整数：{value}")
    return int(number)


def _percent(value: object) -> float | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if text.endswith("%"):
        return float(text[:-1]) / 100
    return float(text)


def _date(value: object, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"{field_name}日期格式无法识别：{value}")


def article_source_key(title: str, publish_date: date) -> str:
    digest = hashlib.sha256(f"{title.strip()}|{publish_date.isoformat()}T00:00:00".encode()).hexdigest()
    return f"title_time:{digest}"


@dataclass(frozen=True)
class AccountChannelTrendRow:
    stat_date: date
    channel: str
    read_users: int | None


@dataclass(frozen=True)
class AccountDailyStatRow:
    stat_date: date
    views: int | None
    shares: int | None
    favorites: int | None
    publish_count: int | None


@dataclass(frozen=True)
class ArticleSourceRow:
    source_key: str
    title: str
    publish_date: date

    @property
    def publish_time(self) -> datetime:
        return datetime.combine(self.publish_date, datetime.min.time(), SHANGHAI)


@dataclass(frozen=True)
class ArticleTotalRow:
    source_key: str
    stat_date: date
    read_users: int | None


@dataclass(frozen=True)
class ArticleChannelRow:
    source_key: str
    stat_date: date
    channel: str
    read_users: int | None
    read_percent: float | None


@dataclass(frozen=True)
class WechatXlsBatch:
    source_file: Path
    file_hash: str
    period_start: date
    period_end: date
    account_channel_trends: list[AccountChannelTrendRow] = field(default_factory=list)
    account_daily_stats: list[AccountDailyStatRow] = field(default_factory=list)
    articles: list[ArticleSourceRow] = field(default_factory=list)
    article_totals: list[ArticleTotalRow] = field(default_factory=list)
    article_channel_stats: list[ArticleChannelRow] = field(default_factory=list)

    @property
    def account_content_stats(self) -> list[AccountDailyStatRow]:
        """兼容旧调用方；新入库表为 account_daily_stats。"""
        return self.account_daily_stats

    @property
    def article_channels(self) -> list[ArticleChannelRow]:
        """兼容旧调用方；新入库表为 article_channel_stats。"""
        return self.article_channel_stats

    @property
    def total_source_rows(self) -> int:
        return (
            len(self.account_channel_trends)
            + len(self.account_daily_stats)
            + len(self.article_totals)
            + len(self.article_channel_stats)
        )


def _find_header_groups(rows: list[list[object]]) -> tuple[int, int, int, int]:
    for row_index, row in enumerate(rows[:20]):
        normalized = [_clean_text(value) or "" for value in row]
        starts: list[int] = []
        complete = True
        for headers in (REGION_A_HEADERS, REGION_B_HEADERS, REGION_C_HEADERS):
            found = -1
            width = len(headers)
            for column in range(max(0, len(row) - width + 1)):
                if tuple(normalized[column : column + width]) == headers:
                    found = column
                    break
            if found < 0:
                complete = False
                break
            starts.append(found)
        if complete:
            return row_index, starts[0], starts[1], starts[2]
    raise ValueError("前20行中未找到微信内容分析的三个数据区域")


def _report_period(rows: list[list[object]], header_index: int) -> tuple[date, date]:
    for row in rows[: header_index + 1]:
        for value in row:
            text = _clean_text(value) or ""
            match = re.search(r"(\d{4}\.\d{2}\.\d{2})-(\d{4}\.\d{2}\.\d{2})", text)
            if match:
                return _date(match.group(1), "报表开始"), _date(match.group(2), "报表结束")
    raise ValueError("未从报表标题识别数据日期范围")


def parse_wechat_xls(path: Path) -> WechatXlsBatch:
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"找不到微信 .xls 文件：{path}")
    if path.suffix.lower() != ".xls":
        raise ValueError("微信真实报表解析器仅支持 .xls")

    workbook = xlrd.open_workbook(path, on_demand=True)
    try:
        if workbook.nsheets != 1:
            raise ValueError(f"微信内容分析报表应有1个 Sheet，实际为 {workbook.nsheets}")
        sheet = workbook.sheet_by_index(0)
        rows = [[sheet.cell_value(r, c) for c in range(sheet.ncols)] for r in range(sheet.nrows)]
    finally:
        workbook.release_resources()

    header_index, column_a, column_b, column_c = _find_header_groups(rows)
    period_start, period_end = _report_period(rows, header_index)
    trends: list[AccountChannelTrendRow] = []
    raw_account_stats: list[tuple[date, int | None, int | None, int | None]] = []
    article_by_key: dict[str, ArticleSourceRow] = {}
    totals: dict[str, ArticleTotalRow] = {}
    channels: dict[tuple[str, str], ArticleChannelRow] = {}

    for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        a = row[column_a : column_a + len(REGION_A_HEADERS)]
        if any(value not in (None, "") for value in a):
            trends.append(
                AccountChannelTrendRow(
                    stat_date=_date(a[0], f"第{row_number}行区域A日期"),
                    channel=_clean_text(a[1]) or "",
                    read_users=_integer(a[2], "区域A阅读人数"),
                )
            )

        b = row[column_b : column_b + len(REGION_B_HEADERS)]
        if any(value not in (None, "") for value in b):
            # 新表没有“跳转阅读原文人数”字段，不强行映射。
            raw_account_stats.append(
                (
                    _date(b[0], f"第{row_number}行区域B日期"),
                    _integer(b[1], "分享人数"),
                    _integer(b[3], "微信收藏人数"),
                    _integer(b[4], "发表篇数"),
                )
            )

        c = row[column_c : column_c + len(REGION_C_HEADERS)]
        if any(value not in (None, "") for value in c):
            channel = _clean_text(c[0])
            title = _clean_text(c[2])
            if not channel or not title:
                raise ValueError(f"第{row_number}行区域C缺少传播渠道或内容标题")
            publish_date = _date(c[1], f"第{row_number}行发表日期")
            source_key = article_source_key(title, publish_date)
            article_by_key[source_key] = ArticleSourceRow(source_key, title, publish_date)
            read_users = _integer(c[3], "区域C阅读人数")
            if channel == "全部":
                totals[source_key] = ArticleTotalRow(source_key, period_end, read_users)
            else:
                channels[(source_key, channel)] = ArticleChannelRow(
                    source_key=source_key,
                    stat_date=period_end,
                    channel=channel,
                    read_users=read_users,
                    read_percent=_percent(c[4]),
                )

    if not trends or not raw_account_stats or not article_by_key:
        raise ValueError("微信 .xls 三个数据区域未完整识别")
    daily_views = {
        row.stat_date: row.read_users
        for row in trends
        if row.channel == "全部"
    }
    account_stats = [
        AccountDailyStatRow(
            stat_date=stat_date,
            views=daily_views.get(stat_date),
            shares=shares,
            favorites=favorites,
            publish_count=publish_count,
        )
        for stat_date, shares, favorites, publish_count in raw_account_stats
    ]
    return WechatXlsBatch(
        source_file=path,
        file_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
        period_start=period_start,
        period_end=period_end,
        account_channel_trends=trends,
        account_daily_stats=account_stats,
        articles=list(article_by_key.values()),
        article_totals=list(totals.values()),
        article_channel_stats=list(channels.values()),
    )
