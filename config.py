"""应用配置：所有敏感值均从环境变量读取。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str
    feishu_webhook_url: str
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_base_url: str = "https://api.deepseek.com"
    articles_csv: Path = BASE_DIR / "data" / "articles.csv"
    prompt_file: Path = BASE_DIR / "prompts" / "analysis_prompt.txt"

    @classmethod
    def from_env(cls, *, require_feishu: bool = True) -> "Settings":
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        webhook = os.getenv("FEISHU_WEBHOOK_URL", "").strip()
        if not api_key:
            raise ValueError("缺少环境变量 DEEPSEEK_API_KEY")
        if require_feishu and not webhook:
            raise ValueError("缺少环境变量 FEISHU_WEBHOOK_URL")
        return cls(
            deepseek_api_key=api_key,
            feishu_webhook_url=webhook,
            feishu_app_id=os.getenv("FEISHU_APP_ID", "").strip(),
            feishu_app_secret=os.getenv("FEISHU_APP_SECRET", "").strip(),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash").strip(),
            deepseek_base_url=os.getenv(
                "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
            ).rstrip("/"),
            articles_csv=Path(os.getenv("ARTICLES_CSV", BASE_DIR / "data" / "articles.csv")),
        )
