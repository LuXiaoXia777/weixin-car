#!/bin/zsh

# 只安装/更新 LaunchAgent，RunAtLoad=false，安装时不会执行真实日报。
set -eu

readonly LABEL="com.luxiaoxia.wechat-ai-daily-report"
readonly PROJECT_DIR="/Users/design/Documents/微信公众号数据分析/weixin-car-repo"
readonly SOURCE_PLIST="${PROJECT_DIR}/launchd/${LABEL}.plist"
readonly TARGET_DIR="${HOME}/Library/LaunchAgents"
readonly TARGET_PLIST="${TARGET_DIR}/${LABEL}.plist"
readonly DOMAIN="gui/$(id -u)"

/usr/bin/plutil -lint "${SOURCE_PLIST}"
mkdir -p "${TARGET_DIR}" "${PROJECT_DIR}/logs" "${PROJECT_DIR}/runtime"

/bin/launchctl bootout "${DOMAIN}" "${TARGET_PLIST}" 2>/dev/null || true
/bin/cp "${SOURCE_PLIST}" "${TARGET_PLIST}"
/bin/chmod 600 "${TARGET_PLIST}"
/bin/launchctl bootstrap "${DOMAIN}" "${TARGET_PLIST}"
/bin/launchctl enable "${DOMAIN}/${LABEL}"

echo "LaunchAgent 已安装，安装过程未执行日报。"
echo "手动触发：${PROJECT_DIR}/scripts/trigger_daily_report.sh"
