"""真实微信 .xls 账号每日数据与文章渠道入库测试。"""

from __future__ import annotations

from pathlib import Path
import unittest

from services.supabase_writer import SupabaseWechatWriter
from services.wechat_xls_parser import parse_wechat_xls


REAL_XLS = Path(__file__).resolve().parent / "data/import/wechat_content_2026-07-16.xls"


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method, table, **kwargs):
        self.calls.append((method, table, kwargs))
        if table == "wechat_accounts":
            return [{"id": "account-1"}]
        if table == "import_runs" and method == "POST":
            return [{"id": "run-1"}]
        if table == "import_runs" and method == "GET":
            return [{"id": "existing-success"}]
        if table == "articles":
            return [
                {"id": f"article-{index}", "source_key": row["source_key"]}
                for index, row in enumerate(kwargs["json"], start=1)
            ]
        return None


@unittest.skipUnless(REAL_XLS.exists(), "本机尚未下载真实微信 .xls")
class AccountStatsImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.batch = parse_wechat_xls(REAL_XLS)

    def test_region_b_maps_to_account_daily_stats(self):
        self.assertEqual(len(self.batch.account_daily_stats), 30)
        last = self.batch.account_daily_stats[-1]
        self.assertEqual(last.stat_date.isoformat(), "2026-07-16")
        self.assertEqual(last.views, 6673)
        self.assertEqual(last.shares, 91)
        self.assertEqual(last.favorites, 5)
        self.assertEqual(last.publish_count, 2)

    def test_region_c_maps_to_article_channel_stats(self):
        self.assertEqual(len(self.batch.article_channel_stats), 81)
        row = self.batch.article_channel_stats[0]
        self.assertNotEqual(row.channel, "全部")
        self.assertIsNotNone(row.read_users)
        self.assertIsNotNone(row.read_percent)
        self.assertEqual(row.stat_date.isoformat(), "2026-07-16")

    def test_writer_uses_new_tables_and_upsert_constraints(self):
        client = FakeClient()
        result = SupabaseWechatWriter(client).write("车事人话", self.batch)
        self.assertEqual(result["account_daily_stats"], 30)
        self.assertEqual(result["article_channel_stats"], 81)

        daily_call = next(call for call in client.calls if call[1] == "account_daily_stats")
        self.assertEqual(daily_call[2]["params"]["on_conflict"], "account_id,stat_date")
        channel_call = next(call for call in client.calls if call[1] == "article_channel_stats")
        self.assertEqual(
            channel_call[2]["params"]["on_conflict"],
            "article_id,channel,stat_date",
        )

    def test_repeat_import_is_not_skipped(self):
        client = FakeClient()
        writer = SupabaseWechatWriter(client)
        first = writer.write("车事人话", self.batch)
        second = writer.write("车事人话", self.batch)
        self.assertEqual(first["status"], "success")
        self.assertEqual(second["status"], "success")
        self.assertEqual(
            sum(1 for _, table, _ in client.calls if table == "account_daily_stats"),
            2,
        )


if __name__ == "__main__":
    unittest.main()
