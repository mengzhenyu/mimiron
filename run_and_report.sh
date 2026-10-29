#!/bin/bash
# ============================================================
# 观星系统 E2E 测试 - 一键运行 + 自动刷新 Allure 报告
# 用法:
#   bash run_and_report.sh                              # 跑全部测试
#   bash run_and_report.sh tests/test_banzushezhi.py    # 指定单个测试文件
#   bash run_and_report.sh tests/ZhiBanGL/              # 指定测试目录
#   bash run_and_report.sh -k "create"                  # pytest 参数透传
# ============================================================

cd "$(dirname "$0")" || exit 1

export HEADLESS="${HEADLESS:-false}"

# 测试目标: 命令行传入, 或默认跑全部
TEST_TARGET="${*:-tests/}"

echo "========================================"
echo "运行测试目标: $TEST_TARGET"
echo "HEADLESS=$HEADLESS"
echo "========================================"

# ===== 1. 运行测试 =====
venv/bin/python -m pytest $TEST_TARGET -v \
    --alluredir=./allure-results \
    --clean-alluredir

TEST_EXIT_CODE=$?
if [ $TEST_EXIT_CODE -ne 0 ]; then
    echo "========================================"
    echo "⚠️  测试存在失败用例 (exit code: $TEST_EXIT_CODE)"
    echo "========================================"
fi

# ===== 2. 重启 Allure 报告服务 =====
# 调用 scripts/restart_allure.sh, 让 launchctl 重新加载最新 allure-results
echo ""
echo "========================================"
echo "刷新 Allure 报告..."
echo "========================================"
bash scripts/restart_allure.sh

exit $TEST_EXIT_CODE
