"""微信公众号后台内容分析报表导出。"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError


LOGGER = logging.getLogger(__name__)
XLS_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
XLSX_SIGNATURE = b"PK\x03\x04"
DOWNLOAD_TIMEOUT_MS = 120_000


class ExportReportError(RuntimeError):
    """页面结构、日期选择或文件下载不符合预期。"""


@dataclass(frozen=True)
class ExportResult:
    file_path: Path
    report_date: date
    size_bytes: int
    created_at: datetime


def default_report_date() -> date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=1)


def parse_report_date(value: str | None) -> date:
    if value is None:
        return default_report_date()
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("--date 必须使用 YYYY-MM-DD 格式") from exc
    if parsed > datetime.now(ZoneInfo("Asia/Shanghai")).date():
        raise ValueError("不能导出未来日期")
    return parsed


def _unique_visible(locators: Iterable[Locator], description: str) -> Locator:
    ambiguous = False
    for locator in locators:
        count = locator.count()
        if count == 1 and locator.is_visible():
            return locator
        if count > 1:
            ambiguous = True
    reason = "匹配到多个元素" if ambiguous else "没有找到元素"
    raise ExportReportError(f"{description}：{reason}，为避免误操作已停止")


def _named_action(page: Page, names: tuple[str, ...], description: str) -> Locator:
    candidates: list[Locator] = []
    for name in names:
        for role in ("link", "button", "menuitem", "tab"):
            candidates.append(page.get_by_role(role, name=name, exact=True))
        candidates.append(page.get_by_text(name, exact=True))
    return _unique_visible(candidates, description)


def navigate_to_content_analysis(page: Page) -> None:
    """只通过可见文本和语义角色进入数据分析、内容分析。"""

    if page.get_by_text("内容分析", exact=True).count() == 0:
        data_analysis = _named_action(page, ("数据分析", "数据与分析"), "数据分析菜单")
        data_analysis.click()
        try:
            page.get_by_text("内容分析", exact=True).wait_for(state="visible", timeout=8_000)
        except PlaywrightTimeoutError as exc:
            raise ExportReportError(
                "点击数据分析后没有出现内容分析子菜单；页面结构可能已变化"
            ) from exc

    content_analysis = _named_action(page, ("内容分析",), "内容分析菜单")
    content_analysis.click()
    page.wait_for_load_state("domcontentloaded")
    LOGGER.info("已进入内容分析页面")


def _fill_labeled_date(page: Page, label: str, value: str) -> bool:
    candidates = (
        page.get_by_label(label, exact=True),
        page.get_by_placeholder(label, exact=True),
        page.get_by_role("textbox", name=label, exact=True),
    )
    for locator in candidates:
        if locator.count() == 1 and locator.is_visible():
            locator.fill(value)
            locator.press("Enter")
            return True
    return False


def select_report_date(page: Page, target_date: date) -> None:
    """优先使用“昨日”，自定义日期仅操作有明确标签的输入框。"""

    if target_date == default_report_date():
        try:
            yesterday = _named_action(page, ("昨日", "昨天"), "昨日日期选项")
            yesterday.click()
            LOGGER.info("已选择昨日：%s", target_date)
            return
        except ExportReportError:
            LOGGER.info("页面没有独立的昨日选项，尝试带标签的日期输入框")

    value = target_date.isoformat()
    start_ok = _fill_labeled_date(page, "开始日期", value)
    end_ok = _fill_labeled_date(page, "结束日期", value)
    if not (start_ok and end_ok):
        raise ExportReportError(
            "未找到带“开始日期/结束日期”标签的控件；请不要手动点击导出，"
            "先截图确认实际日期控件"
        )
    LOGGER.info("已选择内容分析日期：%s", target_date)


def _wait_for_direct_download(page: Page, action: Locator):
    try:
        with page.expect_download(timeout=8_000) as download_info:
            action.click()
        return download_info.value
    except PlaywrightTimeoutError:
        return None


def _trigger_content_download(page: Page):
    export_action = _named_action(
        page,
        ("导出数据", "导出报表", "导出"),
        "内容分析导出按钮",
    )
    download = _wait_for_direct_download(page, export_action)
    if download is not None:
        return download

    # 某些版本会先打开报表类型菜单，再点击具体类型才开始下载。
    report_action = _named_action(
        page,
        ("内容分析数据", "内容分析报表", "导出 Excel", "导出全部数据"),
        "内容分析报表类型",
    )
    try:
        with page.expect_download(timeout=DOWNLOAD_TIMEOUT_MS) as download_info:
            report_action.click()
        return download_info.value
    except PlaywrightTimeoutError as exc:
        raise ExportReportError("点击内容分析报表后未检测到 Playwright 下载事件") from exc


def detect_excel_extension(path: Path) -> str:
    with path.open("rb") as stream:
        signature = stream.read(8)
    if signature == XLS_SIGNATURE:
        return ".xls"
    if signature.startswith(XLSX_SIGNATURE):
        return ".xlsx"
    raise ExportReportError("下载文件不是有效的 .xls 或 .xlsx Excel 文件")


def validate_download(path: Path, report_date: date) -> ExportResult:
    if not path.exists() or not path.is_file():
        raise ExportReportError(f"下载文件不存在：{path}")
    size = path.stat().st_size
    if size <= 0:
        raise ExportReportError(f"下载文件为空：{path}")
    detected = detect_excel_extension(path)
    if path.suffix.lower() != detected:
        raise ExportReportError(f"文件扩展名与实际格式不一致：{path.suffix} / {detected}")
    created_at = datetime.fromtimestamp(path.stat().st_ctime, ZoneInfo("Asia/Shanghai"))
    return ExportResult(path, report_date, size, created_at)


def export_content_report(page: Page, target_date: date, output_dir: Path) -> ExportResult:
    navigate_to_content_analysis(page)
    select_report_date(page, target_date)

    output_dir.mkdir(parents=True, exist_ok=True)
    download = _trigger_content_download(page)
    suggested = (download.suggested_filename or "").lower()
    suggested_extension = Path(suggested).suffix
    if suggested_extension not in (".xls", ".xlsx"):
        raise ExportReportError(f"微信返回了不支持的文件扩展名：{suggested_extension or '无'}")

    temporary = output_dir / f".wechat_content_{target_date.isoformat()}{suggested_extension}.part"
    destination = output_dir / f"wechat_content_{target_date.isoformat()}{suggested_extension}"
    download.save_as(str(temporary))
    failure = download.failure()
    if failure:
        temporary.unlink(missing_ok=True)
        raise ExportReportError(f"微信内容分析报表下载失败：{failure}")

    detected_extension = detect_excel_extension(temporary)
    if detected_extension != suggested_extension:
        temporary.unlink(missing_ok=True)
        raise ExportReportError("微信下载文件的扩展名与实际 Excel 格式不一致")
    os.replace(temporary, destination)
    result = validate_download(destination, target_date)
    LOGGER.info(
        "内容分析报表下载完成：%s（%s 字节，创建时间 %s）",
        result.file_path,
        result.size_bytes,
        result.created_at.isoformat(),
    )
    return result
