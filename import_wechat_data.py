"""微信后台 Excel/CSV -> Supabase 导入命令。"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from database.client import SupabaseConfig, SupabaseRestClient
from database.repository import SupabaseRepository
from services.import_service import parse_import_file
from services.supabase_writer import SupabaseWechatWriter
from services.wechat_xls_parser import parse_wechat_xls


logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导入微信公众平台 Excel/CSV 数据到 Supabase")
    parser.add_argument("file", type=Path, help="微信公众平台导出的 .xls、.xlsx 或 .csv 文件")
    parser.add_argument("--account-name", default="车事人话", help="公众号名称")
    parser.add_argument("--dry-run", action="store_true", help="只解析和校验，不写入 Supabase")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.file.suffix.lower() == ".xls":
        batch = parse_wechat_xls(args.file)
        LOGGER.info(
            "真实微信 .xls 解析成功：区域A %s行，区域B %s行，"
            "文章 %s篇，文章总阅读 %s条，文章渠道 %s条",
            len(batch.account_channel_trends),
            len(batch.account_content_stats),
            len(batch.articles),
            len(batch.article_totals),
            len(batch.article_channels),
        )
        if args.dry_run:
            LOGGER.info("dry-run 完成，未写入 Supabase")
            return
        client = SupabaseRestClient(SupabaseConfig.from_env())
        result = SupabaseWechatWriter(client).write(args.account_name, batch)
        LOGGER.info("Supabase 真实微信数据入库结果：%s", result)
        return

    batch = parse_import_file(args.file)
    LOGGER.info(
        "文件校验成功：文章 %s 行，用户统计 %s 行",
        len(batch.articles),
        len(batch.user_stats),
    )
    if args.dry_run:
        LOGGER.info("dry-run 完成，未写入 Supabase")
        return

    client = SupabaseRestClient(SupabaseConfig.from_env())
    result = SupabaseRepository(client).import_batch(args.account_name, batch)
    LOGGER.info("Supabase 导入结果：%s", result)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        LOGGER.exception("导入失败")
        sys.exit(1)
