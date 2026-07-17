"""AI 公众号数据分析机器人入口。"""

from __future__ import annotations

import argparse
import logging
import sys

from config import Settings
from services.ai_analysis import analyze_articles
from services.data_loader import daily_totals, latest_seven_days, load_articles
from services.feishu import build_report, send_report


logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成并推送微信公众号 AI 日报")
    parser.add_argument("--dry-run", action="store_true", help="生成日报但不发送到飞书")
    return parser.parse_args()


def run(*, dry_run: bool = False) -> None:
    settings = Settings.from_env(require_feishu=not dry_run)
    articles = load_articles(settings.articles_csv)
    seven_days = latest_seven_days(articles)
    report_date = max(article.date for article in seven_days)
    report_articles = [article for article in seven_days if article.date == report_date]
    totals = daily_totals(seven_days, report_date)

    LOGGER.info("已读取 %s 条最近7天文章数据", len(seven_days))
    analysis = analyze_articles(
        seven_days,
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        prompt_file=settings.prompt_file,
    )
    best = next(
        (article for article in report_articles if article.title == analysis.best_article),
        max(
            report_articles,
            key=lambda item: (
                item.views,
                item.likes + item.shares + item.comments,
                item.new_followers,
            ),
        ),
    )
    markdown = build_report(report_date, totals, best, analysis)

    if dry_run:
        print(markdown)
        LOGGER.info("本地测试完成，未发送飞书消息")
        return
    send_report(settings.feishu_webhook_url, markdown)
    LOGGER.info("日报已成功推送到飞书")


if __name__ == "__main__":
    try:
        run(dry_run=parse_args().dry_run)
    except Exception:
        LOGGER.exception("日报任务执行失败")
        sys.exit(1)
