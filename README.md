# 车事人话 AI 公众号运营助手

本项目是一个需要在本机手动启动的半自动微信公众号数据分析工具。

```text
本机 Playwright 打开微信公众平台
          ↓
用户手动登录/安全验证后导出 XLS
          ↓
解析并写入 Supabase PostgreSQL
          ↓
生成指标报告与图表
          ↓
DeepSeek 运营分析
          ↓
飞书 Interactive Card 日报
```

## 重要：不会自动发送

项目已取消 GitHub Actions 定时任务，不会在每天固定时间自动调用 DeepSeek 或发送飞书消息。

只有当用户在本机终端主动运行以下命令时，才会执行完整流程并发送飞书日报：

```bash
cd "/Users/design/Documents/微信公众号数据分析/weixin-car-repo"
source .venv/bin/activate
python run_daily_report.py
```

同一数据日期已成功发送时，默认会根据 `sync_runs` 记录跳过重复发送。如需人工强制重发：

```bash
python run_daily_report.py --force
```

## 环境配置

项目根目录的 `.env` 需包含：

```dotenv
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
DEEPSEEK_API_KEY=...
DEEPSEEK_MODEL=deepseek-v4-flash
FEISHU_WEBHOOK_URL=...
FEISHU_APP_ID=...
FEISHU_APP_SECRET=...
```

`.env` 、微信登录状态、导出数据、日志、截图、报告 JSON 和图表均已被 Git 忽略，不应提交到仓库。

## 首次安装

需要 Python 3.11+：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## 分步运行

只采集微信后台 XLS：

```bash
python collect_wechat_data.py
python collect_wechat_data.py --date 2026-07-16
python collect_wechat_data.py --debug
```

首次运行会打开有界面 Chromium，用户负责扫码登录和安全验证。登录状态保存在本机 `wechat-browser-profile/`，不会上传。

只导入已下载的微信 XLS：

```bash
python import_wechat_data.py data/import/wechat_content_YYYY-MM-DD.xls
```

只生成指标报告：

```bash
python -m services.analysis_service --output report.json
```

只运行 DeepSeek 分析：

```bash
python -m services.ai_analyzer report.json
```

只生成图表并发送已有报告：

```bash
python -m services.feishu_sender --report report.json --analysis ai_analysis.json
```

## 数据存储与安全

生产数据唯一存储为 Supabase PostgreSQL。主要数据表包括：

- `wechat_accounts`
- `articles`
- `article_stats`
- `account_daily_stats`
- `article_channel_stats`
- `import_runs`
- `sync_runs`

数据库使用 RLS，Python 后台通过 `service_role` 访问。不要在代码、日志、Issue 或截图中暴露任何密钥。

## 飞书图片卡片

`services/report_visualizer.py` 会生成：

- `data/charts/views_trend.png`
- `data/charts/top_articles.png`

`services/feishu_image_uploader.py` 使用飞书应用凭证上传图片并获得 `image_key`。飞书应用需要开启机器人能力，并具有 `im:resource:upload` 权限。图片上传失败时，日报会降级为文字卡片，不会中断 Webhook 发送。

## 测试

```bash
python -m unittest discover -v
```

Supabase 真实权限测试默认跳过，只有显式设置 `RUN_SUPABASE_PERMISSION_TEST=1` 时才会运行。

## Git 自动推送

仓库包含 `.githooks/post-commit`。配置后，每次本地 commit 成功会自动 push：

```bash
git config core.hooksPath .githooks
```

它不会自动执行 `git add`，也不会自动运行或发送日报。
