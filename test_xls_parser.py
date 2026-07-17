"""真实微信 .xls 解析与 Supabase 写入测试。"""

from __future__ import annotations

from pathlib import Path
import unittest

from services.supabase_writer import SupabaseWechatWriter
from services.wechat_xls_parser import parse_wechat_xls


REAL_XLS = Path(__file__).resolve().parent / "data/import/wechat_content_2026-07-16.xls"


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method, table, **kwargs):
        self.calls.append((method, table, kwargs))
        if table == "wechat_accounts":
            return [{"id": "account-1"}]
        if table == "import_runs" and method == "GET":
            return []
        if table == "import_runs" and method == "POST":
            return [{"id": "run-1"}]
        if table == "articles":
            return [
                {"id": f"article-{index}", "source_key": row["source_key"]}
                for index, row in enumerate(kwargs["json"], start=1)
            ]
        return None


@unittest.skipUnless(REAL_XLS.exists(), "本机尚未下载真实微信 .xls")
class WechatXlsParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.batch = parse_wechat_xls(REAL_XLS)

    def test_real_xls_and_three_regions_are_recognized(self):
        self.assertEqual(self.batch.period_start.isoformat(), "2026-06-17")
        self.assertEqual(self.batch.period_end.isoformat(), "2026-07-16")
        self.assertEqual(len(self.batch.account_channel_trends), 240)
        self.assertEqual(len(self.batch.account_content_stats), 30)
        self.assertGreater(len(self.batch.article_channels), 0)

    def test_real_xls_parsed_counts_are_correct(self):
        self.assertEqual(len(self.batch.articles), 21)
        self.assertEqual(len(self.batch.article_totals), 13)
        self.assertEqual(len(self.batch.article_channels), 81)

    def test_missing_article_metrics_are_not_invented(self):
        total = self.batch.article_totals[0]
        self.assertIsNotNone(total.read_users)
        article = self.batch.articles[0]
        self.assertIsNotNone(article.title)

    def test_supabase_writer_writes_all_supported_tables(self):
        client = FakeSupabaseClient()
        result = SupabaseWechatWriter(client).write("车事人话", self.batch)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["articles"], 21)
        self.assertEqual(result["article_stats"], 13)
        self.assertEqual(result["account_daily_stats"], 30)
        self.assertEqual(result["article_channel_stats"], 81)
        self.assertEqual(result["account_channel_trends_skipped"], 240)
        tables = [table for _, table, _ in client.calls]
        for table in ("articles", "article_stats", "account_daily_stats", "article_channel_stats"):
            self.assertIn(table, tables)

        stats_call = next(call for call in client.calls if call[1] == "article_stats")
        stats = stats_call[2]["json"][0]
        self.assertIsNone(stats["views"])
        self.assertIsNone(stats["likes"])
        self.assertIsNotNone(stats["read_users"])


if __name__ == "__main__":
    unittest.main()
