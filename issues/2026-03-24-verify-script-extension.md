# Issue: 扩展 verify.sh 增加数据质量和深度测试

## 问题概述

**发现日期**: 2026-03-24
**严重程度**: P2（提升测试覆盖度）
**影响范围**: 测试验证流程

## 背景

当前 `verify.sh` 提供三层验证：
- Level 1: 系统就绪（数据库、Redis、API、Worker、Scheduler）
- Level 2: 功能验证（Client、Source、采集、查询）
- Level 3: 增强诊断（diagnose、log 命令）

经过实际测试发现，还有重要的测试场景未覆盖：
- RSS 源可访问性检查
- 内容质量分析
- API 边界测试
- 深度错误处理

---

## 现有验证 vs 缺失测试

### 已覆盖

| 测试项 | verify.sh | 说明 |
|--------|-----------|------|
| 系统组件状态 | ✅ Level 1 | DB、Redis、API、Worker、Scheduler |
| API Client CRUD | ✅ Level 2 | create、list、disable、enable |
| 情报源添加 | ✅ Level 2 | 通过 sources.yaml |
| 数据采集 | ✅ Level 2 | job run + 等待完成 |
| CLI 查询 | ✅ Level 2 | content stats、list |
| API 查询 | ✅ Level 2 | contents 端点 + 游标 |
| diagnose sources | ✅ Level 3 | 采集活动统计 |
| diagnose errors | ✅ Level 3 | 拒绝原因 |
| log 命令 | ✅ Level 3 | stats、errors、search、export |

### 缺失测试

| 测试项 | 重要性 | 说明 |
|--------|--------|------|
| RSS 源可访问性 | 高 | HTTP 状态码检查，发现无法访问的源 |
| 内容质量分析 | 高 | 标题=正文、正文过短等质量问题 |
| 源健康状态 | 高 | 从未采集、采集失败的源 |
| API limit 边界 | 中 | limit=0、limit<0、limit>100 |
| API 游标验证 | 中 | 无效游标、不存在的游标 |
| API 错误处理 | 中 | 401、404、422 等错误码 |
| OPML 导入 | 中 | 批量导入测试 |
| TUI 功能 | 低 | 交互功能验证（需人工） |

---

## 建议扩展方案

### 新增 Level 4: 数据质量验证

```bash
verify_level4() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Level 4: 数据质量验证"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    verify_content_quality
    verify_source_health
    verify_source_accessibility_sample

    echo ""
    echo "Level 4: ✓ 通过"
}
```

#### 4.1 内容质量验证 `verify_content_quality()`

**目的**: 检测内容质量问题（标题=正文、正文过短等）

**实现方案**:

```bash
verify_content_quality() {
    echo ""
    echo "[内容质量分析]"

    # 使用数据库查询分析内容质量
    QUALITY_RESULT=$(docker exec $CONTAINER_POSTGRES psql -U cyberpulse -d cyberpulse -t -A -c "
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN normalized_title = normalized_body THEN 1 ELSE 0 END) as title_eq_body,
            SUM(CASE WHEN LENGTH(normalized_body) < 100 THEN 1 ELSE 0 END) as short_body,
            SUM(CASE WHEN content_completeness >= 1.0 THEN 1 ELSE 0 END) as complete,
            SUM(CASE WHEN content_completeness < 0.5 THEN 1 ELSE 0 END) as low_quality
        FROM contents
    " 2>/dev/null)

    TOTAL=$(echo "$QUALITY_RESULT" | cut -d'|' -f1)
    TITLE_EQ_BODY=$(echo "$QUALITY_RESULT" | cut -d'|' -f2)
    SHORT_BODY=$(echo "$QUALITY_RESULT" | cut -d'|' -f3)
    COMPLETE=$(echo "$QUALITY_RESULT" | cut -d'|' -f4)
    LOW_QUALITY=$(echo "$QUALITY_RESULT" | cut -d'|' -f5)

    echo "  总内容数: $TOTAL"
    echo "  完整内容: $COMPLETE ($(echo "scale=1; $COMPLETE * 100 / $TOTAL" | bc)%)"
    echo "  标题=正文: $TITLE_EQ_BODY"
    echo "  正文过短(<100字): $SHORT_BODY"
    echo "  低质量(<0.5): $LOW_QUALITY"

    # 质量阈值检查
    if [ "$TITLE_EQ_BODY" -gt 0 ]; then
        echo "  ⚠ 发现 $TITLE_EQ_BODY 条标题=正文问题"
    fi

    if [ "$TOTAL" -gt 0 ]; then
        QUALITY_RATE=$(echo "scale=1; $COMPLETE * 100 / $TOTAL" | bc)
        if [ $(echo "$QUALITY_RATE < 50" | bc) -eq 1 ]; then
            echo "  ⚠ 内容质量率低于 50%"
        fi
    fi
}
```

