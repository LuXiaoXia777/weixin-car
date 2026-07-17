"""微信公众号后台专用浏览器配置。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BrowserConfig:
    """第一阶段只允许启动有界面的独立 Chromium。"""

    project_root: Path
    login_timeout_seconds: int = 300
    home_url: str = "https://mp.weixin.qq.com/"

    @property
    def profile_dir(self) -> Path:
        return self.project_root / "wechat-browser-profile"

    @property
    def screenshot_dir(self) -> Path:
        return self.project_root / "screenshots"

    @property
    def log_dir(self) -> Path:
        return self.project_root / "logs"

    @property
    def import_dir(self) -> Path:
        return self.project_root / "data" / "import"

    @property
    def debug_dir(self) -> Path:
        return self.project_root / "debug"

    def prepare_local_directories(self) -> None:
        """创建只保存在本机且被 Git 忽略的运行目录。"""

        for directory in (
            self.profile_dir,
            self.screenshot_dir,
            self.log_dir,
            self.import_dir,
            self.debug_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        # 登录目录只应由当前本机用户访问；Windows 不支持该权限模型。
        try:
            self.profile_dir.chmod(0o700)
        except OSError:
            pass
