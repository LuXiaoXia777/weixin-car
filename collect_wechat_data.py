"""微信公众号后台本机半自动采集助手入口（第二阶段：导出内容报表）。"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from collector.browser_config import BrowserConfig
from collector.debug import save_debug_artifacts
from collector.export_report import export_content_report, parse_report_date
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
    parser.add_argument(
        "--date",
        help="内容分析报表日期，格式 YYYY-MM-DD；默认昨天",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="保存页面截图/HTML，并在定位失败时等待人工点击",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="导出完成后不等待终端回车，供 launchd 总控流程使用",
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
    report_date = parse_report_date(args.date)

    config = BrowserConfig(PROJECT_ROOT, login_timeout_seconds=args.login_timeout)
    config.prepare_local_directories()
    configure_logging(config.log_dir)

    with sync_playwright() as playwright:
        browser = WechatBrowser(playwright, config)
        try:
            page = browser.start()
            browser.open_login_page()
            wait_for_manual_login(page, config.login_timeout_seconds)
            if args.debug:
                save_debug_artifacts(page, config.debug_dir)
            result = export_content_report(
                page,
                report_date,
                config.import_dir,
                debug=args.debug,
                debug_dir=config.debug_dir if args.debug else None,
            )
            LOGGER.info("第二阶段完成：%s", result.file_path)
            print(f"导出完成：{result.file_path}")
            if not args.non_interactive:
                input("浏览器将保持打开。确认下载结果后按回车键退出：")
        except Exception:
            browser.save_failure_screenshot()
            if args.debug and browser.page is not None:
                try:
                    save_debug_artifacts(browser.page, config.debug_dir)
                except Exception:
                    LOGGER.exception("保存 debug 页面信息失败")
            LOGGER.exception("微信公众号后台登录助手运行失败")
            if args.debug:
                input("调试模式已暂停，浏览器保持打开。检查完成后按回车退出：")
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
