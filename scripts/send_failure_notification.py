"""主日报失败时，通过既有飞书 Webhook 发送简短错误通知。"""

from __future__ import annotations

import argparse
import os
import re
import socket
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_LOG_CHARS = 1800


def redact_secrets(content: str) -> str:
    patterns = (
        (r"(?i)(Authorization\s*:\s*Bearer\s+)[^\s]+", r"\1[REDACTED]"),
        (r"(?i)(FEISHU_WEBHOOK_URL|SUPABASE_SERVICE_ROLE_KEY|DEEPSEEK_API_KEY|FEISHU_APP_SECRET)\s*=\s*[^\s]+", r"\1=[REDACTED]"),
        (r"(https://open\.feishu\.cn/open-apis/bot/v2/hook/)[A-Za-z0-9_-]+", r"\1[REDACTED]"),
    )
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)
    return content


def read_log_tail(path: Path, max_chars: int = MAX_LOG_CHARS) -> str:
    if not path.exists() or not path.is_file():
        return "未找到日志文件"
    content = path.read_text(encoding="utf-8", errors="replace")
    return redact_secrets(content[-max_chars:]).strip() or "日志为空"


def build_failure_card(*, exit_code: int, log_tail: str) -> dict:
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "red",
                "title": {"tag": "plain_text", "content": "⚠️ 车事人话日报执行失败"},
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {"tag": "lark_md", "content": f"**Mac**\n{socket.gethostname()}"},
                        },
                        {
                            "is_short": True,
                            "text": {"tag": "lark_md", "content": f"**退出码**\n{exit_code}"},
                        },
                    ],
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "plain_text",
                        "content": f"时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
                    },
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**最近日志**\n```\n{log_tail}\n```",
                    },
                },
            ],
        },
    }


def send_failure_notification(
    webhook_url: str,
    payload: dict,
    *,
    max_attempts: int = 3,
    timeout: int = 15,
) -> None:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(webhook_url, json=payload, timeout=timeout)
            response.raise_for_status()
            result = response.json()
            if result.get("code", result.get("StatusCode", 0)) != 0:
                raise RuntimeError(f"飞书返回业务错误：{result}")
            return
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            last_error = exc
            if attempt < max_attempts:
                time.sleep(attempt)
    raise RuntimeError(f"飞书失败通知发送失败：{last_error}") from last_error


def main() -> None:
    parser = argparse.ArgumentParser(description="发送日报流程失败通知")
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--log-file", type=Path, required=True)
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    webhook_url = os.getenv("FEISHU_WEBHOOK_URL", "").strip()
    if not webhook_url:
        raise ValueError("缺少环境变量 FEISHU_WEBHOOK_URL")
    payload = build_failure_card(
        exit_code=args.exit_code,
        log_tail=read_log_tail(args.log_file),
    )
    send_failure_notification(webhook_url, payload)
    print("飞书失败通知已发送")


if __name__ == "__main__":
    main()
