"""采集时间写入与最新日报基准测试。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch

from services.latest_report_data import load_latest_report_data
from services.supabase_writer import SupabaseWechatWriter
from services.wechat_xls_parser import parse_wechat_xls


REAL_XLS = Path(__file__).resolve().parent / "data/import/wechat_content_2026-07-16.xls"
MIGRATION = (
    Path(__file__).resolve().parent
    / "database/migrations/20260717_add_collected_at.sql"
)


class CollectedAtMigrationTests(unittest.TestCase):
    def test_all_wechat_data_tables_receive_collected_at(self):
        sql = " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())
        for table in (
            "articles",
            "article_stats",
            "user_stats",
            "account_content_stats",
            "article_channels",
            "account_daily_stats",
            "article_channel_stats",
        ):
            self.assertIn(f"public.{table}", sql)
        self.assertGreaterEqual(sql.count("collected_at timestamptz"), 7)


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def request(self, method, table, **kwargs):
        self.calls.append((method, table, kwargs))
        if table == "wechat_accounts":
            return [{"id": "account-1"}]
        if table == "import_runs" and method == "POST":
            return [{"id": "run-1"}]
        if table == "articles":
            return [
                {"id": f"article-{index}", "source_key": row["source_key"]}
                for index, row in enumerate(kwargs["json"], start=1)
            ]
        return None


@unittest.skipUnless(REAL_XLS.exists(), "本机尚未下载真实微信 .xls")
class CollectedAtWriterTests(unittest.TestCase):
    def test_same_batch_uses_one_current_collection_time(self):
        batch = parse_wechat_xls(REAL_XLS)
        client = FakeClient()
        fixed = datetime(2026, 7, 17, 12, 15, tzinfo=timezone.utc)
        with patch("services.supabase_writer.datetime") as mocked_datetime:
            mocked_datetime.now.return_value = fixed
            SupabaseWechatWriter(client).write("车事人话", batch)

        payloads = []
        for _, table, kwargs in client.calls:
            if table in (
                "articles",
                "article_stats",
                "account_daily_stats",
                "article_channel_stats",
            ):
                payloads.extend(kwargs["json"])
        self.assertTrue(payloads)
        self.assertEqual(
            {row["collected_at"] for row in payloads},
            {fixed.isoformat()},
        )

    def test_stat_date_still_comes_from_excel(self):
        batch = parse_wechat_xls(REAL_XLS)
        self.assertEqual(batch.account_daily_stats[-1].stat_date, date(2026, 7, 16))


class LatestReportDataTests(unittest.TestCase):
    def test_latest_successful_import_drives_report_marker(self):
        class ReportClient:
            def request(self, method, table, **kwargs):
                if table == "wechat_accounts":
                    return [{"id": "account-1"}]
                if table == "import_runs":
                    return [{"completed_at": "2026-07-17T04:16:00+00:00"}]
                if table == "account_daily_stats":
                    return [
                        {
                            "stat_date": "2026-07-16",
                            "collected_at": "2026-07-17T04:15:00+00:00",
                        }
                    ]
                raise AssertionError(table)

        latest = load_latest_report_data(ReportClient())
        self.assertEqual(latest.stat_date, date(2026, 7, 16))
        self.assertEqual(latest.collected_at.hour, 4)
        self.assertEqual(latest.report_title, "2026-07-16运营日报")


if __name__ == "__main__":
    unittest.main()
