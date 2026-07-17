"""飞书日报发送模块测试。"""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import requests

from services.ai_analyzer import AIAnalysisResult
from services.feishu_sender import build_card, send_card


REPORT = {
    "date": "2026-07-16",
    "overview": {
        "views": {"value": 6673, "previous": 8864, "change_rate": -0.2472},
        "shares": {"value": 91, "previous": 114, "change_rate": -0.2018},
        "favorites": {"value": 5, "previous": 11, "change_rate": -0.5455},
        "publish_count": {"value": 2, "previous": 1, "change_rate": 1.0},
    },
    "account_score": {"score": 82, "level": "良好", "reasons": ["阅读表现稳定"]},
    "daily_trend": [
        {"date": "2026-07-15", "views": 8864, "shares": 114, "articles": 1},
        {"date": "2026-07-16", "views": 6673, "shares": 91, "articles": 2},
    ],
    "hot_article_analysis": {
        "title": "小鹏MONA L03买前分析", "views": 14644, "multiple": "3.2x",
        "traffic_source": "推荐", "reason": ["价格对比", "购买决策需求"],
        "formula": "品牌+价格差+值不值得",
    },
    "top5_articles": [
        {"title": "小鹏MONA L03买前分析", "views": 14644, "category": "买车建议"}
    ],
    "top_articles": [
        {"rank": 1, "title": "小鹏MONA L03买前分析", "read_users": 14644}
    ],
    "trend_analysis": [],
    "channel_analysis": [],
}

ANALYSIS = AIAnalysisResult(
    summary="阅读人数较昨日下降。",
    best_article={"title": "小鹏MONA L03买前分析", "reason": "阅读人数14644。"},
    content_trend="近7天买车建议类内容表现较好。",
    problems="收藏人数较昨日下降54.55%。",
    weekly_content_patterns=["买前分析标题表现最好", "买车建议平均阅读最高", "减少无数据支撑的泛趋势稿"],
    tomorrow_suggestions=[
        {"title": "写L03配置取舍", "reason": "最佳文章验证", "reference_data": "14644阅读", "expected_performance": "高于近期均值"},
        {"title": "测试同价位对比", "reason": "服务选车决策", "reference_data": "推荐为主要渠道", "expected_performance": "数据不足，暂无法判断"},
        {"title": "补充真实用车成本", "reason": "测试新方向", "reference_data": "当前无成本类样本", "expected_performance": "数据不足，暂无法判断"},
    ],
)


class FeishuSenderTests(unittest.TestCase):
    def test_card_json_structure(self) -> None:
        payload = build_card(REPORT, ANALYSIS)
        self.assertEqual(payload["msg_type"], "interactive")
        card = payload["card"]
        self.assertEqual(card["header"]["title"]["content"], "🚗 车事人话公众号运营日报 2.0")
        serialized = str(card["elements"])
        self.assertIn("数据日期：2026-07-16", serialized)
        self.assertIn("↓24.7%", serialized)
        self.assertIn("↑100.0%", serialized)
        self.assertIn("小鹏MONA L03买前分析", serialized)
        self.assertIn("82分", serialized)
        self.assertIn("3. 补充真实用车成本", serialized)

    def test_card_contains_uploaded_chart_images(self) -> None:
        payload = build_card(REPORT, ANALYSIS, chart_image_keys={"trend": "img_trend", "top5": "img_top"})
        images = [element for element in payload["card"]["elements"] if element.get("tag") == "img"]
        self.assertEqual([item["img_key"] for item in images], ["img_trend", "img_top"])

    @patch("services.feishu_sender.requests.post")
    def test_mock_send_success(self, post: Mock) -> None:
        response = Mock(status_code=200)
        response.raise_for_status.return_value = None
        response.json.return_value = {"code": 0, "msg": "success"}
        post.return_value = response

        result = send_card("https://example.invalid/webhook", build_card(REPORT, ANALYSIS))

        self.assertEqual(result["code"], 0)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs["json"]["msg_type"], "interactive")

    @patch("services.feishu_sender.requests.post")
    def test_network_error_retries_three_times(self, post: Mock) -> None:
        post.side_effect = requests.ConnectionError("offline")
        with self.assertRaisesRegex(RuntimeError, "已重试3次"):
            send_card(
                "https://example.invalid/webhook",
                build_card(REPORT, ANALYSIS),
                retry_delay=0,
            )
        self.assertEqual(post.call_count, 3)

    @patch("services.feishu_sender.requests.post")
    def test_http_error_is_logged_and_not_retried(self, post: Mock) -> None:
        response = Mock(status_code=500)
        response.raise_for_status.side_effect = requests.HTTPError("server error")
        post.return_value = response
        with self.assertLogs("services.feishu_sender", level="ERROR") as logs:
            with self.assertRaisesRegex(RuntimeError, "HTTP错误：500"):
                send_card("https://example.invalid/webhook", build_card(REPORT, ANALYSIS))
        self.assertEqual(post.call_count, 1)
        self.assertTrue(any("status=500" in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()
