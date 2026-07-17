"""Supabase 写入层单元测试，不连接真实网络。"""

from datetime import datetime
from pathlib import Path
import unittest

from database.models import ArticleImportRow, ImportBatch, UserImportRow
from database.repository import SupabaseRepository


class FakeClient:
    def __init__(self, duplicate=False):
        self.duplicate = duplicate
        self.calls = []

    def request(self, method, table, **kwargs):
        self.calls.append((method, table, kwargs))
        if table == "wechat_accounts":
            return [{"id": "account-1"}]
        if table == "import_runs" and method == "GET":
            return [{"id": "old-run"}] if self.duplicate else []
        if table == "import_runs" and method == "POST":
            return [{"id": "run-1"}]
        if table == "articles":
            return [{"id": "article-1", "source_key": "source-1"}]
        return None


def sample_batch():
    article = ArticleImportRow(
        source_key="source-1",
        title="15万预算怎么选新能源SUV",
        publish_time=datetime(2026, 7, 16, 9, 0),
        stat_date=datetime(2026, 7, 16).date(),
        views=1200,
        likes=None,
        shares=20,
    )
    user = UserImportRow(
        stat_date=datetime(2026, 7, 16).date(),
        new_followers=15,
        cancel_followers=3,
        net_followers=12,
    )
    return ImportBatch(Path("export.xlsx"), "hash-1", [article], [user])


class SupabaseRepositoryTests(unittest.TestCase):
    def test_duplicate_successful_file_is_skipped(self):
        client = FakeClient(duplicate=True)
        result = SupabaseRepository(client).import_batch("车事人话", sample_batch())
        self.assertEqual(result["status"], "skipped")
        self.assertFalse(any(table == "articles" for _, table, _ in client.calls))

    def test_import_upserts_all_production_tables(self):
        client = FakeClient()
        result = SupabaseRepository(client).import_batch("车事人话", sample_batch())
        self.assertEqual(result, {"status": "success", "rows_imported": 2})
        tables = [table for _, table, _ in client.calls]
        self.assertIn("articles", tables)
        self.assertIn("article_stats", tables)
        self.assertIn("user_stats", tables)

        stats_call = next(call for call in client.calls if call[1] == "article_stats")
        stats_payload = stats_call[2]["json"][0]
        self.assertIsNone(stats_payload["likes"])
        self.assertEqual(stats_payload["views"], 1200)


if __name__ == "__main__":
    unittest.main()
