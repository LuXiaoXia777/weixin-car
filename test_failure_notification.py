"""launchd 失败通知测试。"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from scripts.send_failure_notification import (
    build_failure_card,
    read_log_tail,
    send_failure_notification,
)


class FailureNotificationTests(unittest.TestCase):
    def test_build_failure_card(self) -> None:
        card = build_failure_card(exit_code=7, log_tail="Playwright failed")

        self.assertEqual(card["msg_type"], "interactive")
        self.assertEqual(card["card"]["header"]["template"], "red")
        rendered = str(card)
        self.assertIn("Playwright failed", rendered)
        self.assertIn("7", rendered)

    def test_read_log_tail_limits_content(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "daily.log"
            path.write_text("A" * 100 + "LAST", encoding="utf-8")
            tail = read_log_tail(path, max_chars=10)

        self.assertEqual(tail, "AAAAAALAST")

    def test_log_tail_redacts_secrets(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "daily.log"
            path.write_text(
                "DEEPSEEK_API_KEY=secret-value\n"
                "Authorization: Bearer tenant-token\n"
                "https://open.feishu.cn/open-apis/bot/v2/hook/webhook-token",
                encoding="utf-8",
            )
            tail = read_log_tail(path)

        self.assertNotIn("secret-value", tail)
        self.assertNotIn("tenant-token", tail)
        self.assertNotIn("webhook-token", tail)
        self.assertGreaterEqual(tail.count("[REDACTED]"), 3)

    @patch("scripts.send_failure_notification.requests.post")
    def test_mock_send_success(self, post: Mock) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"code": 0, "msg": "success"}
        post.return_value = response

        send_failure_notification("https://example.invalid/webhook", {"msg_type": "interactive"})

        post.assert_called_once()

    @patch("scripts.send_failure_notification.time.sleep", return_value=None)
    @patch("scripts.send_failure_notification.requests.post")
    def test_failure_retries_three_times(self, post: Mock, _sleep: Mock) -> None:
        post.side_effect = __import__("requests").ConnectionError("offline")

        with self.assertRaisesRegex(RuntimeError, "失败通知发送失败"):
            send_failure_notification(
                "https://example.invalid/webhook",
                {"msg_type": "interactive"},
                max_attempts=3,
            )
        self.assertEqual(post.call_count, 3)
