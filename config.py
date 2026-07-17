"""应用配置：所有敏感值均从环境变量读取。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    feishu_webhook_url: str
    openai_model: str = "gpt-5.6-luna"
    articles_csv: Path = BASE_DIR / "data" / "articles.csv"
    prompt_file: Path = BASE_DIR / "prompts" / "analysis_prompt.txt"

    @classmethod
    def from_env(cls, *, require_feishu: bool = True) -> "Settings":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        webhook = os.getenv("FEISHU_WEBHOOK_URL", "").strip()
        if not api_key:
            raise ValueError("缺少环境变量 OPENAI_API_KEY")
        if require_feishu and not webhook:
            raise ValueError("缺少环境变量 FEISHU_WEBHOOK_URL")
        return cls(
            openai_api_key=api_key,
            feishu_webhook_url=webhook,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.6-luna").strip(),
            articles_csv=Path(os.getenv("ARTICLES_CSV", BASE_DIR / "data" / "articles.csv")),
        )
