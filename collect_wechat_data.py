"""微信公众号后台本机半自动采集助手入口（第一阶段：登录后台）。"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from collector.browser_config import BrowserConfig
from collector.login import wait_for_manual_login
from collector.wechat_browser import WechatBrowser


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="打开微信公众号后台并等待用户手动登录")
    parser.add_argument(
        "--login-timeout",
        type=int,
        default=300,
        help="等待扫码登录的秒数，默认 300",
    )
    return parser.parse_args()


def configure_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"wechat_collector_{datetime.now():%Y%m%d}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_file, encoding="utf-8")],
    )


def main() -> None:
    args = parse_args()
    if args.login_timeout <= 0:
        raise ValueError("--login-timeout 必须大于 0")

    config = BrowserConfig(PROJECT_ROOT, login_timeout_seconds=args.login_timeout)
    config.prepare_local_directories()
    configure_logging(config.log_dir)

    with sync_playwright() as playwright:
        browser = WechatBrowser(playwright, config)
        try:
            page = browser.start()
            browser.open_login_page()
            wait_for_manual_login(page, config.login_timeout_seconds)
            LOGGER.info("第一阶段完成：已进入微信公众号后台")
            input("浏览器将保持打开。检查完成后按回车键退出：")
        except Exception:
            browser.save_failure_screenshot()
            LOGGER.exception("微信公众号后台登录助手运行失败")
            raise
        finally:
            browser.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        LOGGER.info("用户已终止运行")
    except Exception:
        sys.exit(1)
