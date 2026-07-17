"""使用飞书应用凭证上传消息卡片图片。"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Mapping

import requests


LOGGER = logging.getLogger(__name__)
TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
IMAGE_URL = "https://open.feishu.cn/open-apis/im/v1/images"
IMAGE_TYPE = "message"


def _response_body(response: requests.Response) -> str:
    """返回可用于排查的飞书响应体；不包含请求头或 token。"""
    body = (response.text or "").strip()
    return body if body else "<empty>"


class FeishuImageUploader:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        *,
        timeout: int = 30,
        session: requests.Session | None = None,
    ) -> None:
        if not app_id.strip():
            raise ValueError("FEISHU_APP_ID 不能为空")
        if not app_secret.strip():
            raise ValueError("FEISHU_APP_SECRET 不能为空")
        self.app_id = app_id.strip()
        self._app_secret = app_secret.strip()
        self.timeout = timeout
        self.session = session or requests.Session()
        self._tenant_access_token: str | None = None

    def get_tenant_access_token(self) -> str:
        """获取并缓存 tenant_access_token；日志中不输出密钥或 token。"""
        if self._tenant_access_token:
            return self._tenant_access_token
        try:
            response = self.session.post(
                TOKEN_URL,
                json={"app_id": self.app_id, "app_secret": self._app_secret},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            LOGGER.error("飞书 tenant_access_token 获取失败：%s", exc)
            raise RuntimeError(f"飞书 tenant_access_token 获取失败：{exc}") from exc

        token = payload.get("tenant_access_token")
        if payload.get("code") != 0 or not token:
            message = payload.get("msg", "响应中缺少 tenant_access_token")
            LOGGER.error("飞书 tenant_access_token 获取失败：%s", message)
            raise RuntimeError(f"飞书 tenant_access_token 获取失败：{message}")
        self._tenant_access_token = token
        LOGGER.info("飞书 tenant_access_token 获取成功")
        return token

    def upload_image(self, image_path: Path) -> str:
        """上传一张 PNG，返回可用于卡片 img_key 的 image_key。"""
        path = image_path.expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"找不到待上传图片：{path}")
        if path.stat().st_size <= 0:
            raise ValueError(f"待上传图片为空：{path}")

        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if not mime_type.startswith("image/"):
            raise ValueError(f"待上传文件不是支持的图片类型：{path.name} ({mime_type})")

        file_size = path.stat().st_size
        LOGGER.info(
            "准备上传飞书图片：image_type=%s, file=%s, size=%d bytes, mime_type=%s",
            IMAGE_TYPE,
            path.name,
            file_size,
            mime_type,
        )

        token = self.get_tenant_access_token()
        try:
            with path.open("rb") as image_file:
                # 不手动设置 Content-Type；requests 会为 multipart/form-data 生成正确 boundary。
                response = self.session.post(
                    IMAGE_URL,
                    headers={"Authorization": f"Bearer {token}"},
                    data={"image_type": IMAGE_TYPE},
                    files={"image": (path.name, image_file, mime_type)},
                    timeout=self.timeout,
                )
        except requests.RequestException as exc:
            LOGGER.error("飞书图片上传请求失败：file=%s, error=%s", path.name, exc)
            raise RuntimeError(f"飞书图片上传失败：{path.name}：{exc}") from exc

        body = _response_body(response)
        LOGGER.info("飞书图片上传返回：file=%s, status=%s, body=%s", path.name, response.status_code, body)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            permission_hint = ""
            if '"code":99991672' in body.replace(" ", ""):
                permission_hint = "；请在飞书开放平台开通 im:resource:upload 应用身份权限并发布新版本"
            raise RuntimeError(
                f"飞书图片上传失败：{path.name}：HTTP {response.status_code}{permission_hint}：{body}"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"飞书图片上传失败：{path.name}：返回不是有效 JSON：{body}") from exc

        image_key = (payload.get("data") or {}).get("image_key")
        if payload.get("code") != 0 or not image_key:
            message = payload.get("msg", "响应中缺少 image_key")
            LOGGER.error("飞书图片上传失败：file=%s, error=%s", path.name, message)
            raise RuntimeError(f"飞书图片上传失败：{path.name}：{message}")
        LOGGER.info("飞书图片上传成功：file=%s, image_key=%s", path.name, image_key)
        return image_key

    def upload_images(self, images: Mapping[str, Path]) -> dict[str, str]:
        """尽力上传全部图表；失败返回空/部分结果，由卡片自动降级。"""
        try:
            self.get_tenant_access_token()
        except Exception:
            LOGGER.exception("飞书图片上传已降级：无法获取 tenant_access_token")
            return {}

        image_keys: dict[str, str] = {}
        for name, path in images.items():
            try:
                image_keys[name] = self.upload_image(path)
            except Exception:
                LOGGER.exception("飞书图片上传已降级为文字版：chart=%s", name)
        return image_keys
