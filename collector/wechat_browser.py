"""启动并管理微信公众号后台专用的有界面浏览器。"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, Playwright

from collector.browser_config import BrowserConfig
from collector.login import is_logged_in_url


LOGGER = logging.getLogger(__name__)


class WechatBrowser:
    def __init__(self, playwright: Playwright, config: BrowserConfig) -> None:
        self.playwright = playwright
        self.config = config
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    def start(self) -> Page:
        self.config.prepare_local_directories()
        LOGGER.info("启动微信公众号专用浏览器（有界面模式）")
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.config.profile_dir),
            headless=False,
            accept_downloads=True,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            viewport=None,
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        return self.page

    def open_login_page(self) -> Page:
        page = self._require_page()
        if not is_logged_in_url(page.url):
            page.goto(self.config.home_url, wait_until="domcontentloaded", timeout=60_000)
        return page

    def save_failure_screenshot(self, label: str = "collector_error") -> Path | None:
        if self.page is None:
            return None
        self.config.screenshot_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = self.config.screenshot_dir / f"{label}_{timestamp}.png"
        try:
            self.page.screenshot(path=str(target), full_page=True)
            LOGGER.info("错误截图已保存：%s", target)
            return target
        except Exception:
            LOGGER.exception("保存错误截图失败")
            return None

    def close(self) -> None:
        if self.context is not None:
            self.context.close()
            self.context = None
            self.page = None

    def _require_page(self) -> Page:
        if self.page is None:
            raise RuntimeError("浏览器尚未启动")
        return self.page
