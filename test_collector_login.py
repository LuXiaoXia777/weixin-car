"""第一阶段采集助手的无网络单元测试。"""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from collector.browser_config import BrowserConfig
from collector.login import is_logged_in_url


class CollectorLoginTests(unittest.TestCase):
    def test_backend_home_with_token_is_logged_in(self):
        self.assertTrue(
            is_logged_in_url(
                "https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN&token=123456"
            )
        )

    def test_login_page_without_token_is_not_logged_in(self):
        self.assertFalse(is_logged_in_url("https://mp.weixin.qq.com/"))
        self.assertFalse(
            is_logged_in_url("https://mp.weixin.qq.com/cgi-bin/bizlogin?action=startlogin")
        )

    def test_runtime_directories_are_local_to_project(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = BrowserConfig(root)
            config.prepare_local_directories()
            self.assertTrue(config.profile_dir.is_dir())
            self.assertTrue(config.import_dir.is_dir())
            self.assertEqual(config.profile_dir.parent, root)


if __name__ == "__main__":
    unittest.main()
