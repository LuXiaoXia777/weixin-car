"""微信公众号后台登录状态检测与扫码等待。"""

from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError


LOGGER = logging.getLogger(__name__)
HOME_PATH = "/cgi-bin/home"
HOME_URL_PATTERN = re.compile(r"https://mp\.weixin\.qq\.com/cgi-bin/home(?:\?.*)?$")


def is_logged_in_url(url: str) -> bool:
    """只使用后台首页 URL 判断，不读取或导出 Cookie。"""

    parsed = urlparse(url)
    return (
        parsed.hostname == "mp.weixin.qq.com"
        and parsed.path == HOME_PATH
        and bool(parse_qs(parsed.query).get("token"))
    )


def is_logged_in(page: Page) -> bool:
    return is_logged_in_url(page.url)


def wait_for_manual_login(page: Page, timeout_seconds: int) -> None:
    """等待用户自己扫码或完成微信安全验证，不自动填写或绕过验证。"""

    if is_logged_in(page):
        LOGGER.info("检测到可复用的微信公众号登录状态")
        return

    LOGGER.info("请在浏览器窗口中扫码登录；如出现安全验证，请手动完成")
    try:
        page.wait_for_url(
            HOME_URL_PATTERN,
            wait_until="domcontentloaded",
            timeout=timeout_seconds * 1000,
        )
    except PlaywrightTimeoutError as exc:
        raise TimeoutError(
            f"等待微信公众号登录超时（{timeout_seconds} 秒），未执行任何绕过操作"
        ) from exc

    if not is_logged_in(page):
        raise RuntimeError("页面已跳转，但没有检测到有效的微信公众号后台登录状态")
    LOGGER.info("微信公众号后台登录成功；状态已保存在本机独立浏览器目录")
