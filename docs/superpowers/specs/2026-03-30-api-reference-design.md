# API 参考手册设计

> 创建日期：2026-03-30

---

## 目标

为 cyber-pulse 编写两份 API 参考手册：

1. **管理 API 参考手册** - 运维人员管理情报源、任务、客户端等
2. **业务 API 参考手册** - 下游应用开发者获取情报数据

---

## 文档定位

| 项目 | 管理 API 文档 | 业务 API 文档 |
|------|--------------|--------------|
| 目标读者 | 运维人员 | 下游应用开发者 |
| 文件位置 | `docs/admin-api-reference.md` | `docs/business-api-reference.md` |
| 请求示例 | api.sh 优先 + curl 备选 | TypeScript + curl |
| 认证侧重 | admin 权限、客户端管理完整流程 | read 权限、如何获取业务 Key |

---

## 共同结构框架

每份文档包含：

1. **Overview** - API 定位、版本、基础 URL
2. **Authentication** - API Key 机制、权限系统（各文档独立完整）
3. **Common Concepts / Pagination** - ID 格式、时间格式、分页机制
4. **Endpoints** - 按 API 资源分组，每个端点包含：
   - 端点路径和方法
   - 参数表格
   - 请求示例
   - 完整响应示例（所有字段）
   - 可能的错误码和原因
5. **Error Responses** - 通用错误码汇总表

---

## 管理 API 文档详细结构

### 文件：`docs/admin-api-reference.md`

