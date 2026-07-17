"""飞书自定义机器人推送。"""

from __future__ import annotations

from datetime import date

import requests

from services.ai_analysis import AnalysisResult
from services.data_loader import Article


def _escape_markdown(text: str) -> str:
    return text.replace("\\", "\\\\").replace("*", "\\*").replace("_", "\\_")


def build_report(
    report_date: date,
    totals: dict[str, int],
    best: Article,
    analysis: AnalysisResult,
) -> str:
    suggestions = "\n".join(
        f"{index}. {_escape_markdown(item)}"
        for index, item in enumerate(analysis.suggestions, start=1)
    )
    return f"""**日期：** {report_date.isoformat()}

📊 **数据概览**

文章：{totals['articles']} 篇  
阅读：{totals['views']:,}  
点赞：{totals['likes']:,}｜分享：{totals['shares']:,}｜评论：{totals['comments']:,}  
涨粉：{totals['new_followers']:+,}

🔥 **今日最佳文章**

标题：{_escape_markdown(best.title)}  
阅读：{best.views:,}  
互动：{best.likes + best.shares + best.comments:,}

**AI 分析：** {_escape_markdown(analysis.reason)}

📈 **内容趋势**

{_escape_markdown(analysis.trend)}

📝 **七日总结**

{_escape_markdown(analysis.summary)}

💡 **明日选题建议**

{suggestions}"""


def send_report(webhook_url: str, markdown: str, *, timeout: int = 15) -> None:
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": "🚗 车事人话公众号日报"},
            },
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": markdown}}],
        },
    }
    response = requests.post(webhook_url, json=payload, timeout=timeout)
    response.raise_for_status()
    result = response.json()
    if result.get("code", result.get("StatusCode", 0)) != 0:
        raise RuntimeError(f"飞书推送失败：{result}")
