# 实现计划审核报告

## 一、代码实现状态

### 已实现（Level 1）

| 组件 | 文件 | 状态 |
|------|------|------|
| FullContentFetchService | `services/full_content_fetch_service.py` | ✅ Level 1 已实现 |
| SSRF 保护 | `services/base.py` | ✅ 已实现 |
| fetch_full_content 任务 | `tasks/quality_tasks.py` | ✅ 已实现（但逻辑需修改） |
| Item 模型 | `models/item.py` | ✅ 已有 full_fetch_attempted/succeeded 字段 |

### 未实现（计划新增）

| 组件 | 文件 | 状态 |
|------|------|------|
| PENDING_FULL_FETCH 状态 | `models/item.py` | ❌ 未实现 |
| JinaAIClient | `services/jina_client.py` | ❌ 文件不存在 |
| ContentQualityService | `services/content_quality_service.py` | ❌ 文件不存在 |
| Level 2 fallback | `services/full_content_fetch_service.py` | ❌ 未实现 |
| full_content_tasks.py | `tasks/full_content_tasks.py` | ❌ 文件不存在 |
| API 过滤修正 | `api/routers/items.py` | ❌ 仍是 `status != REJECTED` |
| 数据库迁移 | `alembic/versions/` | ❌ 未创建 |

---

## 二、现有代码问题

### 问题 1：API 过滤条件错误

```python
# items.py:71 - 当前
query = db.query(Item).filter(Item.status != ItemStatus.REJECTED)

# 需要
query = db.query(Item).filter(Item.status == ItemStatus.MAPPED)
```

**影响**：NEW、NORMALIZED、PENDING 状态的 item 会被错误暴露

### 问题 2：质量检测依赖源配置

```python
# quality_tasks.py:126 - 当前
if source and source.needs_full_fetch:
    needs_full_fetch = True

# 需要
# 使用 ContentQualityService 统一判断
```

**影响**：未配置 `needs_full_fetch` 的源不会触发全文获取

### 问题 3：全文获取失败不改变状态

```python
# quality_tasks.py:271 - 当前
item.full_fetch_succeeded = False
# status 不变，仍是 MAPPED

# 需要
item.status = ItemStatus.REJECTED
```

**影响**：全文获取失败的 item 仍被 API 暴露

### 问题 4：FullContentFetchService 缺少 Level 2

```python
# 当前：只有 Level 1 (httpx + trafilatura)
# 需要：Level 1 失败时调用 Jina AI
```

---

## 三、计划完整性检查

### ✅ 已覆盖

| 功能点 | 计划位置 | 状态 |
|--------|---------|------|
| PENDING_FULL_FETCH 状态 | Task 1 | ✅ |
| 数据库迁移 | Task 1 | ✅ |
| API 过滤修正 | Task 2 | ✅ |
| ContentQualityService | Task 3 | ✅ |
| 3 条触发规则 | Task 3 | ✅ |
| JinaAIClient | Task 4 | ✅ |
| Level 2 fallback | Task 5 | ✅ |
| full_content_tasks.py | Task 6 | ✅ |
| max_concurrency=3 | Task 6 | ✅ |
| quality_tasks.py 修改 | Task 7 | ✅ |
| 创建源触发采集 | Task 7 | ✅ |

### ❌ 遗漏项

| 功能点 | 问题 | 建议 |
|--------|------|------|
| Source.needs_full_fetch 字段 | 计划移除依赖，但未处理字段本身 | 可保留字段（向后兼容），但不再使用 |
| 配置化参数 | 设计文档提到可配置，计划未实现 | 可作为后续优化，当前硬编码足够 |
| 监控/日志 | 未提及 Level 1/2 成功率统计 | 建议添加日志统计 |

---

## 四、计划合理性检查

### ✅ 合理设计

| 设计点 | 评估 |
|--------|------|
| 两层策略 | ✅ Level 1 快速处理大部分，Level 2 救援反爬 |
| 20 RPM 限制 | ✅ 无需 API Key，简单可靠 |
| max_concurrency=3 | ✅ 3 * 20 = 60 RPM，安全边际足够 |
| 失败 → REJECTED | ✅ 简化业务逻辑，保证 API 质量一致 |
| 统一触发点 | ✅ 移除源级配置，减少运维复杂度 |

### ⚠️ 需要考虑

| 设计点 | 风险 | 建议 |
|--------|------|------|
| Jina AI 可用性 | 服务不可用时无法救援 | 可接受，失败即 REJECTED |
| 无 API Key 限制 | 20 RPM 可能不够用 | 当前规模足够，后续可升级 |
| 重归一化循环 | 可能产生死循环？ | 不会：full_fetch_attempted=True 防止重复 |

