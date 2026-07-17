"""将日报 JSON 生成为适合飞书卡片展示的 PNG 图表。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


CHINESE_FONTS = ["PingFang SC", "Arial Unicode MS", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["font.sans-serif"] = CHINESE_FONTS
plt.rcParams["axes.unicode_minus"] = False


def _prepare_output(path: Path) -> Path:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def generate_trend_chart(report: dict[str, Any], output_path: Path) -> Path:
    rows = report.get("daily_trend") or []
    if not rows:
        raise ValueError("report.json 缺少 daily_trend，无法生成7日趋势图")
    dates = [str(row.get("date", ""))[5:] for row in rows]
    views = [row.get("views") for row in rows]
    if all(value is None for value in views):
        raise ValueError("daily_trend 没有可用阅读数据")

    path = _prepare_output(output_path)
    figure, axis = plt.subplots(figsize=(10, 4.8), dpi=160)
    figure.patch.set_facecolor("#F7F9FC")
    axis.set_facecolor("#F7F9FC")
    numeric = [value if value is not None else float("nan") for value in views]
    axis.plot(dates, numeric, color="#3370FF", linewidth=3, marker="o", markersize=7)
    axis.fill_between(dates, numeric, color="#3370FF", alpha=0.10)
    for x, value in zip(dates, views):
        if value is not None:
            axis.annotate(f"{value:,}", (x, value), xytext=(0, 10), textcoords="offset points", ha="center", fontsize=9)
    axis.set_title("近7天阅读趋势", loc="left", fontsize=16, fontweight="bold", pad=18)
    axis.set_ylabel("阅读人数")
    axis.grid(axis="y", alpha=0.18)
    axis.spines[["top", "right", "left"]].set_visible(False)
    figure.tight_layout()
    figure.savefig(path, bbox_inches="tight", facecolor=figure.get_facecolor())
    plt.close(figure)
    return path


def generate_top_articles_chart(report: dict[str, Any], output_path: Path) -> Path:
    rows = (report.get("top5_articles") or [])[:5]
    if not rows:
        raise ValueError("report.json 缺少 top5_articles，无法生成排行图")
    titles = [str(row.get("title") or "未命名") for row in rows]
    labels = [title if len(title) <= 22 else f"{title[:21]}…" for title in titles]
    views = [row.get("views") or 0 for row in rows]

    path = _prepare_output(output_path)
    figure, axis = plt.subplots(figsize=(10, 5.8), dpi=160)
    figure.patch.set_facecolor("#F7F9FC")
    axis.set_facecolor("#F7F9FC")
    positions = list(range(len(rows)))
    bars = axis.barh(positions, views, color=["#FF7D00", "#3370FF", "#6C5CE7", "#00B578", "#8F959E"][: len(rows)])
    axis.set_yticks(positions, [f"TOP{i + 1}  {label}" for i, label in enumerate(labels)])
    axis.invert_yaxis()
    axis.set_title("TOP5文章阅读排行", loc="left", fontsize=16, fontweight="bold", pad=18)
    axis.set_xlabel("阅读人数")
    axis.grid(axis="x", alpha=0.18)
    axis.spines[["top", "right", "left"]].set_visible(False)
    for bar, value in zip(bars, views):
        axis.text(bar.get_width(), bar.get_y() + bar.get_height() / 2, f"  {value:,}", va="center", fontsize=9)
    figure.tight_layout()
    figure.savefig(path, bbox_inches="tight", facecolor=figure.get_facecolor())
    plt.close(figure)
    return path


def generate_report_charts(report: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    return {
        "trend": generate_trend_chart(report, output_dir / "daily_trend.png"),
        "top5": generate_top_articles_chart(report, output_dir / "top5_articles.png"),
    }
