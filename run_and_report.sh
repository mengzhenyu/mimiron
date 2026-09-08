#!/bin/bash
# ============================================================
# 观星系统 E2E 测试 - 一键运行 + 打开报告
# 用法: bash run_and_report.sh
# ============================================================

# 切换到脚本所在目录
cd "$(dirname "$0")" || exit 1

# ===== 环境变量 (运行前按需修改) =====
export LOGIN_PASSWORD='}zV:&L) ".sT'
export HEADLESS=false

# ===== 1. 运行测试 =====
echo "========================================"
echo "开始运行 test_gongzuotai.py 测试..."
echo "========================================"
venv/bin/python -m pytest tests/test_gongzuotai.py -v --alluredir=./allure-results --clean-alluredir

# 检查测试是否成功 (0=成功)
TEST_EXIT_CODE=$?
if [ $TEST_EXIT_CODE -ne 0 ]; then
    echo "========================================"
    echo "测试存在失败用例 (exit code: $TEST_EXIT_CODE)"
    echo "========================================"
fi

# ===== 2. 释放可能被占用的报告端口 =====
lsof -ti :59882 | xargs kill -9 2>/dev/null

# ===== 3. 启动 Allure 报告 =====
echo "========================================"
echo "启动 Allure 报告: http://127.0.0.1:59882"
echo "按 Ctrl+C 退出报告服务"
echo "========================================"
allure serve ./allure-results --port 59882
