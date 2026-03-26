#!/usr/bin/env bash
# Tests for build-deploy-package.sh

set -euo pipefail

SCRIPT_PATH="scripts/build-deploy-package.sh"

echo "=== 测试 build-deploy-package.sh ==="

# 测试 1: 脚本存在
echo -n "Test 1: 脚本存在... "
if [[ -f "$SCRIPT_PATH" ]]; then
    echo "PASS"
else
    echo "FAIL - 脚本不存在"
    exit 1
fi

# 测试 2: 脚本可执行
echo -n "Test 2: 脚本可执行... "
if [[ -x "$SCRIPT_PATH" ]]; then
    echo "PASS"
else
    echo "FAIL - 脚本不可执行"
    exit 1
fi

# 测试 3: 脚本语法有效
echo -n "Test 3: 语法检查... "
bash -n "$SCRIPT_PATH" && echo "PASS" || { echo "FAIL"; exit 1; }

# 测试 4: 有必需函数
echo -n "Test 4: 有 check_required_files 函数... "
grep -q "check_required_files" "$SCRIPT_PATH" && echo "PASS" || { echo "FAIL"; exit 1; }

echo -n "Test 5: 有 create_archive 函数... "
grep -q "create_archive" "$SCRIPT_PATH" && echo "PASS" || { echo "FAIL"; exit 1; }

# 测试 6: 排除 src/ tests/ docs/
echo -n "Test 6: 排除 src/ 从包中... "
if grep -q "src/" "$SCRIPT_PATH" && ! grep -q '"src/' "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL: src/ 可能被包含"
    exit 1
fi

echo ""
echo "=== 所有测试通过 ==="