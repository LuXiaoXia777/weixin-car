# 手机远程触发、Mac 本地执行配置

## 1. 运行方式

```text
iPhone 快捷指令（SSH） ──┐
                              ├─→ macOS launchd
每天 12:30 StartCalendarInterval ─┘       ↓
                         scripts/run_daily_report.sh
                                      ↓
                         run_daily_report.py
                                      ↓
                  微信 XLS → Supabase → DeepSeek → 飞书
```

GitHub Actions 不参与运行。Mac 必须已登录当前用户，Playwright 才能在 Aqua 图形会话中打开有界面浏览器。

## 2. 安装前检查

```bash
cd "/Users/design/Documents/微信公众号数据分析/weixin-car-repo"
source .venv/bin/activate
python --version
python -m playwright install chromium
test -f .env && echo ".env 存在"
```

`.env` 需包含 `SUPABASE_URL`、`SUPABASE_SERVICE_ROLE_KEY`、`DEEPSEEK_API_KEY`、`FEISHU_WEBHOOK_URL`、`FEISHU_APP_ID` 和 `FEISHU_APP_SECRET`。

## 3. macOS 一次性权限清单

### 必须开启

1. **远程登录（SSH）**
   - 系统设置 → 通用 → 共享 → 远程登录。
   - 只允许当前运行日报的 Mac 用户，不要选“所有用户”。
   - 用于 iPhone 快捷指令连入 Mac 并触发 LaunchAgent。

2. **文件与文件夹 / 完全磁盘访问**
   - 系统设置 → 隐私与安全性。
   - 对实际运行的 `.venv/bin/python`、`/bin/zsh` 以及 Playwright 的 `Google Chrome for Testing` 允许访问“文稿”目录。
   - 如 macOS 只允许添加 App，可为“终端”和 `Google Chrome for Testing.app` 开启完全磁盘访问，并在首次 LaunchAgent 运行时允许出现的“文稿文件夹”访问提示。

3. **允许后台项**
   - 系统设置 → 通用 → 登录项与扩展 → 允许在后台。
   - LaunchAgent 安装后，如出现与当前用户或 `zsh` 相关的后台项，保持开启。

4. **唤醒以供网络访问**
   - 系统设置 → 节能/电池/显示器高级设置中，开启“唤醒以供网络访问”。
   - Mac 完全关机时无法远程触发；定时运行时建议接通电源并保持用户登录。

### 通常不需要

- 不需要“辅助功能”：Playwright 通过浏览器自动化协议操作。
- 不需要“屏幕录制”。
- 不需要“自动化/Apple Events”。
- 不需要 Codex 或终端保持打开。

## 4. 先完成一次手动登录

安装 LaunchAgent 前，在 Mac 上主动运行一次采集器：

```bash
python collect_wechat_data.py
```

手动扫码和安全验证后，登录信息会保存在：

```text
/Users/design/Documents/微信公众号数据分析/weixin-car-repo/wechat-browser-profile/
```

该目录权限设为 `700` 且已被 Git 忽略。不要同时启动两个使用此 profile 的 Chromium。

## 5. 安装 LaunchAgent

```bash
cd "/Users/design/Documents/微信公众号数据分析/weixin-car-repo"
./scripts/install_launch_agent.sh
```

安装脚本会检查 plist，并安装到：

```text
~/Library/LaunchAgents/com.luxiaoxia.wechat-ai-daily-report.plist
```

`RunAtLoad=false`，因此安装不会立即发送日报。定时时间默认为每天 12:30，修改源 plist 的 `Hour`/`Minute` 后重新执行安装脚本即可更新。

验证已加载（不会执行日报）：

```bash
launchctl print "gui/$(id -u)/com.luxiaoxia.wechat-ai-daily-report"
```

## 6. Mac 手动触发

```bash
./scripts/trigger_daily_report.sh
```

查看日志：

```bash
tail -f logs/daily_report_$(date '+%Y%m%d').log
```

`scripts/run_daily_report.sh` 通过原子锁目录防止两次任务重叠运行。

## 7. iPhone 远程触发

1. iPhone 打开“快捷指令”，新建快捷指令。
2. 添加“通过 SSH 运行脚本”。
3. 主机填 Mac 的内网 IP 或可信 VPN 地址，用户填 Mac 用户名。
4. 建议使用专用 SSH 密钥，不要把 Mac 密码写入脚本文本。
5. 命令填：

```bash
/Users/design/Documents/微信公众号数据分析/weixin-car-repo/scripts/trigger_daily_report.sh
```

同一 Wi-Fi 下可直接使用 Mac 内网 IP。外网触发建议使用 Tailscale 等可信组网，**不要把 SSH 22 端口直接暴露到公网**。

## 8. 失败通知与排查

主流程非零退出时，wrapper 会调用 `scripts/send_failure_notification.py`，向现有 `FEISHU_WEBHOOK_URL` 发送红色告警卡片。通知包含 Mac 名称、退出码、时间和最近日志，不包含 `.env` 内容。

主日志：

```text
logs/daily_report_YYYYMMDD.log
logs/launchd.stdout.log
logs/launchd.stderr.log
```

常见失败：

- 浏览器登录失效：Mac 上会显示扫码页，5 分钟未处理则失败并通知飞书。
- Mac 未登录图形会话：LaunchAgent 不能打开 headful Chromium。
- “Operation not permitted”：检查“文稿”目录或完全磁盘访问权限。
- Mac 关机/断网：定时任务无法完成，恢复后可用手机快捷指令手动补发。