---

## 五、测试完备性检查

### 现有测试覆盖

| 测试文件 | 覆盖范围 | 状态 |
|----------|---------|------|
| `test_full_content_fetch.py` | Level 1 (httpx) | ✅ 完整 |
| `test_quality_tasks.py` | quality_check_item, fetch_full_content | ✅ 完整 |
| SSRF 测试 | localhost, 内网 IP | ✅ 已覆盖 |

### 计划新增测试

| 测试文件 | 覆盖范围 | 计划状态 |
|----------|---------|---------|
| `test_jina_client.py` | JinaAIClient | ✅ 计划包含 |
| `test_content_quality.py` | ContentQualityService | ✅ 计划包含 |
| `test_full_content_tasks.py` | fetch_full_content 任务 | ✅ 计划包含 |
| `test_items.py` 更新 | API 过滤测试 | ✅ 计划包含 |

### ⚠️ 测试遗漏

| 测试场景 | 问题 | 建议 |
|----------|------|------|
| PENDING_FULL_FETCH 状态 | 无专门测试 | 在 quality_tasks 测试中添加 |
| Level 2 fallback 集成 | 无端到端测试 | 添加集成测试 |
| 并发限制测试 | 未测试 max_concurrency=3 | 可作为后续优化 |

---

## 六、计划正确性检查

### ✅ 正确的实现

| 检查项 | 结果 |
|--------|------|
| Jina AI 请求头 | ✅ X-Return-Format: markdown, X-Md-Link-Style: discarded |
| Jina AI URL 格式 | ✅ https://r.jina.ai/{url} |
| 状态流转 | ✅ PENDING_FULL_FETCH → NORMALIZED/REJECTED |
| ContentQualityService 规则 | ✅ 长度、相似度、无效模式 |

### ⚠️ 需要修正

| 检查项 | 问题 | 修正建议 |
|--------|------|---------|
| Task 6 返回值 | 返回 dict 但任务通常返回 None | 可接受，便于调试 |
| Task 7 重复定义 | fetch_full_content 在 quality_tasks.py 已存在 | 需要迁移到 full_content_tasks.py 或修改现有实现 |

---

## 七、建议的修正

### 修正 1：明确 fetch_full_content 迁移策略

当前 `quality_tasks.py` 中已有 `fetch_full_content` 任务实现。计划需要明确：

**方案 A**：在 `full_content_tasks.py` 创建新任务，删除 `quality_tasks.py` 中的旧任务
**方案 B**：修改 `quality_tasks.py` 中现有任务，添加 Level 2 和 REJECTED 逻辑

**建议**：采用方案 A，保持职责分离

### 修正 2：添加 PENDING_FULL_FETCH 状态测试

在 `test_quality_tasks.py` 中添加：

```python
def test_quality_check_sets_pending_full_fetch(self, test_item):
    """Test that content insufficient sets PENDING_FULL_FETCH status."""
    test_item.normalized_body = "Short"  # < 100 chars

    # ... 测试 status = PENDING_FULL_FETCH
```

### 修正 3：添加 Level 2 集成测试

```python
class TestLevel2Integration:
    """End-to-end tests for Level 2 fallback."""

    @pytest.mark.asyncio
    async def test_level1_403_triggers_level2(self):
        """Test that Level 1 403 triggers Level 2."""
        # Mock Level 1 返回 403
        # Mock Level 2 成功
        # 验证最终成功
```

---

## 八、总结

### 实现进度

| 类别 | 已完成 | 待实现 | 完成率 |
|------|--------|--------|--------|
| 核心功能 | 1/3 | 2/3 | 33% |
| 状态管理 | 0/2 | 2/2 | 0% |
| API 修正 | 0/1 | 1/1 | 0% |
| 测试覆盖 | 1/4 | 3/4 | 25% |
| **总计** | **2/10** | **8/10** | **20%** |

### 计划质量评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 完整性 | 8/10 | 有 2 处小遗漏 |
| 合理性 | 9/10 | 设计合理，简化有效 |
| 正确性 | 8/10 | 有 1 处任务冲突需明确 |
| 测试完备性 | 7/10 | 需补充状态测试和集成测试 |

### 行动建议

1. **立即执行**：开始实现 Task 1-8
2. **实现时补充**：PENDING_FULL_FETCH 状态测试
3. **后续优化**：监控统计、配置化参数

---

**结论**：计划整体质量良好，可以开始实现。建议实现时补充遗漏的测试用例。