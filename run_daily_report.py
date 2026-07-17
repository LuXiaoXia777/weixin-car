"""微信公众号日报总控入口：采集、入库、分析并推送飞书。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

from database.client import PROJECT_ENV_FILE, SupabaseConfig, SupabaseRestClient
from services.ai_analyzer import AIAnalysisResult, load_report
from services.wechat_xls_parser import WechatXlsBatch, parse_wechat_xls


PROJECT_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class SelectedXls:
    file_path: Path
    period_end: date


def discover_latest_xls(
    import_dir: Path,
    *,
    parser: Callable[[Path], WechatXlsBatch] = parse_wechat_xls,
) -> SelectedXls:
    """按 Excel 内部统计结束日期选择最新报表，而不是依赖文件名。"""
    candidates: list[tuple[date, float, Path]] = []
    errors: list[str] = []
    for path in import_dir.glob("*.xls"):
        try:
            batch = parser(path)
            candidates.append((batch.period_end, path.stat().st_mtime, path.resolve()))
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
    if not candidates:
        detail = f"；无法解析：{' | '.join(errors)}" if errors else ""
        raise FileNotFoundError(f"{import_dir.resolve()} 中没有可用的微信 .xls 报表{detail}")
    period_end, _, file_path = max(candidates, key=lambda item: (item[0], item[1]))
    return SelectedXls(file_path=file_path, period_end=period_end)


def run_command(
    command: list[str],
    *,
    cwd: Path,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """运行一个子步骤；失败时保留子进程的真实错误信息。"""
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=True,
            text=True,
            capture_output=capture_output,
            env=os.environ.copy(),
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        suffix = f"：{detail}" if detail else ""
        raise RuntimeError(f"命令执行失败（退出码 {exc.returncode}）{suffix}") from exc


class DailyReportRegistry:
    """通过 Supabase sync_runs 保存日报发送状态。"""

    def __init__(self, client: SupabaseRestClient, account_name: str = "车事人话") -> None:
        self.client = client
        rows = client.request(
            "GET",
            "wechat_accounts",
            params={"select": "id", "name": f"eq.{account_name}", "limit": "1"},
        )
        if not rows:
            raise ValueError(f"Supabase 中找不到公众号：{account_name}")
        self.account_id = rows[0]["id"]

    @staticmethod
    def sync_type(report_date: date) -> str:
        return f"daily_report:{report_date.isoformat()}"

    def already_sent(self, report_date: date) -> bool:
        rows = self.client.request(
            "GET",
            "sync_runs",
            params={
                "select": "id",
                "account_id": f"eq.{self.account_id}",
                "sync_type": f"eq.{self.sync_type(report_date)}",
                "status": "eq.success",
                "limit": "1",
            },
        )
        return bool(rows)

    def start(self, report_date: date) -> str:
        rows = self.client.request(
            "POST",
            "sync_runs",
            json={
                "account_id": self.account_id,
                "sync_type": self.sync_type(report_date),
                "status": "running",
                "rows_synced": 0,
                "error_message": None,
            },
            prefer="return=representation",
        )
        if not rows:
            raise RuntimeError("Supabase 未返回日报发送记录 ID")
        return rows[0]["id"]

    def finish(self, run_id: str, status: str, error: str | None = None) -> None:
        self.client.request(
            "PATCH",
            "sync_runs",
            params={"id": f"eq.{run_id}"},
            json={
                "status": status,
                "rows_synced": 1 if status == "success" else 0,
                "error_message": error[:500] if error else None,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
            prefer="return=minimal",
        )


class DailyReportPipeline:
    def __init__(
        self,
        project_root: Path = PROJECT_ROOT,
        *,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = run_command,
        latest_xls_finder: Callable[[Path], SelectedXls] = discover_latest_xls,
        registry_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.command_runner = command_runner
        self.latest_xls_finder = latest_xls_finder
        self.registry_factory = registry_factory or self._default_registry
        self.python = sys.executable
        self.report_path = self.project_root / "report.json"
        self.ai_path = self.project_root / "ai_analysis.json"

    @staticmethod
    def _default_registry() -> DailyReportRegistry:
        return DailyReportRegistry(SupabaseRestClient(SupabaseConfig.from_env()))

    def _status(self, step: int, message: str) -> None:
        print(f"[{step}/6] {message}", flush=True)

    def _run(self, command: list[str], *, capture_output: bool = False):
        return self.command_runner(
            command,
            cwd=self.project_root,
            capture_output=capture_output,
        )

    def run(self) -> dict[str, Any]:
        registry = None
        sync_run_id: str | None = None
        try:
            self._status(1, "启动微信后台采集，请按页面提示完成登录或安全验证…")
            self._run([self.python, "collect_wechat_data.py"])
            self._status(1, "微信报表下载完成")

            selected = self.latest_xls_finder(self.project_root / "data" / "import")
            print(
                f"      最新有效报表：{selected.file_path.name}，实际数据截止日期：{selected.period_end}",
                flush=True,
            )

            self._status(2, "导入最新 XLS 到 Supabase…")
            self._run([self.python, "import_wechat_data.py", str(selected.file_path)])
            self._status(2, "Supabase 入库完成")

            self._status(3, "生成确定性指标报告 report.json…")
            self._run(
                [self.python, "-m", "services.analysis_service", "--output", str(self.report_path)]
            )
            report = load_report(self.report_path)
            report_date = date.fromisoformat(report["date"])
            if report_date > selected.period_end:
                raise RuntimeError(
                    f"指标报告日期 {report_date} 晚于 Excel 数据截止日期 {selected.period_end}"
                )
            self._status(3, f"{report_date} 指标报告生成完成")

            registry = self.registry_factory()
            if registry.already_sent(report_date):
                print(f"[跳过] {report_date} 运营日报已成功发送，未重复调用 AI 和飞书。")
                return {"status": "skipped", "date": report_date.isoformat()}
            sync_run_id = registry.start(report_date)

            self._status(4, "调用 DeepSeek 生成运营分析…")
            completed = self._run(
                [self.python, "-m", "services.ai_analyzer", str(self.report_path)],
                capture_output=True,
            )
            analysis = AIAnalysisResult.model_validate_json(completed.stdout)
            temporary = self.ai_path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(analysis.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(self.ai_path)
            self._status(4, "DeepSeek 分析已保存为 ai_analysis.json")

            self._status(5, "生成飞书 Interactive Card…")
            # 卡片由发送模块读取两个经过校验的 JSON 文件生成。
            self._status(5, "飞书卡片数据准备完成")

            self._status(6, "发送飞书运营日报…")
            self._run(
                [
                    self.python,
                    "-m",
                    "services.feishu_sender",
                    "--report",
                    str(self.report_path),
                    "--analysis",
                    str(self.ai_path),
                ]
            )
            registry.finish(sync_run_id, "success")
            print(f"[完成] {report_date} 运营日报已成功发送到飞书。")
            return {"status": "success", "date": report_date.isoformat()}
        except Exception as exc:
            if registry is not None and sync_run_id is not None:
                try:
                    registry.finish(sync_run_id, "failed", str(exc))
                except Exception as registry_exc:
                    print(f"[警告] 记录失败状态时出错：{registry_exc}", file=sys.stderr)
            print(f"[失败] 日报流程已停止：{exc}", file=sys.stderr)
            raise


def main() -> None:
    # 统一从项目根目录读取本地密钥，子进程会继承这些环境变量。
    load_dotenv(PROJECT_ENV_FILE)
    DailyReportPipeline().run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[停止] 用户已终止日报流程。", file=sys.stderr)
        sys.exit(130)
    except Exception:
        sys.exit(1)
