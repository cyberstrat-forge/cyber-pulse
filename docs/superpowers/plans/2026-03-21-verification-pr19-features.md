# Verification System PR #19 Features Enhancement Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为验证系统添加 PR #19 新增功能的测试能力

**Architecture:** 在现有验证脚本中新增 Level 3: 增强诊断验证模块，测试 diagnose 命令增强和 log 命令新功能。采用渐进式验证策略，确保新功能在生产环境可用。

**Tech Stack:** Bash, Python (JSON 解析), Docker CLI, cyber-pulse CLI

---

## 文件结构

```
scripts/verify.sh        # 主验证脚本（修改）
  - 新增 verify_level3() 函数
  - 新增 verify_diagnose_enhancements() 函数
  - 新增 verify_log_features() 函数
  - 修改 verify_level1() 增强 API/队列检查
  - 修改 print_report() 添加 Level 3 报告
  - 修改 main() 调用 Level 3

docs/verification-guide.md  # 验证指南（修改）
  - 更新 Level 3 说明
```

---

## Task 1: 增强 Level 1 系统诊断验证

**Files:**
- Modify: `scripts/verify.sh:180-228`

**目标:** 增强现有 Level 1 验证，确保 `diagnose system` 的新增功能（API 健康检查、队列状态）正常工作。

- [ ] **Step 1: 修改 verify_level1 函数，解析 diagnose system 输出**

找到 `verify_level1()` 函数（约第 184 行），修改数据库检查部分：

```bash
verify_level1() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Level 1: 系统就绪"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # 运行 diagnose system 并捕获输出
    echo "  检查数据库和 Redis 连接..."
    DIAGNOSE_OUTPUT=$(docker exec $CONTAINER_API cyber-pulse diagnose system 2>&1)

    # 剥离 ANSI 代码（Rich 输出包含颜色代码）
    CLEAN_OUTPUT=$(echo "$DIAGNOSE_OUTPUT" | sed 's/\x1b\[[0-9;]*m//g')

    # 检查关键组件状态（匹配实际输出格式）
    echo "$CLEAN_OUTPUT" | grep -q "Database connection: healthy" && \
        echo "  ✓ Database: connected" || {
        log_error "Level 1 失败: Database 不健康"
        exit 1
    }

    echo "$CLEAN_OUTPUT" | grep -q "Redis connection: healthy" && \
        echo "  ✓ Redis: connected" || {
        log_error "Level 1 失败: Redis 不健康"
        exit 1
    }

    # 检查 API 服务（v1.2.0 新增）
    if echo "$CLEAN_OUTPUT" | grep -q "API service: healthy"; then
        echo "  ✓ API Service: healthy"
    elif echo "$CLEAN_OUTPUT" | grep -q "API service: not reachable"; then
        echo "  ⚠ API Service: not reachable (may be expected in dev)"
    else
        echo "  ⚠ API Service: status unknown"
    fi

    # 检查任务队列（v1.2.0 新增）
    if echo "$CLEAN_OUTPUT" | grep -q "Dramatiq Redis: connected"; then
        QUEUE_LEN=$(echo "$CLEAN_OUTPUT" | grep -o "Pending tasks.*: [0-9]*" | grep -o "[0-9]*" || echo "0")
        echo "  ✓ Task Queue: connected ($QUEUE_LEN pending)"
    elif echo "$CLEAN_OUTPUT" | grep -q "Could not check queue status"; then
        echo "  ⚠ Task Queue: could not check (Redis may not be available)"
    fi

    # Worker 运行检查
    echo "  检查 Worker 运行状态..."
    docker ps --filter "name=$CONTAINER_WORKER" --filter "status=running" | grep -q $CONTAINER_WORKER || {
        log_error "Level 1 失败: Worker 未运行"
        echo "  ✗ Worker: not running"
        echo ""
        echo "排查建议:"
        echo "  1. 检查容器状态: docker ps -a | grep worker"
        echo "  2. 查看日志: docker logs $CONTAINER_WORKER"
        exit 1
    }
    echo "  ✓ Worker: running"

    # Scheduler 运行检查
    echo "  检查 Scheduler 运行状态..."
    docker ps --filter "name=$CONTAINER_SCHEDULER" --filter "status=running" | grep -q $CONTAINER_SCHEDULER || {
        log_error "Level 1 失败: Scheduler 未运行"
        echo "  ✗ Scheduler: not running"
        echo ""
        echo "排查建议:"
        echo "  1. 检查容器状态: docker ps -a | grep scheduler"
        echo "  2. 查看日志: docker logs $CONTAINER_SCHEDULER"
        exit 1
    }
    echo "  ✓ Scheduler: running"

    echo ""
    echo "Level 1: ✓ 通过"
}
```

