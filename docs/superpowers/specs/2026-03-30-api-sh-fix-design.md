# api.sh 修复设计

> 创建日期：2026-03-30
> 关联 Issue: #87

---

## 问题描述

`api.sh` 存在以下问题：

| 问题 | 详情 |
|------|------|
| `items get` 调用不存在的端点 | 调用 `GET /api/v1/items/{item_id}`，但该端点不存在 |
| `items list` 参数与 API 不匹配 | 支持 `--status`, `--source`，但 API 参数是 `cursor, since, until, from, limit` |
| `validate` 端点无命令 | `POST /sources/{source_id}/validate` 没有 api.sh 命令支持 |

---

## 设计决策

### items 命令处理

**决策：移除 items 命令**

理由：
- `items` 是业务 API，面向下游应用开发者
- `api.sh` 是运维管理工具，业务数据查询不属于运维管理范畴
- 运维人员可通过 `curl` 或下游系统查看数据

### validate 命令设计

**决策：作为 sources 子命令**

```bash
./scripts/api.sh sources validate <source_id>
```

理由：
- 与 `sources test` 命令并列，逻辑清晰
- 符合 api.sh 现有的命令组织结构

---

## 实现细节

### 删除内容

| 位置 | 行号 | 删除内容 |
|------|------|----------|
| 函数定义 | 1041-1054 | `cmd_items()` 函数 |
| 函数定义 | 1056-1092 | `cmd_items_list()` 函数 |
| 函数定义 | 1094-1106 | `cmd_items_get()` 函数 |
| 函数定义 | 1108-1113 | `print_items_help()` 函数 |
| main 函数 | 1205-1208 | `items)` case 分支 |
| show_help 函数 | 1160-1162 | items 相关帮助信息（3行） |

**注意**：删除后需验证行号偏移

### 新增内容

#### 1. cmd_sources_validate 函数

在 `cmd_sources_cleanup()` 函数之后、`print_sources_help()` 函数之前插入。

```bash
cmd_sources_validate() {
    local source_id="${1:-}"

    if [[ -z "$source_id" ]]; then
        die "Usage: api.sh sources validate <source_id>"
    fi

    print_info "Validating source: $source_id"

    local response
    response=$(api_post "/api/v1/admin/sources/${source_id}/validate")
    check_api_error "$response"

    local is_valid
    is_valid=$(echo "$response" | jq -r '.is_valid')

    if [[ "$is_valid" == "true" ]]; then
        print_success "Validation passed"
    else
        print_warning "Validation failed"
    fi

    echo ""
    echo "$response" | jq .
}
```

#### 2. 更新 cmd_sources 函数

在 case 语句中添加（第 277 行 cleanup 之后）：

```bash
        validate)       cmd_sources_validate "$@" ;;
```

#### 3. 更新 print_sources_help 函数

在 `test` 命令说明之后添加：

```
    validate <source_id>                      验证源质量
```

---

## 测试验证

修改后验证：

```bash
# 1. 验证 items 命令已移除
./scripts/api.sh items list
# 预期：报错 "Unknown command: items"

# 2. 验证 validate 命令可用
./scripts/api.sh sources validate src_abc12345
# 预期：显示验证结果

# 3. 验证帮助信息
./scripts/api.sh sources --help
# 预期：包含 validate 命令说明
```

---

## 影响范围

- `scripts/api.sh` - 唯一修改文件
- 无 API 变更
- 无数据库变更