**输出示例**:
```
[内容质量分析]
  总内容数: 1582
  完整内容: 313 (19.8%)
  标题=正文: 18
  正文过短(<100字): 45
  低质量(<0.5): 20
  ⚠ 发现 18 条标题=正文问题
```

#### 4.2 源健康状态验证 `verify_source_health()`

**目的**: 检查源的采集状态，发现从未采集或采集失败的源

**实现方案**:

```bash
verify_source_health() {
    echo ""
    echo "[源健康状态]"

    # 统计源状态
    HEALTH_RESULT=$(docker exec $CONTAINER_POSTGRES psql -U cyberpulse -d cyberpulse -t -A -c "
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN last_fetched_at IS NULL THEN 1 ELSE 0 END) as never_fetched,
            SUM(CASE WHEN last_fetched_at < NOW() - INTERVAL '24 hours' THEN 1 ELSE 0 END) as stale,
            SUM(CASE WHEN status = 'ACTIVE' THEN 1 ELSE 0 END) as active
        FROM sources
        WHERE status != 'REMOVED'
    " 2>/dev/null)

    TOTAL=$(echo "$HEALTH_RESULT" | cut -d'|' -f1)
    NEVER_FETCHED=$(echo "$HEALTH_RESULT" | cut -d'|' -f2)
    STALE=$(echo "$HEALTH_RESULT" | cut -d'|' -f3)
    ACTIVE=$(echo "$HEALTH_RESULT" | cut -d'|' -f4)

    echo "  总源数: $TOTAL"
    echo "  活跃源: $ACTIVE"
    echo "  从未采集: $NEVER_FETCHED"
    echo "  超过24h未采集: $STALE"

    if [ "$NEVER_FETCHED" -gt 10 ]; then
        echo "  ⚠ 发现 $NEVER_FETCHED 个源从未采集"
    fi
}
```

**输出示例**:
```
[源健康状态]
  总源数: 146
  活跃源: 146
  从未采集: 57
  超过24h未采集: 0
  ⚠ 发现 57 个源从未采集
```

#### 4.3 RSS 源可访问性抽样验证 `verify_source_accessibility_sample()`

**目的**: 抽样检查 RSS 源的 HTTP 可访问性

**实现方案**:

```bash
verify_source_accessibility_sample() {
    echo ""
    echo "[RSS 源可访问性抽样]"

    # 获取前 10 个 RSS 源的 feed_url
    FEED_URLS=$(docker exec $CONTAINER_POSTGRES psql -U cyberpulse -d cyberpulse -t -A -c "
        SELECT config->>'feed_url'
        FROM sources
        WHERE connector_type = 'rss'
          AND status = 'ACTIVE'
          AND config->>'feed_url' IS NOT NULL
        LIMIT 10
    " 2>/dev/null)

    SUCCESS=0
    FAIL=0

    while IFS= read -r url; do
        if [ -n "$url" ]; then
            HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || echo "000")
            if [ "$HTTP_CODE" = "200" ]; then
                SUCCESS=$((SUCCESS + 1))
            else
                FAIL=$((FAIL + 1))
                echo "    ⚠ $url -> HTTP $HTTP_CODE"
            fi
        fi
    done <<< "$FEED_URLS"

    echo "  抽样数: $((SUCCESS + FAIL))"
    echo "  成功: $SUCCESS"
    echo "  失败: $FAIL"

    if [ "$FAIL" -gt 0 ]; then
        echo "  ⚠ 发现 $FAIL 个源无法访问"
    fi
}
```

**输出示例**:
```
[RSS 源可访问性抽样]
    ⚠ https://feedproxy.feedly.com/xxx -> HTTP 403
    ⚠ https://rsshub.app/xxx -> HTTP 403
  抽样数: 10
  成功: 8
  失败: 2
  ⚠ 发现 2 个源无法访问
```

---

### 新增 Level 5: 深度测试

```bash
verify_level5() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Level 5: 深度测试"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    verify_api_edge_cases
    verify_api_error_handling

    echo ""
    echo "Level 5: ✓ 通过"
}
```

#### 5.1 API 边界测试 `verify_api_edge_cases()`

**目的**: 测试 API 参数边界和异常情况

**实现方案**:

