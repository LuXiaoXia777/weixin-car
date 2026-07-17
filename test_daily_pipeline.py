"""微信公众号日报总控流程测试。"""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from run_daily_report import DailyReportPipeline, SelectedXls, discover_latest_xls


AI_RESULT = {
    "summary": "数据摘要",
    "best_article": {"title": "测试文章", "reason": "阅读人数100。"},
    "content_trend": "数据不足，暂无法判断。",
    "problems": "数据不足，暂无法判断。",
    "weekly_content_patterns": ["规律1", "规律2", "规律3"],
    "tomorrow_suggestions": [
        {"title": "建议1", "reason": "原因1", "reference_data": "数据1", "expected_performance": "预计1"},
        {"title": "建议2", "reason": "原因2", "reference_data": "数据2", "expected_performance": "预计2"},
        {"title": "建议3", "reason": "原因3", "reference_data": "数据3", "expected_performance": "预计3"},
    ],
}


def report_payload() -> dict:
    return {
        "date": "2026-07-16",
        "overview": {},
        "account_score": {},
        "daily_trend": [],
        "hot_article_analysis": None,
        "top5_articles": [],
        "top_articles": [],
        "trend_analysis": [],
        "channel_analysis": [],
    }


class FakeRegistry:
    def __init__(self, already_sent: bool = False) -> None:
        self.sent = already_sent
        self.started: list[date] = []
        self.finished: list[tuple[str, str, str | None]] = []

    def already_sent(self, report_date: date) -> bool:
        return self.sent

    def start(self, report_date: date) -> str:
        self.started.append(report_date)
        return "run-1"

    def finish(self, run_id: str, status: str, error: str | None = None) -> None:
        self.finished.append((run_id, status, error))


class DailyPipelineTests(unittest.TestCase):
    def test_latest_xls_uses_internal_period_end(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            older_name = root / "wechat_content_2099-01-01.xls"
            newer_data = root / "wechat_content_2020-01-01.xls"
            older_name.write_bytes(b"old")
            newer_data.write_bytes(b"new")
            dates = {older_name.name: date(2026, 7, 15), newer_data.name: date(2026, 7, 16)}

            selected = discover_latest_xls(
                root,
                parser=lambda path: SimpleNamespace(period_end=dates[path.name]),
            )

        self.assertEqual(selected.file_path.name, newer_data.name)
        self.assertEqual(selected.period_end, date(2026, 7, 16))

    def test_complete_pipeline_order_and_success_marker(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            xls = root / "data" / "import" / "wechat.xls"
            xls.parent.mkdir(parents=True)
            xls.write_bytes(b"xls")
            calls: list[list[str]] = []

            def runner(command, *, cwd, capture_output=False):
                calls.append(command)
                if "services.analysis_service" in command:
                    (root / "report.json").write_text(json.dumps(report_payload()), encoding="utf-8")
                stdout = json.dumps(AI_RESULT, ensure_ascii=False) if capture_output else ""
                return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

            registry = FakeRegistry()
            pipeline = DailyReportPipeline(
                root,
                command_runner=runner,
                latest_xls_finder=lambda _: SelectedXls(xls, date(2026, 7, 16)),
                registry_factory=lambda: registry,
            )
            result = pipeline.run()

            self.assertEqual(result, {"status": "success", "date": "2026-07-16"})
            self.assertEqual(len(calls), 5)
            self.assertIn("collect_wechat_data.py", calls[0])
            self.assertIn("import_wechat_data.py", calls[1])
            self.assertIn("services.analysis_service", calls[2])
            self.assertIn("services.ai_analyzer", calls[3])
            self.assertIn("services.feishu_sender", calls[4])
            self.assertTrue((root / "ai_analysis.json").exists())
            self.assertEqual(registry.finished, [("run-1", "success", None)])

    def test_same_date_does_not_call_ai_or_feishu(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            xls = root / "latest.xls"
            xls.write_bytes(b"xls")
            calls: list[list[str]] = []

            def runner(command, *, cwd, capture_output=False):
                calls.append(command)
                if "services.analysis_service" in command:
                    (root / "report.json").write_text(json.dumps(report_payload()), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            pipeline = DailyReportPipeline(
                root,
                command_runner=runner,
                latest_xls_finder=lambda _: SelectedXls(xls, date(2026, 7, 16)),
                registry_factory=lambda: FakeRegistry(already_sent=True),
            )
            result = pipeline.run()

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(len(calls), 3)
        self.assertFalse(any("services.ai_analyzer" in command for command in calls))
        self.assertFalse(any("services.feishu_sender" in command for command in calls))

    def test_failure_stops_following_steps(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            xls = root / "latest.xls"
            xls.write_bytes(b"xls")
            calls: list[list[str]] = []

            def runner(command, *, cwd, capture_output=False):
                calls.append(command)
                if "import_wechat_data.py" in command:
                    raise RuntimeError("Supabase 写入失败")
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            pipeline = DailyReportPipeline(
                root,
                command_runner=runner,
                latest_xls_finder=lambda _: SelectedXls(xls, date(2026, 7, 16)),
                registry_factory=lambda: FakeRegistry(),
            )
            with self.assertRaisesRegex(RuntimeError, "Supabase 写入失败"):
                pipeline.run()

        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
