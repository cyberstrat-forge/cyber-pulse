#!/usr/bin/env bash
# Tests for api.sh script

set -euo pipefail

SCRIPT_PATH="scripts/api.sh"

echo "=== 测试 api.sh ==="

# 测试 1: 脚本存在
echo -n "Test 1: 脚本存在... "
if [[ -f "$SCRIPT_PATH" ]]; then
    echo "PASS"
else
    echo "FAIL - 脚本不存在"
    exit 1
fi

# 测试 2: 脚本语法有效
echo -n "Test 2: 语法检查... "
bash -n "$SCRIPT_PATH" && echo "PASS" || { echo "FAIL"; exit 1; }

# 测试 3: 有 configure 命令
echo -n "Test 3: 有 configure 命令... "
if grep -q "cmd_configure" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL - 未找到 configure 命令"
    exit 1
fi

# 测试 4: 有 sources 命令
echo -n "Test 4: 有 sources 命令... "
if grep -q "cmd_sources_list\|cmd_sources_get\|cmd_sources_create" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL - 未找到 sources 命令"
    exit 1
fi

# 测试 5: 有 jobs 命令
echo -n "Test 5: 有 jobs 命令... "
if grep -q "cmd_jobs_list\|cmd_jobs_run" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL - 未找到 jobs 命令"
    exit 1
fi

# 测试 6: 有 clients 命令
echo -n "Test 6: 有 clients 命令... "
if grep -q "cmd_clients_list\|cmd_clients_create" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL - 未找到 clients 命令"
    exit 1
fi

# 测试 7: 有 diagnose 命令
echo -n "Test 7: 有 diagnose 命令... "
if grep -q "cmd_diagnose" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL - 未找到 diagnose 命令"
    exit 1
fi

# 测试 8: help 命令工作
echo -n "Test 8: help 命令工作... "
set +e
output=$(bash "$SCRIPT_PATH" help 2>&1)
if echo "$output" | grep -q "configure"; then
    echo "PASS"
else
    echo "FAIL - help 命令不工作"
    exit 1
fi
set -e

# 测试 9: 有 sources test 命令
echo -n "Test 9: 有 sources test 命令... "
if grep -q "cmd_sources_test" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL - 未找到 sources test 命令"
    exit 1
fi

# 测试 10: 有 sources schedule 命令
echo -n "Test 10: 有 sources schedule 命令... "
if grep -q "cmd_sources_schedule\|cmd_sources_unschedule" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL - 未找到 sources schedule 命令"
    exit 1
fi

# 测试 11: 有 sources import/export 命令
echo -n "Test 11: 有 sources import/export 命令... "
if grep -q "cmd_sources_import\|cmd_sources_export" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL - 未找到 sources import/export 命令"
    exit 1
fi

# 测试 12: 有 sources defaults 命令
echo -n "Test 12: 有 sources defaults 命令... "
if grep -q "cmd_sources_defaults\|cmd_sources_set_defaults" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL - 未找到 sources defaults 命令"
    exit 1
fi

echo ""
echo "=== 所有测试通过 ==="