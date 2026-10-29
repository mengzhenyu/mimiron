#!/bin/bash
# ============================================================
# Allure 报告服务 - 重启脚本
# 用途: 测试跑完后调用此脚本, 让 launchctl 重新加载 allure-results 并刷新报告
# 用法: bash scripts/restart_allure.sh
# ============================================================

cd "$(dirname "$0")/.." || exit 1

PLIST_LABEL="com.mimiron.allure"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
PORT="59884"
RESULTS_DIR="$(pwd)/allure-results"
REPORT_URL="http://127.0.0.1:${PORT}"

# -------- 1. 确保 plist 存在 --------
if [ ! -f "$PLIST_PATH" ]; then
    echo "[restart_allure] plist 不存在, 重新创建: $PLIST_PATH"
    cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>cd /tmp && exec /Users/admin/.local/bin/allure serve ${RESULTS_DIR} --port ${PORT}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/allure-mimiron.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/allure-mimiron.err</string>
</dict>
</plist>
EOF
fi

# -------- 2. 先卸载旧服务 --------
echo "[restart_allure] 卸载旧服务..."
launchctl unload "$PLIST_PATH" 2>/dev/null
# 保险起见, kill 残留进程
pkill -f "allure.*${PORT}" 2>/dev/null
sleep 1

# -------- 3. 加载新服务 --------
echo "[restart_allure] 加载新服务, 等待启动..."
launchctl load "$PLIST_PATH" 2>/dev/null

# -------- 4. 等待端口就绪 --------
READY=false
for i in $(seq 1 15); do
    if curl -s -o /dev/null -w "%{http_code}" "${REPORT_URL}/" 2>/dev/null | grep -qE "^(200|302)$"; then
        READY=true
        break
    fi
    sleep 1
done

if $READY; then
    echo "[restart_allure] ✅ 服务已就绪: ${REPORT_URL}"
    echo "[restart_allure]   launchctl list:"
    launchctl list | grep mimiron
    # 注意: allure serve 启动后会自动打开浏览器, 此处不再重复 open, 否则会出现两个标签页
else
    echo "[restart_allure] ❌ 服务启动超时, 日志:"
    tail -10 /tmp/allure-mimiron.log 2>/dev/null
    tail -5 /tmp/allure-mimiron.err 2>/dev/null
    exit 1
fi
