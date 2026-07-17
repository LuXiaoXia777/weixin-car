"""Supabase 配置文件加载测试。"""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from database.client import SupabaseConfig


class SupabaseConfigTests(unittest.TestCase):
    def test_project_dotenv_is_loaded_before_reading_config(self):
        with TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "SUPABASE_URL=https://example.supabase.co\n"
                "SUPABASE_SERVICE_ROLE_KEY=test-service-role-secret\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True), patch(
                "database.client.PROJECT_ENV_FILE", env_file
            ):
                config = SupabaseConfig.from_env()

        self.assertEqual(config.url, "https://example.supabase.co")
        self.assertEqual(config.service_role_key, "test-service-role-secret")

    def test_missing_variable_error_reports_path_without_secret(self):
        with TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True), patch(
                "database.client.PROJECT_ENV_FILE", env_file
            ):
                with self.assertRaisesRegex(ValueError, str(env_file)) as context:
                    SupabaseConfig.from_env()

        self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY=", str(context.exception))


if __name__ == "__main__":
    unittest.main()