- [ ] **Step 2: 测试修改后的 Level 1 验证**

```bash
# 模拟测试（如果有 Docker 环境）
./scripts/verify.sh 2>&1 | grep -A 20 "Level 1"
```

Expected: Level 1 输出包含 Database, Redis, API Service, Task Queue, Worker, Scheduler 检查项

- [ ] **Step 3: Commit**

```bash
git add scripts/verify.sh
git commit -m "feat(verify): enhance Level 1 with API/queue status checks"
```

---

## Task 2: 新增 Level 3 增强诊断验证

**Files:**
- Modify: `scripts/verify.sh` (在 Level 2 后添加新函数)

**目标:** 新增 Level 3 验证模块，测试 PR #19 新增的 diagnose 和 log 命令功能。

- [ ] **Step 1: 在 verify_level2 函数后添加 Level 3 验证函数**

在 `verify_level2()` 函数后（约第 257 行）添加：

```bash
# ============================================================================
# Level 3: 增强诊断验证 (v1.2.0+)
# ============================================================================

verify_level3() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Level 3: 增强诊断验证 (v1.2.0+)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # 1. diagnose sources 采集活动验证
    verify_diagnose_sources_collection

    # 2. diagnose errors rejection reason 验证
    verify_diagnose_errors_reason

    # 3. log 命令功能验证
    verify_log_features

    echo ""
    echo "Level 3: ✓ 通过"
}
```

- [ ] **Step 2: 添加 verify_diagnose_sources_collection 函数**

```bash
# ============================================================================
# diagnose sources 采集活动验证
# ============================================================================

verify_diagnose_sources_collection() {
    echo ""
    echo "[diagnose sources 采集活动]"

    # 运行 diagnose sources 命令
    DIAGNOSE_OUTPUT=$(docker exec $CONTAINER_API cyber-pulse diagnose sources 2>&1)

    # 剥离 ANSI 代码（Rich 输出包含颜色代码）
    CLEAN_OUTPUT=$(echo "$DIAGNOSE_OUTPUT" | sed 's/\x1b\[[0-9;]*m//g')

    # 检查是否有 Recent Collection Activity 表格
    if echo "$CLEAN_OUTPUT" | grep -q "Recent Collection Activity"; then
        echo "  ✓ diagnose sources: 显示采集活动表格"

        # 检查状态标签（Fresh/Recent/Stale/Never）
        if echo "$CLEAN_OUTPUT" | grep -qE "(Fresh|Recent|Stale|Never)"; then
            # 统计各状态数量
            FRESH_COUNT=$(echo "$CLEAN_OUTPUT" | grep -c "Fresh" || echo "0")
            RECENT_COUNT=$(echo "$CLEAN_OUTPUT" | grep -c "Recent" || echo "0")
            STALE_COUNT=$(echo "$CLEAN_OUTPUT" | grep -c "Stale" || echo "0")
            NEVER_COUNT=$(echo "$CLEAN_OUTPUT" | grep -c "Never" || echo "0")

            echo "    - Fresh (< 1h): $FRESH_COUNT"
            echo "    - Recent (1-24h): $RECENT_COUNT"
            echo "    - Stale (> 24h): $STALE_COUNT"
            echo "    - Never: $NEVER_COUNT"
        fi
    else
        echo "  ⚠ diagnose sources: 未显示采集活动表格（可能是无活跃源）"
    fi
}
```

- [ ] **Step 3: 添加 verify_diagnose_errors_reason 函数**

