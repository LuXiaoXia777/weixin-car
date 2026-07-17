"""微信公众号内容分析报表导出模块测试。"""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from collector.export_report import (
    ExportReportError,
    XLS_SIGNATURE,
    _trigger_content_download,
    collect_page_actions,
    export_content_report,
    parse_report_date,
    select_report_date,
    validate_download,
)
from collector.debug import save_debug_artifacts


def _locator_with_items(*items):
    locator = MagicMock()
    locator.count.return_value = len(items)
    locator.nth.side_effect = lambda index: items[index]
    return locator


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

    @patch("collector.export_report.default_report_date", return_value=date(2026, 7, 16))
    @patch("collector.export_report._named_action")
    def test_default_date_uses_real_yesterday_option(self, named_action_mock, _date_mock):
        page = MagicMock()
        yesterday = MagicMock()
        named_action_mock.return_value = yesterday

        select_report_date(page, date(2026, 7, 16))

        named_action_mock.assert_called_once_with(page, ("昨日", "昨天"), "昨日日期选项")
        yesterday.click.assert_called_once_with()

    @patch("collector.export_report._select_calendar_date")
    @patch("collector.export_report.default_report_date", return_value=date(2026, 7, 17))
    def test_explicit_date_uses_start_and_end_calendar(
        self,
        _date_mock,
        select_calendar_mock,
    ):
        page = MagicMock()
        target = date(2026, 7, 16)

        select_report_date(page, target)

        self.assertEqual(
            select_calendar_mock.call_args_list,
            [
                unittest.mock.call(page, "开始日期", target),
                unittest.mock.call(page, "结束日期", target),
            ],
        )

    @patch("collector.export_report.log_page_actions")
    @patch("collector.export_report._unique_visible")
    def test_download_uses_real_download_detail_link(self, unique_mock, _log_mock):
        page = MagicMock()
        action = MagicMock()
        unique_mock.return_value = action
        context = MagicMock()
        context.__enter__.return_value.value = FakeDownload()
        page.expect_download.return_value = context

        result = _trigger_content_download(page)

        self.assertIsInstance(result, FakeDownload)
        page.expect_download.assert_called_once_with(timeout=120_000)
        action.click.assert_called_once_with()

    def test_debug_control_inventory_includes_buttons_links_and_placeholders(self):
        page = MagicMock()
        button = MagicMock()
        button.is_visible.return_value = True
        button.inner_text.return_value = "前往查看"
        link = MagicMock()
        link.is_visible.return_value = True
        link.inner_text.return_value = "下载数据明细"
        page.get_by_role.side_effect = lambda role: {
            "button": _locator_with_items(button),
            "link": _locator_with_items(link),
        }[role]
        input_item = MagicMock()
        input_item.is_visible.return_value = True
        input_item.get_attribute.return_value = "开始日期"
        page.locator.return_value = _locator_with_items(input_item)

        result = collect_page_actions(page)

        self.assertEqual(result["buttons"], [{"text": "前往查看"}])
        self.assertEqual(result["links"], [{"text": "下载数据明细"}])
        self.assertEqual(result["inputs"], [{"placeholder": "开始日期"}])

    @patch("collector.export_report._data_analysis_toggle")
    @patch("collector.export_report._content_analysis_link")
    @patch("collector.export_report._content_analysis_heading")
    def test_navigation_expands_data_analysis_before_content(
        self,
        heading_mock,
        content_link_mock,
        data_toggle_mock,
    ):
        page = MagicMock()
        heading = MagicMock()
        heading.count.return_value = 0
        heading.wait_for.side_effect = [Exception("not loaded"), None]
        heading_mock.return_value = heading
        data_action = MagicMock()
        content_action = MagicMock()
        data_toggle_mock.return_value = data_action
        content_link_mock.side_effect = [ExportReportError("collapsed"), content_action]

        from collector.export_report import navigate_to_content_analysis

        with patch("collector.export_report.PlaywrightTimeoutError", Exception):
            navigate_to_content_analysis(page)
        data_action.click.assert_called_once_with()
        content_action.click.assert_called_once_with()

    @patch("collector.export_report._content_analysis_heading")
    def test_navigation_does_nothing_when_content_page_is_loaded(self, heading_mock):
        page = MagicMock()
        heading = MagicMock()
        heading.count.return_value = 1
        heading.is_visible.return_value = True
        heading_mock.return_value = heading

        from collector.export_report import navigate_to_content_analysis

        navigate_to_content_analysis(page)
        page.get_by_text.assert_not_called()

    def test_debug_artifacts_save_screenshot_and_html(self):
        with TemporaryDirectory() as temporary:
            page = MagicMock()
            page.content.return_value = "<html><body>内容分析</body></html>"

            def write_screenshot(*, path, full_page):
                Path(path).write_bytes(b"png")

            page.screenshot.side_effect = write_screenshot
            screenshot, html = save_debug_artifacts(page, Path(temporary))
            self.assertTrue(screenshot.exists())
            self.assertIn("内容分析", html.read_text(encoding="utf-8"))

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
            navigate_mock.assert_called_once_with(page, debug=False, debug_dir=None)
            select_date_mock.assert_called_once_with(page, target)
            download_mock.assert_called_once_with(page)


if __name__ == "__main__":
    unittest.main()
