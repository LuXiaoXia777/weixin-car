"""微信公众号后台内容分析报表导出。"""

from __future__ import annotations

import logging
import os
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError

from collector.debug import log_visible_menu_texts, manual_content_analysis_handoff


LOGGER = logging.getLogger(__name__)
XLS_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
XLSX_SIGNATURE = b"PK\x03\x04"
DOWNLOAD_TIMEOUT_MS = 120_000
DATE_PICKER_TIMEOUT_MS = 10_000


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


def _content_analysis_heading(page: Page) -> Locator:
    """真实页面的主内容使用唯一 h1“内容分析”标识加载完成。"""

    return page.get_by_role("heading", name="内容分析", exact=True)


def _content_analysis_link(page: Page) -> Locator:
    """真实侧栏使用 <a title="内容分析">，role=link 且名称唯一。"""

    candidates = (
        page.get_by_role("link", name="内容分析", exact=True),
        page.locator(
            'xpath=//a[@title="内容分析" and contains(@href, "/misc/appmsganalysis")]'
        ),
    )
    return _unique_visible(candidates, "内容分析菜单")


def _data_analysis_toggle(page: Page) -> Locator:
    """真实侧栏父菜单是带 title 的 span，不是 link/button。"""

    candidates = (
        page.get_by_text("数据分析", exact=True),
        page.locator('xpath=//span[@title="数据分析" and normalize-space(.)="数据分析"]'),
    )
    return _unique_visible(candidates, "数据分析菜单")


def navigate_to_content_analysis(
    page: Page,
    *,
    debug: bool = False,
    debug_dir: Path | None = None,
) -> None:
    """只通过可见文本和语义角色进入数据分析、内容分析。"""

    heading = _content_analysis_heading(page)
    if heading.count() == 1 and heading.is_visible():
        LOGGER.info("当前已位于内容分析页面")
        return

    try:
        content_analysis = _content_analysis_link(page)
    except ExportReportError:
        data_analysis = _data_analysis_toggle(page)
        data_analysis.click()

        # 微信可能在展开父菜单时直接加载默认的“内容分析”页面。
        try:
            heading.wait_for(state="visible", timeout=3_000)
            LOGGER.info("数据分析已直接打开内容分析页面")
            return
        except PlaywrightTimeoutError:
            pass

        try:
            content_analysis = _content_analysis_link(page)
        except ExportReportError as exc:
            log_visible_menu_texts(page)
            if debug and debug_dir is not None:
                manual_content_analysis_handoff(page, debug_dir)
                LOGGER.info("已由用户手动进入内容分析页面")
                return
            raise ExportReportError(
                "点击数据分析后没有出现内容分析子菜单；页面结构可能已变化"
            ) from exc

    content_analysis.click()
    try:
        heading.wait_for(state="visible", timeout=15_000)
    except PlaywrightTimeoutError as exc:
        raise ExportReportError("点击内容分析后，页面主标题未加载") from exc
    LOGGER.info("已进入内容分析页面")


def _only_visible(locator: Locator, description: str) -> Locator:
    """从重复渲染的控件中取唯一可见项。

    微信页面会为吸顶工具栏复制日期控件，因此 DOM 数量不能代表
    实际可操作数量。
    """

    visible = [locator.nth(index) for index in range(locator.count()) if locator.nth(index).is_visible()]
    if len(visible) != 1:
        reason = "匹配到多个可见元素" if visible else "没有找到可见元素"
        raise ExportReportError(f"{description}：{reason}，为避免误操作已停止")
    return visible[0]


def _visible_date_input(page: Page, placeholder: str) -> Locator:
    return _only_visible(
        page.get_by_placeholder(placeholder, exact=True),
        f"{placeholder}输入框",
    )


def _calendar_day(page: Page, target_date: date) -> Locator:
    year = f"{target_date.year}年"
    month = f"{target_date.month:02d}月"
    day = str(target_date.day)
    # 日期数字会在多个月份中重复；以可见面板的年、月标题限定具体日期。
    locator = page.locator(
        "xpath=//div[contains(@class, 'weui-desktop-picker__panel_day') "
        f"and .//span[normalize-space()='{year}'] "
        f"and .//span[normalize-space()='{month}']]"
        f"//a[normalize-space()='{day}' "
        "and not(contains(@class, 'weui-desktop-picker__disabled')) "
        "and not(contains(@class, 'weui-desktop-picker__faded'))]"
    )
    return _only_visible(locator, f"{target_date.isoformat()}日期")


