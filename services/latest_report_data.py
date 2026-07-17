"""从 Supabase 确定最新成功导入后的日报数据基准。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from database.client import SupabaseRestClient


@dataclass(frozen=True)
class LatestReportData:
    stat_date: date
    collected_at: datetime
    import_completed_at: datetime

    @property
    def report_title(self) -> str:
        return f"{self.stat_date.isoformat()}运营日报"


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_latest_report_data(
    client: SupabaseRestClient,
    account_name: str = "车事人话",
) -> LatestReportData:
    accounts = client.request(
        "GET",
        "wechat_accounts",
        params={"select": "id", "name": f"eq.{account_name}", "limit": "1"},
    )
    if not accounts:
        raise ValueError(f"Supabase 中找不到公众号：{account_name}")
    account_id = accounts[0]["id"]

    imports = client.request(
        "GET",
        "import_runs",
        params={
            "select": "completed_at",
            "account_id": f"eq.{account_id}",
            "status": "eq.success",
            "completed_at": "not.is.null",
            "order": "completed_at.desc",
            "limit": "1",
        },
    )
    if not imports:
        raise ValueError("尚无成功导入记录，无法生成日报")
    completed_at_text = imports[0]["completed_at"]

    stats = client.request(
        "GET",
        "account_daily_stats",
        params={
            "select": "stat_date,collected_at",
            "account_id": f"eq.{account_id}",
            "collected_at": f"lte.{completed_at_text}",
            "order": "stat_date.desc,collected_at.desc",
            "limit": "1",
        },
    )
    if not stats:
        raise ValueError("最新成功导入没有可用的账号每日数据")
    return LatestReportData(
        stat_date=date.fromisoformat(stats[0]["stat_date"]),
        collected_at=_timestamp(stats[0]["collected_at"]),
        import_completed_at=_timestamp(completed_at_text),
    )
