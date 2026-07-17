"""基于真实 Supabase 公众号数据的运营指标分析测试。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from database.client import PROJECT_ENV_FILE, SupabaseConfig, SupabaseRestClient
from services.analysis_service import AnalysisService


HAS_REAL_CONFIG = PROJECT_ENV_FILE.exists() or bool(
    os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)


@unittest.skipUnless(HAS_REAL_CONFIG, "缺少真实 Supabase 配置")
class RealSupabaseAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        client = SupabaseRestClient(SupabaseConfig.from_env())
        cls.service = AnalysisService(client)
        cls.report = cls.service.build_report()

    def test_unified_report_shape_and_latest_date(self):
        self.assertEqual(
            set(self.report),
            {
                "date", "overview", "account_score", "daily_trend",
                "hot_article_analysis", "top5_articles", "top_articles",
                "trend_analysis", "channel_analysis",
            },
        )
        self.assertEqual(self.report["date"], "2026-07-16")

    def test_overview_uses_real_daily_values_and_changes(self):
        overview = self.report["overview"]
        self.assertEqual(overview["views"]["value"], 6673)
        self.assertEqual(overview["views"]["previous"], 8864)
        self.assertLess(overview["views"]["change_rate"], 0)
        self.assertEqual(overview["shares"]["value"], 91)
        self.assertEqual(overview["favorites"]["value"], 5)
        self.assertEqual(overview["publish_count"]["value"], 2)

    def test_top_articles_are_ranked_without_inventing_missing_metrics(self):
        rows = self.report["top_articles"]
        self.assertGreater(len(rows), 0)
        self.assertEqual([row["rank"] for row in rows], list(range(1, len(rows) + 1)))
        self.assertEqual(rows[0]["read_users"], 14644)
        self.assertIn("favorite_rate", rows[0]["missing_metrics"])
        self.assertLessEqual(rows[0]["score_completeness"], 1.0)

    def test_seven_day_trend_and_channel_analysis_use_real_rows(self):
        trend = {row["metric"]: row["value"] for row in self.report["trend_analysis"]}
        self.assertGreater(trend["article_count"], 0)
        self.assertGreater(trend["average_read_users"], 0)
        self.assertGreater(len(trend["daily_account_data"]), 0)
        self.assertGreater(len(self.report["channel_analysis"]), 0)
        self.assertEqual(self.report["channel_analysis"][0]["main_channel"], "推荐")

    def test_dashboard_2_fields_are_data_driven(self):
        self.assertGreaterEqual(self.report["account_score"]["score"], 0)
        self.assertLessEqual(self.report["account_score"]["score"], 100)
        self.assertEqual(len(self.report["daily_trend"]), 7)
        self.assertLessEqual(len(self.report["top5_articles"]), 5)
        hot = self.report["hot_article_analysis"]
        self.assertEqual(hot["title"], self.report["top_articles"][0]["title"])
        self.assertTrue(hot["multiple"].endswith("x"))

    def test_report_json_is_written(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            report = self.service.write_report(output)
            saved = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(saved, report)


if __name__ == "__main__":
    unittest.main()