```
# 管理 API 参考手册

## Overview
- API 定位：运维人员管理 cyber-pulse 系统
- 版本信息
- 基础 URL：http://localhost:8000/api/v1/admin

## Authentication
### Admin API Key 获取
- 简要说明 + 交叉引用部署指南
- 链接：[运维者部署指南 - 获取 Admin API Key](./ops-deployment-guide.md#获取-admin-api-key)

### API Key 格式
- cp_live_{32_hex_chars}
- 示例：cp_live_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6

### 认证方式
- Bearer Token
- Header: Authorization: Bearer cp_live_xxx

### 权限类型
- admin：管理 API 所需权限
- read：业务 API 所需权限

### 客户端管理（完整流程）
- 创建客户端（POST /api/v1/admin/clients）
- 查看客户端（GET /api/v1/admin/clients）
- 挂起/激活客户端
- 密钥轮换
- 撤销客户端

## Common Concepts
### ID 格式
- source_id: src_{8位hex}
- job_id: job_{16位hex}
- client_id: cli_{16位hex}

### 时间格式
- ISO 8601 (UTC)
- 示例：2026-03-30T10:00:00Z

## Endpoints

### Sources Management
#### GET /api/v1/admin/sources - 列出情报源
- 参数：status, tier, scheduled
- api.sh 示例 + curl 示例
- 完整响应示例
- 错误：401/403/422

#### POST /api/v1/admin/sources - 创建情报源
- 请求体参数表格
- api.sh 示例 + curl 示例
- 完整响应示例
- 错误：401/403/409/422

#### GET /api/v1/admin/sources/{source_id} - 查看详情
- 路径参数
- api.sh 示例 + curl 示例
- 完整响应示例
- 错误：400/401/403/404

#### PUT /api/v1/admin/sources/{source_id} - 更新情报源
- 请求体参数表格
- api.sh 示例 + curl 示例
- 完整响应示例
- 错误：400/401/403/404/422

#### DELETE /api/v1/admin/sources/{source_id} - 删除情报源
- api.sh 示例 + curl 示例
- 响应示例
- 错误：400/401/403/404

#### POST /api/v1/admin/sources/{source_id}/test - 测试连接
- api.sh 示例 + curl 示例
- 完整响应示例（成功和失败两种）
- 错误：400/401/403/404

#### POST /api/v1/admin/sources/{source_id}/validate - 验证质量
- api.sh 示例 + curl 示例
- 完整响应示例
- 错误：400/401/403/404

#### POST /api/v1/admin/sources/{source_id}/schedule - 设置调度
- 请求体参数：interval
- api.sh 示例 + curl 示例
- 完整响应示例
- 错误：400/401/403/404/422

#### DELETE /api/v1/admin/sources/{source_id}/schedule - 取消调度
- api.sh 示例 + curl 示例
- 响应示例
- 错误：400/401/403/404

#### GET /api/v1/admin/sources/defaults - 获取默认配置
- curl 示例
- 响应示例
- 错误：401/403

#### PATCH /api/v1/admin/sources/defaults - 更新默认配置
- 请求体参数：default_fetch_interval
- curl 示例
- 响应示例
- 错误：401/403/422

#### POST /api/v1/admin/sources/import - 批量导入（OPML）
- FormData 参数：file, force, skip_invalid
- curl 示例
- 完整响应示例
- 错误：400/401/403/500

#### GET /api/v1/admin/sources/export - 导出（OPML）
- 参数：status, tier
- curl 示例
- 响应（OPML XML）
- 错误：401/403/422

#### POST /api/v1/admin/sources/cleanup - 清理已删除源
- curl 示例
- 完整响应示例
- 错误：401/403

### Jobs Management
#### GET /api/v1/admin/jobs - 列出任务
- 参数：type, status, source_id, since, limit
- api.sh 示例 + curl 示例
- 完整响应示例
- 错误：401/403/422

#### POST /api/v1/admin/jobs - 创建采集任务
- 请求体参数：source_id
- api.sh 示例 + curl 示例
- 完整响应示例
- 错误：401/403/404/422

#### GET /api/v1/admin/jobs/{job_id} - 查看任务详情
- api.sh 示例 + curl 示例
- 完整响应示例
- 错误：400/401/403/404

#### DELETE /api/v1/admin/jobs/{job_id} - 删除失败任务
- api.sh 示例 + curl 示例
- 响应示例
- 错误：400/401/403/404

#### POST /api/v1/admin/jobs/{job_id}/retry - 重试失败任务
- api.sh 示例 + curl 示例
- 完整响应示例
- 错误：400/401/403/404

#### POST /api/v1/admin/jobs/cleanup - 清理历史任务
- 参数：days, status
- curl 示例
- 完整响应示例
- 错误：401/403/422

### Clients Management
#### GET /api/v1/admin/clients - 列出客户端
- 参数：status
- api.sh 示例 + curl 示例
- 完整响应示例
- 错误：401/403/422

#### POST /api/v1/admin/clients - 创建客户端
- 请求体参数：name, permissions, description, expires_at
- curl 示例
- 完整响应示例（包含 api_key 警告）
- 错误：401/403/422

#### GET /api/v1/admin/clients/{client_id} - 查看详情
- curl 示例
- 完整响应示例
- 错误：400/401/403/404

#### POST /api/v1/admin/clients/{client_id}/rotate - 轮换密钥
- curl 示例
- 完整响应示例（包含新 api_key）
- 错误：400/401/403/404

#### POST /api/v1/admin/clients/{client_id}/suspend - 挂起客户端
- curl 示例
- 完整响应示例
- 错误：400/401/403/404

#### POST /api/v1/admin/clients/{client_id}/activate - 激活客户端
- curl 示例
- 完整响应示例
- 错误：400/401/403/404

#### DELETE /api/v1/admin/clients/{client_id} - 撤销客户端
- curl 示例
- 响应示例
- 错误：400/401/403/404

### Logs & Diagnose
#### GET /api/v1/admin/logs - 查询系统日志
- 参数：level, source_id, since, limit
- curl 示例
- 完整响应示例
- 错误：401/403/422/500

#### GET /api/v1/admin/diagnose - 系统诊断概览
- curl 示例
- 完整响应示例（包含 statistics 各子对象）
- 错误：401/403

## Error Responses
- 通用错误码汇总表
- 400/401/403/404/409/422/500/503
```

---

## 业务 API 文档详细结构

### 文件：`docs/business-api-reference.md`

