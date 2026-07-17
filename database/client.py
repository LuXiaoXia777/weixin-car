"""轻量 Supabase REST 客户端，包含超时、重试和脱敏错误。"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ENV_FILE = PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    service_role_key: str

    @classmethod
    def from_env(cls) -> "SupabaseConfig":
        # 始终从项目根目录加载，不依赖启动命令时的当前目录。
        load_dotenv(dotenv_path=PROJECT_ENV_FILE)
        url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not url:
            raise ValueError(
                f"缺少环境变量 SUPABASE_URL；当前配置文件路径：{PROJECT_ENV_FILE}"
            )
        if not url.startswith("https://"):
            raise ValueError("SUPABASE_URL 必须以 https:// 开头")
        if not key:
            raise ValueError(
                "缺少环境变量 SUPABASE_SERVICE_ROLE_KEY；"
                f"当前配置文件路径：{PROJECT_ENV_FILE}"
            )
        return cls(url=url, service_role_key=key)


class SupabaseRestClient:
    def __init__(
        self,
        config: SupabaseConfig,
        *,
        timeout: int = 30,
        max_attempts: int = 4,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = f"{config.url}/rest/v1"
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.session = session or requests.Session()
        self.headers = {
            "apikey": config.service_role_key,
            "Authorization": f"Bearer {config.service_role_key}",
            "Content-Type": "application/json",
        }

    def request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        json: Any = None,
        prefer: str | None = None,
    ) -> Any:
        headers = dict(self.headers)
        if prefer:
            headers["Prefer"] = prefer
        last_error: Exception | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.request(
                    method,
                    f"{self.base_url}/{table}",
                    params=params,
                    json=json,
                    headers=headers,
                    timeout=self.timeout,
                )
                if response.status_code in RETRYABLE_STATUS and attempt < self.max_attempts:
                    time.sleep(2 ** (attempt - 1))
                    continue
                response.raise_for_status()
                return response.json() if response.content else None
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempt == self.max_attempts:
                    break
                time.sleep(2 ** (attempt - 1))
            except requests.HTTPError as exc:
                body = exc.response.text[:500] if exc.response is not None else ""
                raise RuntimeError(f"Supabase 请求失败：HTTP错误；响应={body}") from exc

        raise RuntimeError("Supabase 请求失败：网络连接或超时，已完成重试") from last_error
