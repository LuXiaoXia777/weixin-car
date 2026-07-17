"""微信后台 Excel/CSV -> Supabase 导入命令。"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from database.client import SupabaseConfig, SupabaseRestClient
from database.repository import SupabaseRepository
from services.import_service import parse_import_file


logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导入微信公众平台 Excel/CSV 数据到 Supabase")
    parser.add_argument("file", type=Path, help="微信公众平台导出的 .xlsx 或 .csv 文件")
    parser.add_argument("--account-name", default="车事人话", help="公众号名称")
    parser.add_argument("--dry-run", action="store_true", help="只解析和校验，不写入 Supabase")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
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
