"""飞书图片上传服务测试。"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

import requests

from services.feishu_image_uploader import FeishuImageUploader


def response(payload: dict, *, status_code: int = 200) -> Mock:
    item = Mock(status_code=status_code)
    item.raise_for_status.return_value = None
    item.json.return_value = payload
    return item


class FeishuImageUploaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Mock()
        self.uploader = FeishuImageUploader(
            "cli_test_app_id",
            "test-app-secret",
            session=self.session,
        )

    def test_get_tenant_access_token_mock(self) -> None:
        self.session.post.return_value = response(
            {"code": 0, "msg": "ok", "tenant_access_token": "tenant-token"}
        )
        with self.assertLogs("services.feishu_image_uploader", level="INFO") as logs:
            token = self.uploader.get_tenant_access_token()
        self.assertEqual(token, "tenant-token")
        self.assertEqual(self.session.post.call_count, 1)
        self.assertTrue(any("token 获取成功" in line for line in logs.output))
        self.assertFalse(any("test-app-secret" in line for line in logs.output))

    def test_upload_image_returns_image_key(self) -> None:
        self.session.post.side_effect = [
            response({"code": 0, "tenant_access_token": "tenant-token"}),
            response({"code": 0, "data": {"image_key": "img_test_key"}}),
        ]
        with TemporaryDirectory() as directory:
            image = Path(directory) / "views_trend.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\nmock")
            with self.assertLogs("services.feishu_image_uploader", level="INFO") as logs:
                image_key = self.uploader.upload_image(image)

        self.assertEqual(image_key, "img_test_key")
        upload_call = self.session.post.call_args_list[1]
        self.assertEqual(upload_call.kwargs["data"], {"image_type": "message"})
        self.assertIn("image", upload_call.kwargs["files"])
        self.assertTrue(any("image_key=img_test_key" in line for line in logs.output))

    def test_upload_images_returns_both_keys_and_reuses_token(self) -> None:
        self.session.post.side_effect = [
            response({"code": 0, "tenant_access_token": "tenant-token"}),
            response({"code": 0, "data": {"image_key": "img_trend"}}),
            response({"code": 0, "data": {"image_key": "img_top"}}),
        ]
        with TemporaryDirectory() as directory:
            trend = Path(directory) / "views_trend.png"
            top = Path(directory) / "top_articles.png"
            trend.write_bytes(b"png")
            top.write_bytes(b"png")
            keys = self.uploader.upload_images({"trend": trend, "top5": top})

        self.assertEqual(keys, {"trend": "img_trend", "top5": "img_top"})
        self.assertEqual(self.session.post.call_count, 3)

    def test_upload_failure_degrades_to_empty_keys(self) -> None:
        token_response = response({"code": 0, "tenant_access_token": "tenant-token"})
        failed_upload = response({})
        failed_upload.raise_for_status.side_effect = requests.HTTPError("403 forbidden")
        self.session.post.side_effect = [token_response, failed_upload]
        with TemporaryDirectory() as directory:
            image = Path(directory) / "views_trend.png"
            image.write_bytes(b"png")
            with self.assertLogs("services.feishu_image_uploader", level="ERROR") as logs:
                keys = self.uploader.upload_images({"trend": image})

        self.assertEqual(keys, {})
        self.assertTrue(any("降级为文字版" in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()
