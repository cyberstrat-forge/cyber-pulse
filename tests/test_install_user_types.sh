#!/usr/bin/env bash
# Tests for install.sh user type separation

set -euo pipefail

SCRIPT_PATH="install.sh"

echo "=== 测试 install.sh 用户类型 ==="

# 测试 1: 脚本语法有效
echo -n "Test 1: 语法检查... "
bash -n "$SCRIPT_PATH" && echo "PASS" || { echo "FAIL"; exit 1; }

# 测试 2: 有 --type 选项
echo -n "Test 2: 有 --type 选项... "
if grep -q "\-\-type\|USER_TYPE" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL - 未找到 --type 选项"
    exit 1
fi

# 测试 3: 有 developer 模式
echo -n "Test 3: 有 developer 模式... "
if grep -q "developer" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL - 未找到 developer 模式"
    exit 1
fi

# 测试 4: 有 ops 模式
echo -n "Test 4: 有 ops 模式... "
if grep -q "ops" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL - 未找到 ops 模式"
    exit 1
fi

# 测试 5: 有 install_ops_package 函数
echo -n "Test 5: 有 install_ops_package 函数... "
if grep -q "install_ops_package" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL - 未找到 install_ops_package 函数"
    exit 1
fi

echo ""
echo "=== 所有测试通过 ==="