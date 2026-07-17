"""基于 Supabase 真实数据生成确定性公众号运营指标报告。"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any
from zoneinfo import ZoneInfo

from database.client import SupabaseConfig, SupabaseRestClient
from services.latest_report_data import LatestReportData, load_latest_report_data


SHANGHAI = ZoneInfo("Asia/Shanghai")
SCORE_WEIGHTS = {
    "read_users": 0.40,
    "share_rate": 0.30,
    "favorite_rate": 0.10,
    "follower_efficiency": 0.20,
}


def _change(current: int | None, previous: int | None) -> dict[str, Any]:
    if current is None or previous is None:
        return {"value": current, "previous": previous, "change_rate": None}
    if previous == 0:
        rate = None if current else 0.0
    else:
        rate = round((current - previous) / previous, 4)
    return {"value": current, "previous": previous, "change_rate": rate}


def _publish_date(value: str) -> date:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(SHANGHAI).date()


def _topic(title: str) -> str:
    if any(word in title for word in ("对比", "比", "贵在哪", "贵了", "谁更")):
        return "横向对比"
    if any(word in title for word in ("值不值", "能不能买", "可以买", "买前", "等等")):
        return "买车建议"
    if any(word in title for word in ("上市", "发布", "预售", "今晚")):
        return "新车上市"
    if any(word in title for word in ("智驾", "电池", "平台", "技术", "新国标")):
        return "技术趋势"
    if any(word in title for word in ("避坑", "槽点", "问题", "坑")):
        return "用车避坑"
    return "其他"


class AnalysisService:
    def __init__(self, client: SupabaseRestClient, account_name: str = "车事人话") -> None:
        self.client = client
        self.account_name = account_name

    def _account_id(self) -> str:
        rows = self.client.request(
            "GET",
            "wechat_accounts",
            params={"select": "id", "name": f"eq.{self.account_name}", "limit": "1"},
        )
        if not rows:
            raise ValueError(f"Supabase 中找不到公众号：{self.account_name}")
        return rows[0]["id"]

    def _overview(self, account_id: str, report_date: date) -> dict[str, Any]:
        rows = self.client.request(
            "GET",
            "account_daily_stats",
            params={
                "select": "stat_date,views,shares,favorites,publish_count,collected_at",
                "account_id": f"eq.{account_id}",
                "stat_date": f"lte.{report_date.isoformat()}",
                "order": "stat_date.desc",
                "limit": "2",
            },
        )
        if not rows or rows[0]["stat_date"] != report_date.isoformat():
            raise ValueError(f"缺少 {report_date.isoformat()} 的账号每日数据")
        current = rows[0]
        previous = rows[1] if len(rows) > 1 else {}
        return {
            "views": _change(current.get("views"), previous.get("views")),
            "shares": _change(current.get("shares"), previous.get("shares")),
            "favorites": _change(current.get("favorites"), previous.get("favorites")),
            "publish_count": _change(current.get("publish_count"), previous.get("publish_count")),
            "collected_at": current["collected_at"],
        }

    def _articles(self, account_id: str) -> dict[str, dict[str, Any]]:
        rows = self.client.request(
            "GET",
            "articles",
            params={
                "select": "id,title,publish_time,category",
                "account_id": f"eq.{account_id}",
                "limit": "1000",
            },
        )
        return {row["id"]: row for row in rows or []}

    def _stats(self, report_date: date) -> list[dict[str, Any]]:
        return self.client.request(
            "GET",
            "article_stats",
            params={
                "select": "article_id,read_users,shares,new_followers",
                "stat_date": f"eq.{report_date.isoformat()}",
                "limit": "1000",
            },
        ) or []

    def _top_articles(
        self,
        stats: list[dict[str, Any]],
        articles: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        max_reads = max((row.get("read_users") or 0 for row in stats), default=0)
        ranked = []
        for row in stats:
            article = articles.get(row["article_id"])
            if not article:
                continue
            reads = row.get("read_users")
            shares = row.get("shares")
            followers = row.get("new_followers")
            share_rate = shares / reads if shares is not None and reads else None
            favorite_rate = None  # 当前官方导出无单篇收藏字段。
            follower_efficiency = followers / reads if followers is not None and reads else None

            components = {
                "read_users": (reads / max_reads if reads is not None and max_reads else None),
                "share_rate": share_rate,
                "favorite_rate": favorite_rate,
                "follower_efficiency": follower_efficiency,
            }
            score = sum(
                components[name] * weight * 100
                for name, weight in SCORE_WEIGHTS.items()
                if components[name] is not None
            )
            available_weight = sum(
                weight
                for name, weight in SCORE_WEIGHTS.items()
                if components[name] is not None
            )
            ranked.append(
                {
                    "title": article["title"],
                    "category": article.get("category") or _topic(article["title"]),
                    "read_users": reads,
                    "interactions": {
                        "shares": shares,
                        "share_rate": round(share_rate, 6) if share_rate is not None else None,
                        "favorites": None,
                        "favorite_rate": None,
                        "new_followers": followers,
                        "follower_efficiency": (
                            round(follower_efficiency, 6)
                            if follower_efficiency is not None
                            else None
                        ),
                    },
                    "score": round(score, 2),
                    "score_completeness": round(available_weight, 2),
                    "missing_metrics": [
                        name for name, value in components.items() if value is None
                    ],
                }
            )
        ranked.sort(key=lambda item: (item["score"], item["read_users"] or 0), reverse=True)
        for index, item in enumerate(ranked, start=1):
            item["rank"] = index
        return ranked

    def _trend_analysis(
        self,
        account_id: str,
        report_date: date,
        articles: dict[str, dict[str, Any]],
        stats: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        start = report_date - timedelta(days=6)
        daily = self.client.request(
            "GET",
            "account_daily_stats",
            params={
                "select": "stat_date,views,shares,publish_count",
                "account_id": f"eq.{account_id}",
                "stat_date": f"gte.{start.isoformat()}",
                "order": "stat_date.asc",
                "limit": "7",
            },
        ) or []
        recent_ids = {
            article_id
            for article_id, article in articles.items()
            if start <= _publish_date(article["publish_time"]) <= report_date
        }
        recent_stats = [row for row in stats if row["article_id"] in recent_ids]
        topic_reads: dict[str, list[int]] = defaultdict(list)
        for row in recent_stats:
            article = articles[row["article_id"]]
            if row.get("read_users") is not None:
                topic_reads[_topic(article["title"])].append(row["read_users"])
        topics = sorted(
            (
                {
                    "topic": topic,
                    "article_count": len(values),
                    "average_read_users": round(mean(values)),
                }
                for topic, values in topic_reads.items()
            ),
            key=lambda item: item["average_read_users"],
            reverse=True,
        )
        return [
            {"metric": "article_count", "value": len(recent_ids)},
            {
                "metric": "average_read_users",
                "value": round(mean(row["read_users"] for row in recent_stats if row.get("read_users") is not None))
                if any(row.get("read_users") is not None for row in recent_stats)
                else None,
            },
            {"metric": "high_performance_topics", "value": topics[:3]},
            {"metric": "daily_account_data", "value": daily},
        ]

    def _channel_analysis(
        self,
        report_date: date,
        articles: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows = self.client.request(
            "GET",
            "article_channel_stats",
            params={
                "select": "article_id,channel,read_users,read_percent",
                "stat_date": f"eq.{report_date.isoformat()}",
                "limit": "5000",
            },
        ) or []
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[row["article_id"]].append(row)
        result = []
        for article_id, channel_rows in grouped.items():
            article = articles.get(article_id)
            if not article:
                continue
            main = max(channel_rows, key=lambda row: row.get("read_users") or 0)
            result.append(
                {
                    "title": article["title"],
                    "main_channel": main["channel"],
                    "read_users": main.get("read_users"),
                    "read_percent": main.get("read_percent"),
                }
            )
        return sorted(result, key=lambda item: item["read_users"] or 0, reverse=True)

    @staticmethod
    def _daily_trend(trend_analysis: list[dict[str, Any]]) -> list[dict[str, Any]]:
        daily = next(
            (row["value"] for row in trend_analysis if row["metric"] == "daily_account_data"),
            [],
        )
        return [
            {
                "date": row["stat_date"],
                "views": row.get("views"),
                "shares": row.get("shares"),
                "articles": row.get("publish_count"),
            }
            for row in daily
        ]

    @staticmethod
    def _account_score(
        overview: dict[str, Any],
        daily_trend: list[dict[str, Any]],
        top_articles: list[dict[str, Any]],
    ) -> dict[str, Any]:
        reasons: list[str] = []
        view_change = overview["views"].get("change_rate")
        if view_change is None:
            reading_score = 0
            reasons.append("阅读环比缺失，阅读趋势项计0分")
        elif view_change >= 0.10:
            reading_score = 25
            reasons.append(f"阅读环比增长{view_change * 100:.1f}%，阅读趋势25/25")
        elif view_change >= 0:
            reading_score = 20
            reasons.append(f"阅读环比增长{view_change * 100:.1f}%，阅读趋势20/25")
        elif view_change >= -0.10:
            reading_score = 15
            reasons.append(f"阅读环比下降{abs(view_change) * 100:.1f}%，阅读趋势15/25")
        elif view_change >= -0.25:
            reading_score = 8
            reasons.append(f"阅读环比下降{abs(view_change) * 100:.1f}%，阅读趋势8/25")
        else:
            reading_score = 3
            reasons.append(f"阅读环比下降{abs(view_change) * 100:.1f}%，阅读趋势3/25")

        views = overview["views"].get("value")
        shares = overview["shares"].get("value")
        favorites = overview["favorites"].get("value")
        share_rate = shares / views if shares is not None and views else None
        favorite_rate = favorites / views if favorites is not None and views else None
        share_score = round(min(share_rate / 0.02, 1) * 20) if share_rate is not None else 0
        favorite_score = (
            round(min(favorite_rate / 0.01, 1) * 15) if favorite_rate is not None else 0
        )
        reasons.append(
            f"分享率{share_rate * 100:.2f}%，分享项{share_score}/20"
            if share_rate is not None
            else "分享率数据缺失，分享项计0分"
        )
        reasons.append(
            f"收藏率{favorite_rate * 100:.2f}%，收藏项{favorite_score}/15"
            if favorite_rate is not None
            else "收藏率数据缺失，收藏项计0分"
        )

        published = sum(row.get("articles") or 0 for row in daily_trend)
        publish_score = min(published, 5) * 4
        reasons.append(f"近7天发布{published}篇，发布频率{publish_score}/20")

        reads = [row["read_users"] for row in top_articles if row.get("read_users") is not None]
        multiple = max(reads) / mean(reads) if reads and mean(reads) else None
        hot_score = round(min((multiple or 0) / 3, 1) * 20)
        reasons.append(
            f"最高阅读为文章均值的{multiple:.1f}倍，爆款表现{hot_score}/20"
            if multiple is not None
            else "文章阅读数据缺失，爆款表现计0分"
        )
        score = min(100, reading_score + share_score + favorite_score + publish_score + hot_score)
        level = "优秀" if score >= 85 else "良好" if score >= 70 else "需关注" if score >= 50 else "待改善"
        return {"score": score, "level": level, "reasons": reasons}

    @staticmethod
    def _hot_article_analysis(
        top_articles: list[dict[str, Any]],
        channel_analysis: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not top_articles:
            return None
        best = top_articles[0]
        reads = [row["read_users"] for row in top_articles if row.get("read_users") is not None]
        average = mean(reads) if reads else None
        multiple = best.get("read_users") / average if average and best.get("read_users") is not None else None
        channel = next(
            (row.get("main_channel") for row in channel_analysis if row["title"] == best["title"]),
            None,
        )
        title = best["title"]
        reasons: list[str] = []
        formula_parts = ["车型"]
        if any(token in title for token in ("贵", "万", "价格", "预算", "性价比")):
            reasons.append("标题包含价格或预算决策信息")
            formula_parts.append("价格差")
        if any(token in title for token in ("为什么", "到底", "值不值", "能买吗", "买前", "谁更")):
            reasons.append("标题直接回答购买决策问题")
            formula_parts.append("购买疑问")
        if any(char.isdigit() for char in title):
            reasons.append("标题使用具体数字降低信息模糊度")
            formula_parts.append("数字清单")
        if channel:
            reasons.append(f"主要流量来源为{channel}")
        if not reasons:
            reasons.append("仅能确认阅读表现领先，标题驱动因素数据不足")
        return {
            "title": title,
            "views": best.get("read_users"),
            "multiple": f"{multiple:.1f}x" if multiple is not None else None,
            "traffic_source": channel,
            "reason": reasons,
            "formula": "+".join(dict.fromkeys(formula_parts)),
        }

    def build_report(self) -> dict[str, Any]:
        marker: LatestReportData = load_latest_report_data(self.client, self.account_name)
        account_id = self._account_id()
        articles = self._articles(account_id)
        stats = self._stats(marker.stat_date)
        overview = self._overview(account_id, marker.stat_date)
        top_articles = self._top_articles(stats, articles)
        trend_analysis = self._trend_analysis(account_id, marker.stat_date, articles, stats)
        channel_analysis = self._channel_analysis(marker.stat_date, articles)
        daily_trend = self._daily_trend(trend_analysis)
        return {
            "date": marker.stat_date.isoformat(),
            "overview": overview,
            "account_score": self._account_score(overview, daily_trend, top_articles),
            "daily_trend": daily_trend,
            "hot_article_analysis": self._hot_article_analysis(top_articles, channel_analysis),
            "top5_articles": [
                {
                    "title": row["title"],
                    "views": row.get("read_users"),
                    "category": row["category"],
                }
                for row in top_articles[:5]
            ],
            "top_articles": top_articles,
            "trend_analysis": trend_analysis,
            "channel_analysis": channel_analysis,
        }

    def write_report(self, output_path: Path) -> dict[str, Any]:
        report = self.build_report()
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return report


def main() -> None:
    parser = argparse.ArgumentParser(description="生成公众号运营指标 JSON 报告")
    parser.add_argument("--output", type=Path, default=Path("report.json"))
    parser.add_argument("--account-name", default="车事人话")
    args = parser.parse_args()
    client = SupabaseRestClient(SupabaseConfig.from_env())
    report = AnalysisService(client, args.account_name).write_report(args.output)
    print(f"已生成 {report['date']} 运营指标报告：{args.output.resolve()}")


if __name__ == "__main__":
    main()
