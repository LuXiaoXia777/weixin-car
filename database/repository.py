"""Supabase 表的幂等写入操作。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from database.client import SupabaseRestClient
from database.models import ImportBatch


def _chunks(rows: list[dict], size: int = 300) -> Iterable[list[dict]]:
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


class SupabaseRepository:
    def __init__(self, client: SupabaseRestClient) -> None:
        self.client = client

    def upsert_account(self, name: str) -> str:
        rows = self.client.request(
            "POST",
            "wechat_accounts",
            params={"on_conflict": "name"},
            json={"name": name, "account_type": "personal_subscription", "api_enabled": False},
            prefer="resolution=merge-duplicates,return=representation",
        )
        if not rows:
            raise RuntimeError("Supabase 未返回公众号记录")
        return rows[0]["id"]

    def successful_import_exists(self, account_id: str, file_hash: str) -> bool:
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

    def start_import(self, account_id: str, batch: ImportBatch) -> str:
        rows = self.client.request(
            "POST",
            "import_runs",
            params={"on_conflict": "account_id,file_hash"},
            json={
                "account_id": account_id,
                "file_name": batch.source_file.name,
                "file_hash": batch.file_hash,
                "status": "running",
                "rows_received": batch.total_rows,
                "rows_imported": 0,
                "error_message": None,
                "completed_at": None,
            },
            prefer="resolution=merge-duplicates,return=representation",
        )
        if not rows:
            raise RuntimeError("Supabase 未返回导入批次记录")
        return rows[0]["id"]

    def finish_import(self, run_id: str, status: str, rows_imported: int, error: str | None = None) -> None:
        self.client.request(
            "PATCH",
            "import_runs",
            params={"id": f"eq.{run_id}"},
            json={
                "status": status,
                "rows_imported": rows_imported,
                "error_message": error[:500] if error else None,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
            prefer="return=minimal",
        )

    def upsert_articles(self, account_id: str, batch: ImportBatch) -> dict[str, str]:
        payload = [
            {
                "account_id": account_id,
                "source_key": row.source_key,
                "external_id": row.external_id,
                "title": row.title,
                "url": row.url,
                "digest": row.digest,
                "publish_time": row.publish_time.isoformat(),
                "category": row.category,
                "data_source": "manual_import",
            }
            for row in batch.articles
        ]
        result: dict[str, str] = {}
        for chunk in _chunks(payload):
            rows = self.client.request(
                "POST",
                "articles",
                params={"on_conflict": "account_id,source_key"},
                json=chunk,
                prefer="resolution=merge-duplicates,return=representation",
            )
            for row in rows or []:
                result[row["source_key"]] = row["id"]
        if len(result) != len(payload):
            raise RuntimeError("部分文章写入后未返回 ID，事务未能完整映射")
        return result

    def upsert_article_stats(self, article_ids: dict[str, str], batch: ImportBatch) -> int:
        payload = []
        for row in batch.articles:
            if not row.has_stats:
                continue
            payload.append(
                {
                    "article_id": article_ids[row.source_key],
                    "stat_date": row.stat_date.isoformat(),
                    "views": row.views,
                    "read_users": row.read_users,
                    "likes": row.likes,
                    "recommendations": row.recommendations,
                    "shares": row.shares,
                    "comments": row.comments,
                    "new_followers": row.new_followers,
                    "data_source": "manual_import",
                    "imported_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        for chunk in _chunks(payload):
            self.client.request(
                "POST",
                "article_stats",
                params={"on_conflict": "article_id,stat_date"},
                json=chunk,
                prefer="resolution=merge-duplicates,return=minimal",
            )
        return len(payload)

    def upsert_user_stats(self, account_id: str, batch: ImportBatch) -> int:
        payload = [
            {
                "account_id": account_id,
                "stat_date": row.stat_date.isoformat(),
                "new_followers": row.new_followers,
                "cancel_followers": row.cancel_followers,
                "net_followers": row.net_followers,
                "data_source": "manual_import",
                "imported_at": datetime.now(timezone.utc).isoformat(),
            }
            for row in batch.user_stats
        ]
        for chunk in _chunks(payload):
            self.client.request(
                "POST",
                "user_stats",
                params={"on_conflict": "account_id,stat_date"},
                json=chunk,
                prefer="resolution=merge-duplicates,return=minimal",
            )
        return len(payload)

    def import_batch(self, account_name: str, batch: ImportBatch) -> dict[str, Any]:
        account_id = self.upsert_account(account_name)
        if self.successful_import_exists(account_id, batch.file_hash):
            return {"status": "skipped", "rows_imported": 0, "reason": "文件已成功导入"}

        run_id = self.start_import(account_id, batch)
        imported = 0
        try:
            article_ids = self.upsert_articles(account_id, batch) if batch.articles else {}
            imported += len(batch.articles)
            self.upsert_article_stats(article_ids, batch)
            imported += self.upsert_user_stats(account_id, batch)
            self.finish_import(run_id, "success", imported)
            return {"status": "success", "rows_imported": imported}
        except Exception as exc:
            self.finish_import(run_id, "failed", imported, str(exc))
            raise