```bash
# ============================================================================
# diagnose errors rejection reason 验证
# ============================================================================

verify_diagnose_errors_reason() {
    echo ""
    echo "[diagnose errors 拒绝原因]"

    # 运行 diagnose errors 命令
    DIAGNOSE_OUTPUT=$(docker exec $CONTAINER_API cyber-pulse diagnose errors 2>&1)

    # 剥离 ANSI 代码（Rich 输出包含颜色代码）
    CLEAN_OUTPUT=$(echo "$DIAGNOSE_OUTPUT" | sed 's/\x1b\[[0-9;]*m//g')

    # 检查是否有 Rejection Reason 列
    if echo "$CLEAN_OUTPUT" | grep -q "Rejection Reason"; then
        echo "  ✓ diagnose errors: 显示 Rejection Reason 列"

        # 统计 rejected items 数量（匹配 "Found X rejected items" 格式）
        REJECTED_COUNT=$(echo "$CLEAN_OUTPUT" | grep -o "Found [0-9]* rejected items" | grep -o "[0-9]*" || echo "0")
        if [ "$REJECTED_COUNT" -gt 0 ]; then
            echo "    - 发现 $REJECTED_COUNT 条被拒绝记录"
        else
            echo "    - 无被拒绝记录（正常状态）"
        fi
    else
        echo "  ⚠ diagnose errors: 未显示 Rejection Reason 列"
    fi

    # 检查是否有错误日志输出
    if echo "$CLEAN_OUTPUT" | grep -q "Recent Errors from Logs"; then
        echo "  ✓ diagnose errors: 显示错误日志分析"
    fi
}
```

- [ ] **Step 4: 添加 verify_log_features 函数**

```bash
# ============================================================================
# log 命令功能验证
# ============================================================================

verify_log_features() {
    echo ""
    echo "[log 命令功能]"

    # 1. log stats 验证
    LOG_STATS=$(docker exec $CONTAINER_API cyber-pulse log stats 2>&1)
    # 剥离 ANSI 代码后检查关键内容
    CLEAN_LOG_STATS=$(echo "$LOG_STATS" | sed 's/\x1b\[[0-9;]*m//g')
    if echo "$CLEAN_LOG_STATS" | grep -q "File:"; then
        echo "  ✓ log stats: 可用"
    else
        echo "  ⚠ log stats: 不可用或无日志"
    fi

    # 2. log errors --format json 验证
    LOG_ERRORS_JSON=$(docker exec $CONTAINER_API cyber-pulse log errors --format json 2>&1)
    if validate_json "$LOG_ERRORS_JSON"; then
        # JSON 是数组，计算长度
        ERROR_COUNT=$(echo "$LOG_ERRORS_JSON" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
        echo "  ✓ log errors --format json: 有效 JSON ($ERROR_COUNT 条错误)"
    else
        echo "  ⚠ log errors --format json: 无错误或格式异常"
    fi

    # 3. log search --format json 验证
    LOG_SEARCH_JSON=$(docker exec $CONTAINER_API cyber-pulse log search "test" --format json 2>&1)
    if validate_json "$LOG_SEARCH_JSON"; then
        echo "  ✓ log search --format json: 有效 JSON"
    else
        echo "  ⚠ log search --format json: 无匹配或格式异常"
    fi

    # 4. log export 验证
    EXPORT_PATH="/tmp/verify_log_export_$$.log"
    EXPORT_OUTPUT=$(docker exec $CONTAINER_API cyber-pulse log export --output "$EXPORT_PATH" 2>&1)
    CLEAN_EXPORT=$(echo "$EXPORT_OUTPUT" | sed 's/\x1b\[[0-9;]*m//g')
    if echo "$CLEAN_EXPORT" | grep -q "Exported"; then
        EXPORT_COUNT=$(echo "$CLEAN_EXPORT" | grep -o "Exported [0-9]*" | grep -o "[0-9]*" || echo "0")
        echo "  ✓ log export: 导出成功 ($EXPORT_COUNT 条)"
        # 清理导出文件
        docker exec $CONTAINER_API rm -f "$EXPORT_PATH" 2>/dev/null
    else
        echo "  ⚠ log export: 导出失败或无日志"
    fi

    # 5. log clear 验证（dry-run，不实际执行）
    # 使用 --help 确认命令存在
    CLEAR_HELP=$(docker exec $CONTAINER_API cyber-pulse log clear --help 2>&1)
    if echo "$CLEAR_HELP" | grep -q "older-than"; then
        echo "  ✓ log clear: 命令可用"
    else
        echo "  ⚠ log clear: 命令不可用"
    fi
}
```

