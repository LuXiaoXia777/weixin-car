#!/bin/zsh

# 供 Mac 终端或 iPhone 快捷指令的“通过 SSH 运行脚本”调用。
set -eu

readonly LABEL="com.luxiaoxia.wechat-ai-daily-report"
readonly USER_ID="$(id -u)"

/bin/launchctl kickstart -k "gui/${USER_ID}/${LABEL}"
echo "已触发 ${LABEL}"
