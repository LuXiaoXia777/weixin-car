"""单独测试 DeepSeek API，不发送飞书消息。"""

from __future__ import annotations

import json

from config import Settings
from services.ai_analysis import analyze_articles
from services.data_loader import latest_seven_days, load_articles
from services.metrics import build_report_metrics


def main() -> None:
    settings = Settings.from_env(require_feishu=False)
    articles = latest_seven_days(load_articles(settings.articles_csv))
    metrics = build_report_metrics(articles)
    result = analyze_articles(
        articles,
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        prompt_file=settings.prompt_file,
        metrics=metrics,
    )
    print("DeepSeek API连接成功")
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