```bash
verify_api_edge_cases() {
    echo ""
    echo "[API 边界测试]"

    API_KEY=$(cat /tmp/cyberpulse_verify.key 2>/dev/null)
    if [ -z "$API_KEY" ]; then
        echo "  ⚠ 跳过: 未找到 API Key"
        return
    fi

    # 测试 1: limit 边界
    echo "  测试 limit 参数边界..."

    # limit=1
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $API_KEY" \
        "${API_URL}/api/v1/contents?limit=1")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "    ✓ limit=1: HTTP 200"
    else
        echo "    ✗ limit=1: HTTP $HTTP_CODE"
    fi

    # limit=0 (应该返回错误)
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $API_KEY" \
        "${API_URL}/api/v1/contents?limit=0")
    if [ "$HTTP_CODE" = "422" ]; then
        echo "    ✓ limit=0: HTTP 422 (参数错误)"
    else
        echo "    ⚠ limit=0: HTTP $HTTP_CODE (预期 422)"
    fi

    # limit=-1 (应该返回错误)
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $API_KEY" \
        "${API_URL}/api/v1/contents?limit=-1")
    if [ "$HTTP_CODE" = "422" ]; then
        echo "    ✓ limit=-1: HTTP 422 (参数错误)"
    else
        echo "    ⚠ limit=-1: HTTP $HTTP_CODE (预期 422)"
    fi

    # limit=200 (文档说最大100，检查是否被限制)
    BODY=$(curl -s -H "Authorization: Bearer $API_KEY" \
        "${API_URL}/api/v1/contents?limit=200")
    COUNT=$(echo "$BODY" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('data', [])))" 2>/dev/null || echo "0")
    if [ "$COUNT" -le 100 ]; then
        echo "    ✓ limit=200: 返回 $COUNT 条 (被限制为 ≤100)"
    else
        echo "    ⚠ limit=200: 返回 $COUNT 条 (未限制最大值)"
    fi

    # 测试 2: 游标验证
    echo "  测试游标参数..."

    # 无效游标格式
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $API_KEY" \
        "${API_URL}/api/v1/contents?cursor=invalid_cursor")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "    ⚠ 无效游标: HTTP 200 (未校验游标格式)"
    else
        echo "    ✓ 无效游标: HTTP $HTTP_CODE"
    fi

    # 测试 3: source_id 筛选
    echo "  测试 source_id 筛选..."
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $API_KEY" \
        "${API_URL}/api/v1/contents?source_id=src_notexist")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "    ✓ 不存在的 source_id: HTTP 200 (返回空列表)"
    else
        echo "    ⚠ 不存在的 source_id: HTTP $HTTP_CODE"
    fi
}
```

**输出示例**:
```
[API 边界测试]
  测试 limit 参数边界...
    ✓ limit=1: HTTP 200
    ✓ limit=0: HTTP 422 (参数错误)
    ✓ limit=-1: HTTP 422 (参数错误)
    ⚠ limit=200: 返回 200 条 (未限制最大值)
  测试游标参数...
    ⚠ 无效游标: HTTP 200 (未校验游标格式)
  测试 source_id 筛选...
    ✓ 不存在的 source_id: HTTP 200 (返回空列表)
```

#### 5.2 API 错误处理测试 `verify_api_error_handling()`

**目的**: 测试 API 的错误响应格式

**实现方案**:

```bash
verify_api_error_handling() {
    echo ""
    echo "[API 错误处理测试]"

    # 测试 1: 无效 API Key
    echo "  测试认证错误..."
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer invalid_key" \
        "${API_URL}/api/v1/contents?limit=1")
    if [ "$HTTP_CODE" = "401" ]; then
        echo "    ✓ 无效 API Key: HTTP 401"
    else
        echo "    ⚠ 无效 API Key: HTTP $HTTP_CODE (预期 401)"
    fi

    # 测试 2: 缺失 Authorization
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        "${API_URL}/api/v1/contents?limit=1")
    if [ "$HTTP_CODE" = "401" ]; then
        echo "    ✓ 缺失 Authorization: HTTP 401"
    else
        echo "    ⚠ 缺失 Authorization: HTTP $HTTP_CODE (预期 401)"
    fi

    # 测试 3: 不存在的资源
    echo "  测试 404 错误..."
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $(cat /tmp/cyberpulse_verify.key)" \
        "${API_URL}/api/v1/contents/cnt_notexist")
    if [ "$HTTP_CODE" = "404" ]; then
        echo "    ✓ 不存在的内容: HTTP 404"
    else
        echo "    ⚠ 不存在的内容: HTTP $HTTP_CODE (预期 404)"
    fi

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $(cat /tmp/cyberpulse_verify.key)" \
        "${API_URL}/api/v1/sources/src_notexist")
    if [ "$HTTP_CODE" = "404" ]; then
        echo "    ✓ 不存在的源: HTTP 404"
    else
        echo "    ⚠ 不存在的源: HTTP $HTTP_CODE (预期 404)"
    fi

    # 测试 4: 参数类型错误
    echo "  测试参数验证..."
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $(cat /tmp/cyberpulse_verify.key)" \
        "${API_URL}/api/v1/contents?limit=abc")
    if [ "$HTTP_CODE" = "422" ]; then
        echo "    ✓ limit=abc: HTTP 422 (参数类型错误)"
    else
        echo "    ⚠ limit=abc: HTTP $HTTP_CODE (预期 422)"
    fi
}
```

