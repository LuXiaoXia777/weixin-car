# AI 公众号数据分析机器人

每天读取最近 7 天公众号文章 CSV 数据，调用 DeepSeek 生成汽车内容运营分析，并通过飞书自定义机器人推送日报。

## 工作方式

1. GitHub Actions 每天北京时间 09:00 启动。
2. 程序读取 `data/articles.csv` 中截至最新日期的最近 7 天数据。
3. DeepSeek 分析标题吸引力、购买心理、内容趋势和次日选题。
4. 飞书自定义机器人将结果发送到指定群聊。

日报采用七段表格结构：今日概览、文章排行、内容类型、爆款拆解、兴趣变化、下周选题和三条运营建议。阅读、互动率、涨粉效率、环比和综合评分由程序计算；AI 只负责基于这些数据生成短句判断。

第一阶段的 CSV 不会自动更新。要得到新的日报，需要在仓库中追加或更新最新一天的数据。

## 1. 创建 GitHub 仓库

1. 登录 GitHub，点击右上角 `+`，选择 **New repository**。
2. 仓库名填写 `wechat-ai-assistant`。
3. 建议选择 **Private**，不要勾选自动创建 README。
4. 创建后，按照 GitHub 页面提示把本项目上传到仓库。

如果使用 GitHub Desktop：选择 **Add Existing Repository**，指向本项目文件夹；若提示它还不是仓库，选择创建仓库，然后点击 **Publish repository**。

## 2. 添加 GitHub Secrets

打开仓库，依次进入：

**Settings → Secrets and variables → Actions → New repository secret**

创建两个 Secret：

- `DEEPSEEK_API_KEY`：DeepSeek API 密钥。
- `FEISHU_WEBHOOK_URL`：飞书自定义机器人的完整 Webhook 地址。

不要把密钥写入代码、CSV、Issue 或 Actions 日志。

## 3. 配置飞书机器人

1. 打开接收日报的飞书群。
2. 进入 **群设置 → 群机器人 → 添加机器人 → 自定义机器人**。
3. 设置机器人名称，例如“车事人话数据助手”。
4. 安全设置可先选择“自定义关键词”，填写 `车事人话`。本项目卡片标题包含该关键词。
5. 复制 Webhook 地址，并保存到 GitHub Secret `FEISHU_WEBHOOK_URL`。

Webhook 相当于机器人密码，不要发送给其他人。

## 4. 本地测试

需要 Python 3.11+。在本项目目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export DEEPSEEK_API_KEY="你的 DeepSeek API 密钥"
python main.py --dry-run
```

`--dry-run` 会调用 DeepSeek 并在终端显示日报，但不会发送飞书消息。

只测试 DeepSeek API 连接和模拟数据分析：

```bash
python test_ai.py
```

成功时会输出 `DeepSeek API连接成功` 和一段 JSON 分析结果。

测试真实飞书推送：

```bash
export FEISHU_WEBHOOK_URL="你的飞书 Webhook"
python main.py
```

退出终端后，上述 `export` 设置会失效，不会写入项目文件。

## 5. 在 GitHub 手动测试

1. 打开仓库的 **Actions** 页面。
2. 左侧选择 **Daily WeChat AI Report**。
3. 点击 **Run workflow → Run workflow**。
4. 等待任务变为绿色对勾。
5. 检查飞书群是否收到“车事人话公众号日报”。

若任务显示红色叉号，点击该次运行，再点击 **Generate and send report** 查看错误日志。不要在日志或截图中暴露密钥。

## 6. 每日自动运行

工作流文件位于 `.github/workflows/daily_report.yml`，定时表达式为 `0 1 * * *`。GitHub 使用 UTC，因此对应北京时间每天 09:00。GitHub 的定时任务可能因平台繁忙延迟数分钟，不保证精确到秒。

定时工作流只会运行默认分支上的版本。请确保代码已经推送到默认分支，并在 Actions 页面启用了工作流。

## CSV 数据格式

编辑 `data/articles.csv`，字段为：

```text
date,title,category,views,likes,shares,comments,new_followers
```

日期格式必须是 `YYYY-MM-DD`，数值列只能填写整数。当前 MVP 以 CSV 中最新日期作为日报日期，并分析截至该日的最近 7 个自然日。

## 可选配置

模型通过 GitHub Repository Variable `DEEPSEEK_MODEL` 控制，当前默认使用 `deepseek-v4-flash`。进入 **Settings → Secrets and variables → Actions → Variables** 即可更换模型，无需修改代码。API 地址默认为 `https://api.deepseek.com`，也可通过 `DEEPSEEK_BASE_URL` 覆盖。

## 后续扩展位置

- 微信公众号 API：在 `services/data_loader.py` 增加新的数据源实现。
- 飞书多维表格与历史存储：新增独立 storage service。
- 周报/月报：在数据加载后增加报告周期参数。
- 自动选题库：保存 `suggestions` 到新的数据文件或外部存储。

## 本机提交后自动推送

仓库包含 `.githooks/post-commit`。在一台新电脑首次克隆仓库后，执行一次：

```bash
git config core.hooksPath .githooks
```

此后每次 `git commit` 成功都会自动推送当前分支。该功能不会自动执行 `git add`，提交前仍需确认暂存内容，避免误提交密钥或临时文件。
