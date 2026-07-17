"""日报2.0图表、JSON字段和飞书卡片测试。"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from services.ai_analyzer import AIAnalysisResult
from services.feishu_sender import build_card
from services.report_visualizer import generate_report_charts


REPORT = {
    "date": "2026-07-16",
    "overview": {
        "views": {"value": 6673, "previous": 8864, "change_rate": -0.2472},
        "shares": {"value": 91, "previous": 114, "change_rate": -0.2018},
        "favorites": {"value": 5, "previous": 11, "change_rate": -0.5455},
        "publish_count": {"value": 2, "previous": 1, "change_rate": 1.0},
    },
    "account_score": {"score": 82, "level": "良好", "reasons": ["真实评分原因"]},
    "daily_trend": [
        {"date": f"2026-07-{day:02d}", "views": 3000 + day * 100, "shares": 50 + day, "articles": 1}
        for day in range(10, 17)
    ],
    "hot_article_analysis": {
        "title": "15万SUV怎么选", "views": 14644, "multiple": "3.2x",
        "traffic_source": "推荐", "reason": ["价格对比", "购买决策需求"],
        "formula": "品牌+价格差+值不值得",
    },
    "top5_articles": [
        {"title": f"测试文章{i}", "views": 15000 - i * 2000, "category": "买车建议"}
        for i in range(1, 6)
    ],
    "top_articles": [],
    "trend_analysis": [],
    "channel_analysis": [],
}

ANALYSIS = AIAnalysisResult(
    summary="摘要",
    best_article={"title": "15万SUV怎么选", "reason": "阅读14644。"},
    content_trend="买车建议表现较好。",
    problems="收藏下降。",
    weekly_content_patterns=["价格标题领先", "买车建议领先", "减少泛趋势稿"],
    tomorrow_suggestions=[
        {"title": f"明日选题{i}", "reason": "基于TOP文章", "reference_data": "阅读14644", "expected_performance": "有望高于均值"}
        for i in range(1, 4)
    ],
)


class ReportVisualizerTests(unittest.TestCase):
    def test_report_2_json_fields_are_complete(self) -> None:
        required = {"account_score", "daily_trend", "hot_article_analysis", "top5_articles"}
        self.assertTrue(required.issubset(REPORT))
        self.assertEqual(len(REPORT["daily_trend"]), 7)
        self.assertEqual(len(REPORT["top5_articles"]), 5)

    def test_charts_generate_valid_png_files(self) -> None:
        with TemporaryDirectory() as directory:
            charts = generate_report_charts(REPORT, Path(directory))
            for path in charts.values():
                self.assertTrue(path.exists())
                self.assertGreater(path.stat().st_size, 1000)
                self.assertEqual(path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_feishu_card_contains_2_0_sections_and_images(self) -> None:
        card = build_card(REPORT, ANALYSIS, chart_image_keys={"trend": "img_1", "top5": "img_2"})
        serialized = str(card)
        self.assertEqual(card["msg_type"], "interactive")
        self.assertIn("今日健康度", serialized)
        self.assertIn("TOP5文章排行", serialized)
        self.assertIn("img_1", serialized)
        self.assertIn("明日选题1", serialized)


if __name__ == "__main__":
    unittest.main()
