"""微信公众号后台页面调试信息采集，仅保存到本机。"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from playwright.sync_api import Page


LOGGER = logging.getLogger(__name__)
KNOWN_MENU_NAMES = (
    "首页",
    "内容管理",
    "互动管理",
    "数据分析",
    "数据与分析",
    "内容分析",
    "用户分析",
    "菜单分析",
    "消息分析",
    "收入变现",
    "账号成长",
    "广告与服务",
    "设置与开发",
)


@dataclass(frozen=True)
class NavigationTrace:
    before_url: str
    before_title: str
    after_url: str
    after_title: str


def save_debug_artifacts(page: Page, debug_dir: Path, prefix: str = "") -> tuple[Path, Path]:
    """保存截图和当前 HTML；文件可能含账号信息，目录必须保持 Git 忽略。"""

    debug_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = debug_dir / f"{prefix}screenshot.png"
    html_path = debug_dir / f"{prefix}page.html"
    page.screenshot(path=str(screenshot_path), full_page=True)
    html_path.write_text(page.content(), encoding="utf-8")
    LOGGER.info("调试截图已保存：%s", screenshot_path)
    LOGGER.info("调试 HTML 已保存：%s", html_path)
    return screenshot_path, html_path


def collect_visible_menu_texts(page: Page, limit: int = 200) -> list[str]:
    """只通过 role/text 收集可见菜单文字，不依赖 CSS 结构。"""

    texts: list[str] = []
    seen: set[str] = set()

    def add_text(raw: str) -> None:
        for line in raw.splitlines():
            value = " ".join(line.split())
            if value and value not in seen:
                seen.add(value)
                texts.append(value)

    for role in ("menuitem", "link", "button", "tab"):
        locator = page.get_by_role(role)
        for index in range(min(locator.count(), limit)):
            item = locator.nth(index)
            if item.is_visible():
                add_text(item.inner_text())

    # 微信部分侧栏项不是标准语义元素，使用精确文本补充已知菜单。
    for name in KNOWN_MENU_NAMES:
        locator = page.get_by_text(name, exact=True)
        if locator.count() == 1 and locator.is_visible():
            add_text(name)

    return texts[:limit]


def log_visible_menu_texts(page: Page) -> list[str]:
    texts = collect_visible_menu_texts(page)
    if texts:
        LOGGER.warning("当前页面可见菜单文本：\n%s", "\n".join(texts))
    else:
        LOGGER.warning("当前页面没有检测到可见菜单文本")
    return texts


def manual_content_analysis_handoff(page: Page, debug_dir: Path) -> NavigationTrace:
    """等待用户亲自点击内容分析，并记录点击前后的页面信息。"""

    before_url = page.url
    before_title = page.title()
    save_debug_artifacts(page, debug_dir)
    print("\n没有稳定识别到“内容分析”。")
    print("请在保持打开的浏览器中手动点击一次“内容分析”，进入页面后回到终端。")
    input("完成点击后按回车继续：")
    page.wait_for_load_state("domcontentloaded")
    after_url = page.url
    after_title = page.title()
    trace = NavigationTrace(before_url, before_title, after_url, after_title)
    trace_path = debug_dir / "navigation.json"
    trace_path.write_text(json.dumps(asdict(trace), ensure_ascii=False, indent=2), encoding="utf-8")
    save_debug_artifacts(page, debug_dir, prefix="after_manual_")
    LOGGER.info("人工点击前 URL：%s", before_url)
    LOGGER.info("人工点击后 URL：%s", after_url)
    LOGGER.info("人工点击后页面标题：%s", after_title)
    return trace
