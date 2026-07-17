"""构建测试卡片；设置 FEISHU_WEBHOOK_URL 后发送到真实飞书群。"""

from __future__ import annotations

import os
from pathlib import Path

from services.ai_analysis import (
    AnalysisResult,
    ArticleJudgment,
    BlockbusterAnalysis,
    CategoryJudgment,
    InterestTrend,
    OperatingAdvice,
    TopicSuggestion,
)
from services.data_loader import latest_seven_days, load_articles
from services.feishu import build_report, send_report
from services.metrics import build_report_metrics


def build_test_card() -> dict:
    articles = latest_seven_days(load_articles(Path("data/articles.csv")))
    metrics = build_report_metrics(articles)
    analysis = AnalysisResult(
        best_article=metrics.rankings[0].article.title,
        article_judgments=[
            ArticleJudgment(
                title=item.article.title,
                judgment=f"{item.article.views:,}阅读；标题给出明确决策点，值得继续测试。",
            )
            for item in metrics.rankings
        ],
        category_judgments=[
            CategoryJudgment(
                content_type=row["content_type"],
                judgment=f"篇均{row['average_views']:,}阅读。",
            )
            for row in metrics.categories
        ],
        blockbuster=BlockbusterAnalysis(
            title_structure="风险提醒＋数字清单",
            user_pain="担心买车后出现隐性支出",
            click_reason="“最容易忽略”制造信息缺口",
            content_value="帮助读者提前计算真实用车成本",
            replicable_formula="目标人群＋最容易忽略＋数字清单",
        ),
        trends=[
            InterestTrend(
                trend="上涨方向",
                data_basis="横向对比类篇均3,186阅读、篇均35涨粉",
                judgment="购买决策型内容表现领先",
            ),
            InterestTrend(
                trend="下降方向",
                data_basis="技术趋势文章1,920阅读、19涨粉",
                judgment="纯技术解释的触达相对较弱",
            ),
        ],
        suggestions=[
            TopicSuggestion(
                priority="TOP1",
                title="15万预算买新能源SUV，哪3项配置不能省？",
                user_need="预算取舍",
                reason="价格配置内容表现领先",
            ),
            TopicSuggestion(
                priority="TOP2",
                title="智驾版贵3万，普通家庭到底值不值？",
                user_need="配置决策",
                reason="值不值标题已有数据验证",
            ),
            TopicSuggestion(
                priority="TOP3",
                title="新能源车买后才发现的5笔隐性费用",
                user_need="成本避坑",
                reason="费用避坑文章综合评分第一",
            ),
        ],
        advice=[
            OperatingAdvice(advice="继续增加横向对比", reason="篇均阅读和涨粉领先"),
            OperatingAdvice(advice="减少纯概念技术稿", reason="该类阅读相对较低"),
            OperatingAdvice(advice="测试预算分档选车", reason="价格差标题表现较好"),
        ],
    )
    return build_report(metrics, analysis)


def main() -> None:
    card = build_test_card()
    assert card["msg_type"] == "interactive"
    assert card["card"]["header"]["title"]["content"] == "🚗 车事人话｜公众号运营日报"
    assert any("fields" in element for element in card["card"]["elements"])

    webhook = os.getenv("FEISHU_WEBHOOK_URL", "").strip()
    if not webhook:
        print("飞书卡片结构验证成功；设置 FEISHU_WEBHOOK_URL 后可发送测试卡片。")
        return
    send_report(webhook, card)
    print("飞书 Interactive Card 测试发送成功")


if __name__ == "__main__":
    main()