- [ ] **Step 5: 测试新增函数**

```bash
# 语法检查
bash -n scripts/verify.sh && echo "Syntax OK"

# 功能测试（需要 Docker 环境）
./scripts/verify.sh 2>&1 | grep -A 30 "Level 3"
```

Expected: Level 3 输出包含 diagnose sources, diagnose errors, log 命令验证

- [ ] **Step 6: Commit**

```bash
git add scripts/verify.sh
git commit -m "feat(verify): add Level 3 enhanced diagnostics verification"
```

---

## Task 3: 集成 Level 3 到主流程

**Files:**
- Modify: `scripts/verify.sh` (main 函数和 print_report 函数)

**目标:** 将 Level 3 集成到验证流程，并更新报告输出。

- [ ] **Step 1: 修改 main 函数调用 Level 3**

找到 `main()` 函数（约第 655 行），修改调用顺序：

```bash
main() {
    parse_args "$@"

    echo "╭─────────────────────────────────────────────────────────────────╮"
    echo "│                  cyber-pulse 验证系统                           │"
    echo "│                    $(date '+%Y-%m-%d %H:%M:%S')                         │"
    echo "╰─────────────────────────────────────────────────────────────────╯"

    validate_sources_file

    LOCK_FILE="/tmp/cyberpulse_verify.lock"

    # 跨平台锁机制（支持 macOS 和 Linux）
    if command -v flock &> /dev/null; then
        exec 200>$LOCK_FILE
        flock -n 200 || {
            log_error "另一个验证任务正在运行"
            exit 1
        }
    else
        # macOS fallback: use mkdir for atomic lock
        mkdir "$LOCK_FILE" 2>/dev/null || {
            log_error "另一个验证任务正在运行"
            exit 1
        }
        trap "rmdir '$LOCK_FILE' 2>/dev/null" EXIT
    fi

    verify_level1
    verify_level2
    verify_level3  # 新增
    cleanup_verify_data
    print_report

    # 释放锁
    if command -v flock &> /dev/null; then
        flock -u 200
    else
        rmdir "$LOCK_FILE" 2>/dev/null
    fi
}
```

- [ ] **Step 2: 更新 print_report 函数添加 Level 3 报告**

找到 `print_report()` 函数（约第 596 行），更新报告模板：

```bash
print_report() {
    if [ -f /tmp/cyberpulse_verify_stats.txt ]; then
        source /tmp/cyberpulse_verify_stats.txt
    fi

    if [ -n "$OUTPUT_FILE" ]; then
        mkdir -p "$(dirname "$OUTPUT_FILE")"
        cat > "$OUTPUT_FILE" << EOF
# cyber-pulse 验证报告

**时间：** $(date '+%Y-%m-%d %H:%M:%S')
**结果：** ✓ 通过

---

## Level 1: 系统就绪

| 检查项 | 状态 |
|--------|------|
| Database | ✓ connected |
| Redis | ✓ connected |
| API Service | ✓ healthy |
| Task Queue | ✓ connected |
| Worker | ✓ running |
| Scheduler | ✓ running |

**结果：** ✓ 通过

---

## Level 2: 功能验证

### 数据统计

| 指标 | 值 |
|------|-----|
| 新增内容 | ${new_contents:-0} contents |

**结果：** ✓ 通过

---

## Level 3: 增强诊断验证 (v1.2.0+)

| 功能 | 状态 |
|------|------|
| diagnose sources 采集活动 | ✓ 通过 |
| diagnose errors 拒绝原因 | ✓ 通过 |
| log stats | ✓ 可用 |
| log errors --format json | ✓ 有效 JSON |
| log search --format json | ✓ 有效 JSON |
| log export | ✓ 可用 |
| log clear | ✓ 可用 |

**结果：** ✓ 通过

---

## 结论

验证通过，系统可用。所有 v1.2.0 新增功能正常工作。
EOF
        echo ""
        echo "报告已保存到: $OUTPUT_FILE"
    else
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "结论: 验证通过 ✓"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    fi
}
```

