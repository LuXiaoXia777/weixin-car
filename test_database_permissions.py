"""service_role 表级权限迁移和可选真实连接测试。"""

from __future__ import annotations

import os
from pathlib import Path
import unittest
from uuid import uuid4

from database.client import SupabaseConfig, SupabaseRestClient


PROJECT_ROOT = Path(__file__).resolve().parent
MIGRATION = PROJECT_ROOT / "database/rls_service_role.sql"
TABLES = (
    "wechat_accounts",
    "articles",
    "article_stats",
    "user_stats",
    "import_runs",
    "sync_runs",
)


class ServiceRoleMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sql = " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())

    def test_service_role_receives_select_insert_update_delete(self):
        self.assertIn("grant select, insert, update, delete", self.sql)
        self.assertIn("to service_role", self.sql)
        for table in TABLES:
            self.assertIn(f"public.{table}", self.sql)

    def test_frontend_roles_are_revoked_and_rls_stays_enabled(self):
        self.assertIn("from anon, authenticated", self.sql)
        for table in TABLES:
            self.assertIn(
                f"alter table public.{table} enable row level security",
                self.sql,
            )


@unittest.skipUnless(
    os.getenv("RUN_SUPABASE_PERMISSION_TEST") == "1",
    "设置 RUN_SUPABASE_PERMISSION_TEST=1 后执行真实 Supabase 权限测试",
)
class LiveServiceRolePermissionTests(unittest.TestCase):
    def test_service_role_can_select_insert_and_update(self):
        client = SupabaseRestClient(SupabaseConfig.from_env())
        name = f"codex-permission-test-{uuid4()}"
        inserted_id = None
        try:
            rows = client.request(
                "POST",
                "wechat_accounts",
                json={
                    "name": name,
                    "account_type": "personal_subscription",
                    "api_enabled": False,
                },
                prefer="return=representation",
            )
            self.assertTrue(rows)
            inserted_id = rows[0]["id"]

            client.request(
                "PATCH",
                "wechat_accounts",
                params={"id": f"eq.{inserted_id}"},
                json={"api_enabled": True},
                prefer="return=minimal",
            )
            selected = client.request(
                "GET",
                "wechat_accounts",
                params={"select": "id,api_enabled", "id": f"eq.{inserted_id}"},
            )
            self.assertEqual(selected, [{"id": inserted_id, "api_enabled": True}])
        finally:
            if inserted_id:
                client.request(
                    "DELETE",
                    "wechat_accounts",
                    params={"id": f"eq.{inserted_id}"},
                    prefer="return=minimal",
                )


if __name__ == "__main__":
    unittest.main()
