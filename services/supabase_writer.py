"""将真实微信 .xls 解析结果幂等写入 Supabase。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from database.client import SupabaseRestClient
from services.wechat_xls_parser import WechatXlsBatch


def _chunks(rows: list[dict[str, Any]], size: int = 300) -> Iterable[list[dict[str, Any]]]:
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


class SupabaseWechatWriter:
    def __init__(self, client: SupabaseRestClient) -> None:
        self.client = client

    def _upsert(self, table: str, payload: list[dict[str, Any]], conflict: str, *, representation=False):
        rows: list[dict[str, Any]] = []
        for chunk in _chunks(payload):
            response = self.client.request(
                "POST",
                table,
                params={"on_conflict": conflict},
                json=chunk,
                prefer=f"resolution=merge-duplicates,return={'representation' if representation else 'minimal'}",
            )
            rows.extend(response or [])
        return rows

    def _account_id(self, account_name: str) -> str:
        rows = self.client.request(
            "POST",
            "wechat_accounts",
            params={"on_conflict": "name"},
            json={"name": account_name, "account_type": "personal_subscription", "api_enabled": False},
            prefer="resolution=merge-duplicates,return=representation",
        )
        if not rows:
            raise RuntimeError("Supabase 未返回公众号 ID")
        return rows[0]["id"]

    def _successful_import_exists(self, account_id: str, file_hash: str) -> bool:
        rows = self.client.request(
            "GET",
            "import_runs",
            params={
                "select": "id",
                "account_id": f"eq.{account_id}",
                "file_hash": f"eq.{file_hash}",
                "status": "eq.success",
                "limit": "1",
            },
        )
        return bool(rows)

    def _start_import(self, account_id: str, batch: WechatXlsBatch) -> str:
        rows = self.client.request(
            "POST",
            "import_runs",
            params={"on_conflict": "account_id,file_hash"},
            json={
                "account_id": account_id,
                "file_name": batch.source_file.name,
                "file_hash": batch.file_hash,
                "status": "running",
                "rows_received": batch.total_source_rows,
                "rows_imported": 0,
                "error_message": None,
                "completed_at": None,
            },
            prefer="resolution=merge-duplicates,return=representation",
        )
        if not rows:
            raise RuntimeError("Supabase 未返回导入记录 ID")
        return rows[0]["id"]

    def _finish_import(self, run_id: str, status: str, count: int, error: str | None = None) -> None:
        self.client.request(
            "PATCH",
            "import_runs",
            params={"id": f"eq.{run_id}"},
            json={
                "status": status,
                "rows_imported": count,
                "error_message": error[:500] if error else None,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
            prefer="return=minimal",
        )

    def _write_articles(
        self,
        account_id: str,
        batch: WechatXlsBatch,
        collected_at: str,
    ) -> dict[str, str]:
        payload = [
            {
                "account_id": account_id,
                "source_key": row.source_key,
                "title": row.title,
                "publish_time": row.publish_time.isoformat(),
                "url": None,
                "digest": None,
                "category": None,
                "data_source": "manual_import",
                "collected_at": collected_at,
            }
            for row in batch.articles
        ]
        rows = self._upsert("articles", payload, "account_id,source_key", representation=True)
        result = {row["source_key"]: row["id"] for row in rows}
        if len(result) != len(payload):
            raise RuntimeError("文章写入后未完整返回 ID")
        return result

    def write(self, account_name: str, batch: WechatXlsBatch) -> dict[str, Any]:
        account_id = self._account_id(account_name)
        # 真实 .xls 允许重复导入，以 upsert 覆盖同日数据。
        run_id = self._start_import(account_id, batch)
        collected_at = datetime.now(timezone.utc).isoformat()
        counts = {"articles": 0, "article_stats": 0, "account_daily_stats": 0, "article_channel_stats": 0}
        try:
            article_ids = self._write_articles(account_id, batch, collected_at)
            counts["articles"] = len(batch.articles)

            article_stats = [
                {
                    "article_id": article_ids[row.source_key],
                    "stat_date": row.stat_date.isoformat(),
                    "views": None,
                    "read_users": row.read_users,
                    "likes": None,
                    "recommendations": None,
                    "shares": None,
                    "comments": None,
                    "new_followers": None,
                    "data_source": "manual_import",
                    "collected_at": collected_at,
                    "imported_at": datetime.now(timezone.utc).isoformat(),
                }
                for row in batch.article_totals
            ]
            self._upsert("article_stats", article_stats, "article_id,stat_date")
            counts["article_stats"] = len(article_stats)

            account_stats = [
                {
                    "account_id": account_id,
                    "stat_date": row.stat_date.isoformat(),
                    "views": row.views,
                    "shares": row.shares,
                    "favorites": row.favorites,
                    "publish_count": row.publish_count,
                    "data_source": "manual_import",
                    "collected_at": collected_at,
                }
                for row in batch.account_daily_stats
            ]
            self._upsert("account_daily_stats", account_stats, "account_id,stat_date")
            counts["account_daily_stats"] = len(account_stats)

            channel_stats = [
                {
                    "article_id": article_ids[row.source_key],
                    "stat_date": row.stat_date.isoformat(),
                    "channel": row.channel,
                    "read_users": row.read_users,
                    "read_percent": row.read_percent,
                    "data_source": "manual_import",
                    "collected_at": collected_at,
                }
                for row in batch.article_channel_stats
            ]
            self._upsert("article_channel_stats", channel_stats, "article_id,channel,stat_date")
            counts["article_channel_stats"] = len(channel_stats)

            imported = sum(counts.values())
            self._finish_import(run_id, "success", imported)
            return {
                "status": "success",
                "rows_imported": imported,
                **counts,
                "account_channel_trends_skipped": len(batch.account_channel_trends),
            }
        except Exception as exc:
            self._finish_import(run_id, "failed", sum(counts.values()), str(exc))
            raise
