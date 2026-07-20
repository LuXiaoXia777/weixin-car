"""macOS LaunchAgent 配置静态测试。"""

from __future__ import annotations

import plistlib
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent
LABEL = "com.luxiaoxia.wechat-ai-daily-report"


class MacOSLaunchdTests(unittest.TestCase):
    def test_plist_has_manual_and_daily_configuration(self) -> None:
        path = PROJECT_ROOT / "launchd" / f"{LABEL}.plist"
        config = plistlib.loads(path.read_bytes())

        self.assertEqual(config["Label"], LABEL)
        self.assertEqual(config["StartCalendarInterval"], {"Hour": 12, "Minute": 30})
        self.assertFalse(config["RunAtLoad"])
        self.assertFalse(config["KeepAlive"])
        self.assertEqual(config["LimitLoadToSessionType"], "Aqua")
        self.assertTrue(config["ProgramArguments"][0].endswith("scripts/run_daily_report.sh"))

    def test_wrapper_uses_persistent_project_and_failure_notification(self) -> None:
        script = (PROJECT_ROOT / "scripts" / "run_daily_report.sh").read_text(encoding="utf-8")

        self.assertIn("source \"${PROJECT_DIR}/.venv/bin/activate\"", script)
        self.assertIn("run_daily_report.py", script)
        self.assertIn("send_failure_notification.py", script)
        self.assertIn("daily-report.lock", script)
        self.assertIn("/usr/bin/caffeinate -dims", script)

    def test_collector_profile_is_persistent_and_gitignored(self) -> None:
        browser_config = (PROJECT_ROOT / "collector" / "browser_config.py").read_text(encoding="utf-8")
        gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn('return self.project_root / "wechat-browser-profile"', browser_config)
        self.assertIn("wechat-browser-profile/", gitignore)
