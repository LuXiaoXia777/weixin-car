"""CSV/XLSX 解析与幂等导入单元测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from services.import_service import parse_import_file


ARTICLE_HEADERS = ["发布时间", "文章标题", "文章链接", "内容类型", "阅读量", "点赞", "分享", "留言", "新增粉丝"]
ARTICLE_ROW = ["2026-07-16", "小鹏L03比M03贵2万到底贵在哪", "https://example.com/a", "横向对比", 3568, 128, 56, 23, 39]


class ImportFileTests(unittest.TestCase):
    def test_csv_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "articles.csv"
            path.write_text(
                ",".join(ARTICLE_HEADERS) + "\n" + ",".join(map(str, ARTICLE_ROW)) + "\n",
                encoding="utf-8-sig",
            )
            batch = parse_import_file(path)
            self.assertEqual(len(batch.articles), 1)
            self.assertEqual(batch.articles[0].views, 3568)
            self.assertEqual(batch.articles[0].new_followers, 39)

    def test_xlsx_with_article_and_user_sheets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wechat.xlsx"
            workbook = Workbook()
            article_sheet = workbook.active
            article_sheet.title = "图文数据"
            article_sheet.append(ARTICLE_HEADERS)
            article_sheet.append(ARTICLE_ROW)
            user_sheet = workbook.create_sheet("用户数据")
            user_sheet.append(["数据日期", "新增关注", "取消关注"])
            user_sheet.append(["2026/07/16", 42, 7])
            workbook.save(path)

            batch = parse_import_file(path)
            self.assertEqual(len(batch.articles), 1)
            self.assertEqual(len(batch.user_stats), 1)
            self.assertEqual(batch.user_stats[0].net_followers, 35)

    def test_missing_values_remain_none(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "minimal.csv"
            path.write_text("发布时间,文章标题\n2026-07-16,最小数据文章\n", encoding="utf-8")
            batch = parse_import_file(path)
            self.assertIsNone(batch.articles[0].views)
            self.assertIsNone(batch.articles[0].likes)


if __name__ == "__main__":
    unittest.main()
