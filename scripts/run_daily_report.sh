#!/bin/zsh

# launchd 与本机手动触发共用的稳定入口。
set -u
set -o pipefail

readonly PROJECT_DIR="/Users/design/Documents/微信公众号数据分析/weixin-car-repo"
readonly PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"
readonly LOG_DIR="${PROJECT_DIR}/logs"
readonly RUNTIME_DIR="${PROJECT_DIR}/runtime"
readonly LOCK_DIR="${RUNTIME_DIR}/daily-report.lock"
readonly LOG_FILE="${LOG_DIR}/daily_report_$(date '+%Y%m%d').log"

mkdir -p "${LOG_DIR}" "${RUNTIME_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] [launchd] 日报任务启动"

if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [launchd] 已有日报任务在运行，本次跳过"
  exit 0
fi

cleanup() {
  rmdir "${LOCK_DIR}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [launchd] 找不到虚拟环境 Python：${PYTHON_BIN}"
  exit_code=127
else
  cd "${PROJECT_DIR}" || exit 1
  source "${PROJECT_DIR}/.venv/bin/activate"
  export PYTHONUNBUFFERED=1
  export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

  # 任务运行期间防止 Mac 因空闲进入睡眠。
  /usr/bin/caffeinate -dims "${PYTHON_BIN}" "${PROJECT_DIR}/run_daily_report.py" "$@"
  exit_code=$?
fi

if (( exit_code != 0 )); then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [launchd] 日报任务失败，exit_code=${exit_code}"
  if [[ -x "${PYTHON_BIN}" ]]; then
    "${PYTHON_BIN}" "${PROJECT_DIR}/scripts/send_failure_notification.py" \
      --exit-code "${exit_code}" \
      --log-file "${LOG_FILE}" || \
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] [launchd] 飞书失败通知发送失败"
  fi
  exit "${exit_code}"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] [launchd] 日报任务完成"
