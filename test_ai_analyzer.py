"""DeepSeek 运营分析模块单元测试。"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import requests

from services.ai_analyzer import analyze_report, load_report


SAMPLE_REPORT = {
    "date": "2026-07-16",
    "overview": {
        "views": {"value": 6673, "previous": 8864, "change_rate": -0.2472},
        "shares": {"value": 91, "previous": 114, "change_rate": -0.2018},
    },
    "account_score": {"score": 62, "level": "需关注", "reasons": []},
    "daily_trend": [{"date": "2026-07-16", "views": 6673, "shares": 91, "articles": 2}],
    "hot_article_analysis": {
        "title": "小鹏MONA L03，这3个槽点和3个优点，买前最好先知道",
        "views": 14644,
        "multiple": "2.0x",
        "traffic_source": "推荐",
        "reason": ["数字清单"],
        "formula": "车型+数字清单",
    },
    "top5_articles": [{"title": "小鹏MONA L03，这3个槽点和3个优点，买前最好先知道", "views": 14644, "category": "买车建议"}],
    "top_articles": [
        {
            "rank": 1,
            "title": "小鹏MONA L03，这3个槽点和3个优点，买前最好先知道",
            "read_users": 14644,
            "missing_metrics": ["favorite_rate", "follower_efficiency"],
        }
    ],
    "trend_analysis": [{"metric": "article_count", "value": 7}],
    "channel_analysis": [
        {"title": "小鹏MONA L03", "main_channel": "推荐", "read_users": 9000}
    ],
}

VALID_RESULT = {
    "summary": "7月16日阅读6673，较昨日下降24.72%。",
    "best_article": {
        "title": "小鹏MONA L03，这3个槽点和3个优点，买前最好先知道",
        "reason": "阅读人数14644；收藏率和涨粉效率缺失，其他原因暂无法判断。",
    },
    "content_trend": "近7天发布7篇；其余趋势数据不足，暂无法判断。",
    "problems": "阅读和分享分别较昨日下降24.72%和20.18%。",
    "weekly_content_patterns": [
        "数字清单标题阅读14644。",
        "买车建议主题当前排名第一。",
        "其他主题样本不足，暂无法判断是否减少。",
    ],
    "tomorrow_suggestions": [
        {"title": "L03买前必须知道的3项取舍", "reason": "延续数字清单", "reference_data": "同类标题14644阅读", "expected_performance": "有望高于近期均值"},
        {"title": "L03和C10怎么选", "reason": "测试车型对比", "reference_data": "主要渠道为推荐", "expected_performance": "数据不足，暂无法判断"},
        {"title": "15万买新能源SUV哪些配置不能省", "reason": "服务购买决策", "reference_data": "买车建议排名第一", "expected_performance": "数据不足，暂无法判断"},
    ],
}


class AIAnalyzerTests(unittest.TestCase):
    @patch("services.ai_analyzer.requests.post")
    def test_mock_deepseek_response(self, post: Mock) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(VALID_RESULT, ensure_ascii=False)}}]
        }
        post.return_value = response

        result = analyze_report(
            SAMPLE_REPORT, api_key="test-key", model="deepseek-chat"
        )

        self.assertEqual(result.best_article.title, VALID_RESULT["best_article"]["title"])
        self.assertEqual(len(result.tomorrow_suggestions), 3)
        self.assertEqual(result.tomorrow_suggestions[0].title, "L03买前必须知道的3项取舍")
        request_body = post.call_args.kwargs["json"]
        self.assertEqual(request_body["response_format"], {"type": "json_object"})
        self.assertIn("14644", request_body["messages"][1]["content"])

    @patch("services.ai_analyzer.requests.post")
    def test_api_error_is_wrapped(self, post: Mock) -> None:
        post.side_effect = requests.Timeout("timeout")
        with self.assertRaisesRegex(RuntimeError, "DeepSeek API 请求失败"):
            analyze_report(SAMPLE_REPORT, api_key="test-key", model="deepseek-chat")

    @patch("services.ai_analyzer.requests.post")
    def test_invalid_analysis_json_is_rejected(self, post: Mock) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": "不是 JSON"}}]
        }
        post.return_value = response
        with self.assertRaisesRegex(RuntimeError, "JSON 解析或字段校验失败"):
            analyze_report(SAMPLE_REPORT, api_key="test-key", model="deepseek-chat")

    def test_load_report(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(SAMPLE_REPORT), encoding="utf-8")
            loaded = load_report(path)
        self.assertEqual(loaded["date"], "2026-07-16")


if __name__ == "__main__":
    unittest.main()