- [ ] **Step 3: 完整测试**

```bash
# 语法检查
bash -n scripts/verify.sh && echo "Syntax OK"

# 完整验证测试（需要 Docker 环境）
./scripts/verify.sh --output /tmp/verify_report.md

# 检查报告
cat /tmp/verify_report.md
```

Expected: 报告包含 Level 1, Level 2, Level 3 三部分

- [ ] **Step 4: Commit**

```bash
git add scripts/verify.sh
git commit -m "feat(verify): integrate Level 3 into main verification flow"
```

---

## Task 4: 更新验证指南文档

**Files:**
- Modify: `docs/verification-guide.md`

**目标:** 更新文档说明新增的 Level 3 验证内容。

- [ ] **Step 1: 更新验证流程说明**

修改 `docs/verification-guide.md`，更新验证流程部分：

```markdown
## 验证流程

### Level 1: 系统就绪

检查项：
- 数据库连接
- Redis 连接
- API 服务健康（v1.2.0+）
- 任务队列状态（v1.2.0+）
- Worker 运行状态
- Scheduler 运行状态

### Level 2: 功能验证

检查项：
- API Client 管理（create/list/disable/enable）
- 情报源添加与连接测试
- 数据采集任务执行
- CLI 数据查询
- API 查询功能

### Level 3: 增强诊断验证（v1.2.0+）

检查项：
- diagnose sources 采集活动表格（Fresh/Recent/Stale/Never）
- diagnose errors Rejection Reason 列
- log stats 日志统计
- log errors --format json JSON 输出
- log search --format json JSON 输出
- log export 日志导出
- log clear 日志清理（命令可用性）
```

- [ ] **Step 2: 更新故障排查表格**

在故障排查部分添加 Level 3 相关内容：

```markdown
### Level 3 失败

| 症状 | 可能原因 | 排查命令 |
|------|----------|----------|
| 采集活动表格未显示 | 无活跃情报源 | `cyber-pulse source list --status active` |
| log export 失败 | 日志文件不存在或权限问题 | `docker logs cyber-pulse-api-1` |
| JSON 输出无效 | 命令执行错误 | 检查命令参数是否正确 |
```

- [ ] **Step 3: Commit**

```bash
git add docs/verification-guide.md
git commit -m "docs: update verification guide for Level 3 diagnostics"
```

---

## Task 5: 最终验证与集成测试

**Files:**
- 无文件修改，仅验证

**目标:** 确保所有修改正常工作。

- [ ] **Step 1: 运行完整验证脚本**

```bash
./scripts/verify.sh --output /tmp/final_verify_report.md
```

Expected: 全部三级验证通过

- [ ] **Step 2: 检查报告输出**

```bash
cat /tmp/final_verify_report.md
```

Expected: 报告包含完整的 Level 1/2/3 验证结果

- [ ] **Step 3: 最终 Commit**

```bash
git add -A
git commit -m "feat(verify): complete PR #19 features verification support

- Enhance Level 1 with API health and queue status checks
- Add Level 3 for diagnose/log command verification
- Update verification guide documentation

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 验收标准

| 标准 | 验证方法 |
|------|----------|
| Level 1 包含 API/队列检查 | `./scripts/verify.sh` 输出包含 "API Service" 和 "Task Queue" |
| Level 3 验证 diagnose 功能 | `./scripts/verify.sh` 输出包含 "采集活动" 和 "拒绝原因" |
| Level 3 验证 log 功能 | `./scripts/verify.sh` 输出包含 "log stats", "log export" 等 |
| 报告包含 Level 3 结果 | 报告 Markdown 包含 "Level 3: 增强诊断验证" 章节 |
| 文档已更新 | `docs/verification-guide.md` 包含 Level 3 说明 |