def _select_calendar_date(page: Page, placeholder: str, target_date: date) -> None:
    date_input = _visible_date_input(page, placeholder)
    date_input.click()
    try:
        day = _calendar_day(page, target_date)
    except ExportReportError as exc:
        raise ExportReportError(
            f"日历未显示 {target_date.isoformat()}；当前阶段仅支持页面已加载的可选日期"
        ) from exc
    day.click()
    date_input.wait_for(state="visible", timeout=DATE_PICKER_TIMEOUT_MS)


def select_report_date(page: Page, target_date: date) -> None:
    """默认使用真实快捷项“昨日”，自定义日期通过只读日历控件选择。"""

    if target_date == default_report_date():
        try:
            yesterday = _named_action(page, ("昨日", "昨天"), "昨日日期选项")
            yesterday.click()
            LOGGER.info("已选择昨日：%s", target_date)
            return
        except ExportReportError:
            LOGGER.info("页面没有独立的昨日选项，尝试带标签的日期输入框")

    _select_calendar_date(page, "开始日期", target_date)
    _select_calendar_date(page, "结束日期", target_date)
    LOGGER.info("已选择内容分析日期：%s", target_date)


def _trigger_content_download(page: Page):
    log_page_actions(page)
    # 真实页面中唯一的明细下载入口是链接“下载数据明细”。
    export_action = _unique_visible(
        (
            page.get_by_role("link", name="下载数据明细", exact=True),
            page.locator(
                "xpath=//a[normalize-space()='下载数据明细' "
                "and contains(@href, 'action=download_summary_tendency')]"
            ),
        ),
        "内容分析下载链接",
    )
    try:
        with page.expect_download(timeout=DOWNLOAD_TIMEOUT_MS) as download_info:
            export_action.click()
        return download_info.value
    except PlaywrightTimeoutError as exc:
        raise ExportReportError("点击“下载数据明细”后未检测到 Playwright 下载事件") from exc


def collect_page_actions(page: Page) -> dict[str, list[dict[str, str]]]:
    """收集可见按钮、链接和输入框，便于页面变化时继续定位。"""

    result: dict[str, list[dict[str, str]]] = {"buttons": [], "links": [], "inputs": []}
    for role, key in (("button", "buttons"), ("link", "links")):
        locator = page.get_by_role(role)
        for index in range(locator.count()):
            item = locator.nth(index)
            if not item.is_visible():
                continue
            text = " ".join(item.inner_text().split())
            result[key].append({"text": text})
    inputs = page.locator("input")
    for index in range(inputs.count()):
        item = inputs.nth(index)
        if item.is_visible():
            result["inputs"].append({"placeholder": item.get_attribute("placeholder") or ""})
    return result


def log_page_actions(page: Page) -> dict[str, list[dict[str, str]]]:
    actions = collect_page_actions(page)
    button_texts = [item["text"] for item in actions["buttons"] if item["text"]]
    LOGGER.info("当前页面所有可见按钮文本：%s", button_texts or "无文本按钮")
    return actions


def save_export_debug(page: Page, debug_dir: Path) -> None:
    from collector.debug import save_debug_artifacts

    save_debug_artifacts(page, debug_dir)
    actions = collect_page_actions(page)
    path = debug_dir / "buttons.json"
    path.write_text(json.dumps(actions, ensure_ascii=False, indent=2), encoding="utf-8")
    LOGGER.info("页面控件信息已保存：%s", path)


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


def export_content_report(
    page: Page,
    target_date: date,
    output_dir: Path,
    *,
    debug: bool = False,
    debug_dir: Path | None = None,
) -> ExportResult:
    try:
        navigate_to_content_analysis(page, debug=debug, debug_dir=debug_dir)
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
    except Exception:
        if debug and debug_dir is not None:
            save_export_debug(page, debug_dir)
        raise