**输出示例**:
```
[API 错误处理测试]
  测试认证错误...
    ✓ 无效 API Key: HTTP 401
    ✓ 缺失 Authorization: HTTP 401
  测试 404 错误...
    ✓ 不存在的内容: HTTP 404
    ✓ 不存在的源: HTTP 404
  测试参数验证...
    ✓ limit=abc: HTTP 422 (参数类型错误)
```

---

## 新增命令行参数

```bash
# 新增参数
--quick           # 快速验证（只运行 Level 1-3）
--quality         # 只运行数据质量验证（Level 4）
--deep            # 运行深度测试（Level 5）
--all             # 运行所有级别（默认）
--source-sample N # RSS 源抽样数量（默认 10）
```

**使用示例**:

```bash
# 完整验证（所有级别）
./scripts/verify.sh

# 快速验证（跳过深度测试）
./scripts/verify.sh --quick

# 只检查数据质量
./scripts/verify.sh --quality

# 只运行深度测试
./scripts/verify.sh --deep

# 抽样 20 个 RSS 源检查可访问性
./scripts/verify.sh --source-sample 20
```

---

## 报告输出扩展

在验证报告中新增 Level 4 和 Level 5 的输出：

```markdown
## Level 4: 数据质量验证

### 内容质量分析

| 指标 | 值 |
|------|-----|
| 总内容数 | 1582 |
| 完整内容 | 313 (19.8%) |
| 标题=正文 | 18 |
| 正文过短(<100字) | 45 |

### 源健康状态

| 指标 | 值 |
|------|-----|
| 总源数 | 146 |
| 活跃源 | 146 |
| 从未采集 | 57 |

### RSS 源可访问性抽样

| 抽样数 | 成功 | 失败 |
|--------|------|------|
| 10 | 8 | 2 |

**结果：** ⚠ 发现问题（详见上方）

---

## Level 5: 深度测试

### API 边界测试

| 测试项 | 状态 |
|--------|------|
| limit=1 | ✓ HTTP 200 |
| limit=0 | ✓ HTTP 422 |
| limit=-1 | ✓ HTTP 422 |
| limit=200 | ⚠ 返回 200 条（未限制） |
| 无效游标 | ⚠ HTTP 200（未校验） |

### API 错误处理测试

| 测试项 | 状态 |
|--------|------|
| 无效 API Key | ✓ HTTP 401 |
| 缺失 Authorization | ✓ HTTP 401 |
| 不存在的内容 | ✓ HTTP 404 |
| 不存在的源 | ✓ HTTP 404 |
| 参数类型错误 | ✓ HTTP 422 |

**结果：** ⚠ 发现问题（详见上方）
```

---

## 实现优先级

| 优先级 | 功能 | 说明 |
|--------|------|------|
| P1 | Level 4 内容质量验证 | 发现数据质量问题 |
| P1 | Level 4 源健康状态 | 发现未采集的源 |
| P2 | Level 4 RSS 源可访问性 | 发现无法访问的源 |
| P2 | Level 5 API 边界测试 | 发现 API 边界问题 |
| P2 | Level 5 错误处理测试 | 验证错误响应格式 |
| P3 | 命令行参数扩展 | --quick、--quality 等 |

---

## 相关文件

- `scripts/verify.sh` - 验证脚本（需修改）
- `docs/verification-guide.md` - 验证指南（需更新）

## 相关 Issue

- `2026-03-24-api-test-report.md` - API 测试报告
- `2026-03-24-content-quality-report.md` - 内容质量报告
- `2026-03-24-rss-source-accessibility.md` - RSS 源可访问性问题