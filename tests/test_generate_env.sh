#!/usr/bin/env bash
#
# tests/test_generate_env.sh - 测试 generate-env.sh 修改
#
# 验证 ADMIN_API_KEY 相关代码已被移除

set -euo pipefail

SCRIPT_PATH="deploy/init/generate-env.sh"

echo "=== 测试 generate-env.sh ==="

# 测试 1: 脚本语法有效
echo -n "Test 1: 脚本语法检查... "
if bash -n "$SCRIPT_PATH" 2>/dev/null; then
    echo "PASS"
else
    echo "FAIL"
    exit 1
fi

# 测试 2: 不应包含 ADMIN_API_KEY 输出
echo -n "Test 2: 无 ADMIN_API_KEY 在 .env 模板中... "
if grep -q "^ADMIN_API_KEY=" "$SCRIPT_PATH"; then
    echo "FAIL - 发现 ADMIN_API_KEY 在模板中"
    exit 1
else
    echo "PASS"
fi

# 测试 3: 不应包含 generate_admin_api_key 函数
echo -n "Test 3: 无 generate_admin_api_key 函数... "
if grep -q "generate_admin_api_key()" "$SCRIPT_PATH"; then
    echo "FAIL - 发现 generate_admin_api_key 函数"
    exit 1
else
    echo "PASS"
fi

# 测试 4: 不应包含 admin_api_key 变量赋值
echo -n "Test 4: 无 admin_api_key 变量... "
if grep -q "admin_api_key=\$" "$SCRIPT_PATH"; then
    echo "FAIL - 发现 admin_api_key 变量赋值"
    exit 1
else
    echo "PASS"
fi

# 测试 5: 不应包含 Admin API Key 在输出摘要中
echo -n "Test 5: 无 Admin API Key 在输出摘要... "
if grep -q "Admin API Key:" "$SCRIPT_PATH"; then
    echo "FAIL - 发现 Admin API Key 在输出摘要"
    exit 1
else
    echo "PASS"
fi

echo ""
echo "=== 所有测试通过 ==="