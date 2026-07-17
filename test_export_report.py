"""微信公众号内容分析报表导出模块测试。"""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from collector.export_report import (
    ExportReportError,
    XLS_SIGNATURE,
    export_content_report,
    parse_report_date,
    validate_download,
)


class FakeDownload:
    suggested_filename = "tendency.xls"

    def save_as(self, path: str) -> None:
        Path(path).write_bytes(XLS_SIGNATURE + b"wechat-report")

    def failure(self):
        return None


class ExportReportTests(unittest.TestCase):
    def test_parse_explicit_date(self):
        self.assertEqual(parse_report_date("2026-07-16"), date(2026, 7, 16))

    def test_valid_xls_download(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "wechat_content_2026-07-16.xls"
            path.write_bytes(XLS_SIGNATURE + b"content")
            result = validate_download(path, date(2026, 7, 16))
            self.assertEqual(result.file_path, path)
            self.assertGreater(result.size_bytes, 0)

    def test_rejects_empty_or_invalid_download(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "wechat_content_2026-07-16.xls"
            path.write_bytes(b"")
            with self.assertRaises(ExportReportError):
                validate_download(path, date(2026, 7, 16))

    @patch("collector.export_report._named_action")
    def test_navigation_expands_data_analysis_before_content(self, named_action_mock):
        page = MagicMock()
        content_text = MagicMock()
        content_text.count.return_value = 0
        page.get_by_text.return_value = content_text
        data_action = MagicMock()
        content_action = MagicMock()
        named_action_mock.side_effect = [data_action, content_action]

        from collector.export_report import navigate_to_content_analysis

        navigate_to_content_analysis(page)
        data_action.click.assert_called_once_with()
        content_text.wait_for.assert_called_once_with(state="visible", timeout=8_000)
        content_action.click.assert_called_once_with()

    @patch("collector.export_report._trigger_content_download", return_value=FakeDownload())
    @patch("collector.export_report.select_report_date")
    @patch("collector.export_report.navigate_to_content_analysis")
    def test_logged_in_workflow_exports_once(
        self,
        navigate_mock: MagicMock,
        select_date_mock: MagicMock,
        download_mock: MagicMock,
    ):
        with TemporaryDirectory() as temporary:
            page = MagicMock()
            target = date(2026, 7, 16)
            result = export_content_report(page, target, Path(temporary))
            self.assertTrue(result.file_path.exists())
            self.assertEqual(result.file_path.name, "wechat_content_2026-07-16.xls")
            navigate_mock.assert_called_once_with(page)
            select_date_mock.assert_called_once_with(page, target)
            download_mock.assert_called_once_with(page)


if __name__ == "__main__":
    unittest.main()
