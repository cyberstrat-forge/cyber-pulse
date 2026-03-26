#!/usr/bin/env bash
# Tests for cyber-pulse.sh admin reset command

set -euo pipefail

SCRIPT_PATH="scripts/cyber-pulse.sh"

echo "=== 测试 cyber-pulse.sh admin 命令 ==="

# 测试 1: 脚本语法有效
echo -n "Test 1: 语法检查... "
bash -n "$SCRIPT_PATH" && echo "PASS" || { echo "FAIL"; exit 1; }

# 测试 2: 不应包含 show-key 命令
echo -n "Test 2: 无 show-key 命令... "
if grep -q "show-key\|show_key" "$SCRIPT_PATH"; then
    echo "FAIL - 发现 show-key 命令"
    exit 1
else
    echo "PASS"
fi

# 测试 3: 不应包含 rotate-key 命令
echo -n "Test 3: 无 rotate-key 命令... "
if grep -q "rotate-key\|rotate_key" "$SCRIPT_PATH"; then
    echo "FAIL - 发现 rotate-key 命令"
    exit 1
else
    echo "PASS"
fi

# 测试 4: 应包含 reset 命令
echo -n "Test 4: 有 reset 命令... "
if grep -q "cmd_admin_reset\|admin reset" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL - 未找到 reset 命令"
    exit 1
fi

echo ""
echo "=== 所有测试通过 ==="