```
# 业务 API 参考手册

## Overview
- API 定位：下游应用获取已处理的情报数据
- 版本信息
- 基础 URL：http://localhost:8000/api/v1
- 数据流说明

## Authentication
### API Key 获取
- 业务 API Key 由运维人员通过管理 API 创建
- 创建方式示例（curl 命令调用管理 API）
- 权限要求：需要 admin 权限的客户端才能创建新客户端

### API Key 格式
- cp_live_{32_hex_chars}
- 示例：cp_live_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6

### 认证方式
- Bearer Token
- Header: Authorization: Bearer cp_live_xxx

### 权限类型
- read：业务 API 所需权限
- 说明：仅能访问 /api/v1/items 端点

## Pagination & Filtering

### 分页参数

| 参数 | 类型 | 说明 |
|------|------|------|
| cursor | string | 游标位置，格式 item_{8位hex} |
| from | string | 起始方向：latest（默认）、beginning |
| limit | int | 每页数量，1-100，默认 50 |

### 时间过滤参数

| 参数 | 类型 | 说明 |
|------|------|------|
| since | datetime | 发布时间起点（ISO 8601） |
| until | datetime | 发布时间终点（ISO 8601） |

### 获取方式示例

#### 方式一：获取最新数据（默认）
- 适用场景：首次获取、查看最新情报
- TypeScript 示例 + curl 示例
- 响应示例

#### 方式二：增量同步（使用 cursor）
- 适用场景：持续同步、断点续传
- TypeScript 示例 + curl 示例
- 响应示例

#### 方式三：从头遍历（from=beginning）
- 适用场景：全量同步、数据迁移
- TypeScript 示例 + curl 示例
- 响应示例

#### 方式四：按时间范围获取
- 适用场景：获取特定时间段数据
- TypeScript 示例 + curl 示例
- 响应示例

#### 方式五：时间范围 + 增量同步
- 适用场景：时间段内的分页获取
- TypeScript 示例 + curl 示例
- 响应示例

### 注意事项
- cursor 和 from 不能同时使用
- cursor 格式必须为 item_{8位hex}
- 时间过滤基于 published_at 字段

## Endpoints

### Items
#### GET /api/v1/items - 获取情报列表
- 参数表格：cursor, since, until, from, limit
- TypeScript 示例 + curl 示例
- 完整响应示例（所有字段，包含 source 子对象）
- 响应字段说明表格
- 错误：400/401/404

### Health Check
#### GET /health - 健康检查（无需认证）
- curl 示例
- 完整响应示例
- 用途说明
- 错误：无（始终返回）

## Error Responses
- 通用错误码汇总表
- 400/401/500/503
```

---

## 示例编写规范

### curl 示例格式

```bash
curl -X GET "http://localhost:8000/api/v1/admin/sources" \
  -H "Authorization: Bearer cp_live_xxx" \
  -H "Content-Type: application/json"
```

### TypeScript 示例格式

```typescript
const response = await fetch(
  "http://localhost:8000/api/v1/items?limit=50",
  {
    headers: {
      Authorization: "Bearer cp_live_xxx",
    },
  }
);
const data = await response.json();
```

### api.sh 示例格式

```bash
./scripts/api.sh sources list
./scripts/api.sh sources create --name "安全客" --type rss --url "https://www.anquanke.com/rss.xml" --tier T1
```

### 响应示例格式

- 展示所有字段
- 使用实际示例值填充
- null 字段明确显示为 null
- 时间使用 ISO 8601 格式

---

## 响应字段来源

响应字段需从以下源文件确认：

- `src/cyberpulse/api/schemas/item.py` - ItemResponse, ItemListResponse
- `src/cyberpulse/api/schemas/source.py` - SourceResponse, SourceListResponse
- `src/cyberpulse/api/schemas/job.py` - JobResponse, JobListResponse
- `src/cyberpulse/api/schemas/client.py` - ClientResponse, ClientListResponse
- `src/cyberpulse/api/schemas/diagnose.py` - DiagnoseResponse
- `src/cyberpulse/api/schemas/log.py` - LogEntry, LogListResponse

---

## 错误码来源

错误码需从以下源文件确认：

- `src/cyberpulse/api/routers/admin/sources.py`
- `src/cyberpulse/api/routers/admin/jobs.py`
- `src/cyberpulse/api/routers/admin/clients.py`
- `src/cyberpulse/api/routers/admin/logs.py`
- `src/cyberpulse/api/routers/admin/diagnose.py`
- `src/cyberpulse/api/routers/items.py`
- `src/cyberpulse/api/auth.py`

---

## 文档语言规范

- 标题/参数名：英文（如 "Sources Management"、"cursor"）
- 说明文字：中文
- 示例代码：保留原语言
- ID/时间格式：英文描述

---

## 下一步

设计确认后，转入 writing-plans 创建实现计划。