# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.8.2] - 2026-04-02

### Fixed

- Issue #107: 修复全文采集成功后 Item 状态死循环问题
  - 根因：`quality_check_item` 不检查 `full_fetch_succeeded` 状态
  - 修复：当 `full_fetch_succeeded=True` 且内容仍不合格时直接 REJECT
  - 确保 MAPPED 状态的数据质量

### Added

- `POST /api/v1/admin/items/fix-stuck-pending`: 数据修复 API
  - 修复卡在 `PENDING_FULL_FETCH` 状态的历史数据
  - 智能处理：内容合格 → 重新检查，内容仍不合格 → REJECT

## [1.8.1] - 2026-04-02

### Fixed

- Issue #102: 修复容器状态检查关键词错误 (`running` → `Up`)
  - Docker Compose v2 输出格式为 `Up X minutes (healthy)`
  - 影响脚本: `cyber-pulse.sh`, `create-backup.sh`, `restore-backup.sh`, `create-snapshot.sh`, `restore-snapshot.sh`
- Issue #103: 修复 ENV_FILE 路径配置不一致
  - 脚本路径从 `$PROJECT_ROOT/.env` 改为 `$PROJECT_ROOT/deploy/.env`
  - 影响脚本: `create-backup.sh`, `restore-backup.sh`, `create-snapshot.sh`, `restore-snapshot.sh`

## [1.8.0] - 2026-04-01

### Added

#### 增量同步 API
- `since` 参数：支持全量同步 (`since=beginning`) 和增量同步 (`since={datetime}`)
- `cursor` 参数：基于 `item_id` 的游标分页，必须与 `since` 配合使用
- `last_item_id` 和 `last_fetched_at`：响应中包含分页状态信息
- 增量同步时按 `fetched_at` 升序排列，无 `since` 时按降序排列

#### URL 变更自动触发采集
- `JobTrigger.URL_UPDATE`：新增触发类型，记录 URL 变更导致的采集
- `update_source` API 自动检测 `feed_url` 变更并触发采集任务
- URL 相同时不重复触发（幂等性）
- 触发失败时返回警告信息

### Changed

- `ItemListResponse` schema：移除 `next_cursor`，改用 `last_item_id` 和 `last_fetched_at`
- Items API 只返回 `MAPPED` 状态的 Item（下游系统可见性控制）

### Fixed

- Issue #97：情报源 URL 变更后需手动触发采集的问题
- 增量同步 API 设计完善，支持下游系统高效数据获取

## [1.7.0] - 2026-04-01

### Added

- **Docker Compose 项目名隔离**：不同环境自动获得独立的容器和数据卷
- **端口偏移机制**：`基础端口 + 环境偏移量`（prod=0, test=+1, dev=+2）
- **脚本自检测**：自动识别开发者/运维者模式，生成正确的项目名和端口配置
- **生产环境安全**：PostgreSQL 和 Redis 端口不再对外暴露

### Changed

- `generate-env.sh` 新增 `detect_mode`、`get_current_env`、`generate_project_name`、`generate_ports` 函数
- `cyber-pulse.sh` 的 `get_current_env` 函数根据运行模式返回正确的默认环境
- `docker-compose.yml` 端口改为变量配置
- `docker-compose.prod.yml` 使用 `ports: !reset []` 确保数据库端口不暴露

### Fixed

- Issue #94: Docker Compose 项目名冲突导致 worktree 覆盖生产环境数据
- 密码同步问题：不同环境共享同一套 Docker volume 导致密码不一致

## [1.6.2] - 2026-03-31

### Added

- `JobTrigger` 枚举：区分 job 触发来源（manual/scheduler/create）
- Job 创建审计：所有采集触发点统一创建 job 记录
- `trigger` 字段：Job 模型和 API 响应新增触发来源字段

### Changed

- **Client DELETE 端点**：从软删除改为硬删除（物理删除）
- **Scheduler job 创建**：`collect_source` 和 `run_scheduled_collection` 创建 job 记录用于审计追踪

### Removed

- `routers/clients.py`：未使用的遗留文件
- `full_fetch_attempted`/`full_fetch_succeeded`：Items API 移除内部字段
- `sources.yaml`：部署包不再包含，改为创建空示例文件
- `revoke_client` 方法：auth.py 中不再使用

### Fixed

- Issue #91: Client 删除改为物理删除
- Issue #92: Scheduler 创建 job 记录用于审计追踪

## [1.6.1] - 2026-03-31

### Added

#### API 参考文档
- `docs/admin-api-reference.md` - 管理 API 参考手册（29 个端点）
- `docs/business-api-reference.md` - 业务 API 参考手册（2 个端点）
- 设计文档和实现计划（`docs/superpowers/specs/`, `docs/superpowers/plans/`）

### Changed

- `api.sh` 移除 `items` 命令（调用不存在的端点）
- `api.sh` 新增 `sources validate` 子命令
- 部署指南改进：一步式清理命令 `docker compose down -v`

### Fixed

- **Worker Redis 连接错误**：`tasks/__init__.py` 导入顺序修复，确保 broker 在任务模块之前初始化
- **RSS 解析失败 (Brotli)**：`http_headers.py` 移除 `br` 编码，httpx 不原生支持 Brotli
- **Jina AI 错误检测**：新增 `JINA_ERROR_PATTERNS` 检测 HTTP 200 响应中的错误消息
- **内容质量误判**：`INVALID_CONTENT_PATTERNS` 修复，避免 "Forbidden" 误匹配正常内容

## [1.6.0] - 2026-03-29

### Added

#### 双模式部署系统
- **开发者模式**：git clone 完整代码，本地构建镜像
- **运维者模式**：下载部署包，远程拉取镜像
- 自动模式检测：基于 `.git` 目录存在性
- 版本动态解析：`APP_VERSION` 环境变量 → `.version` 文件 → 默认值

#### 升级系统
- `cyber-pulse.sh upgrade`：一键升级到最新版本
- 升级前自动创建快照（数据库备份）
- 升级失败自动回滚
- 健康检查验证升级成功

#### CI/CD 增强
- GitHub Actions 自动构建部署包
- 阿里云容器镜像仓库托管
- Docker build-time 版本注入

### Changed

- `install.sh` 支持 `--type ops` 参数一键安装
- `api.sh configure` 支持非交互式参数
- `cyber-pulse.sh deploy` 完成后显示 Admin Key

### Fixed

- Git 检查在运维者模式下改为非阻塞提示
- 测试套件动态读取 `deploy/.env` 配置
- 测试 job_id 格式符合验证规则
- 内容质量测试阈值更新（500 字符、50 词）

### Documentation

- 新增 `docs/developer-deployment-guide.md`
- 新增 `docs/ops-deployment-guide.md`
- 更新 `README.md` 和 `CLAUDE.md` 反映双模式部署

## [1.5.0] - 2026-03-28

### Added

#### 两级全文提取策略
- **Level 1**: httpx + trafilatura 直接抓取（快速，无限制）
- **Level 2**: Jina AI Reader 作为降级方案（20 RPM 限制）
- `FullContentFetchService` 实现两级策略自动切换
- `ContentQualityService` 统一内容质量评估和全文提取触发
- `PENDING_FULL_FETCH` 状态：等待全文提取的 Item

#### Redis 分布式 Rate Limiter
- 使用 Redis Sorted Set (ZSET) 实现滑动窗口算法
- 跨进程/跨容器 Rate Limit 同步
- 解决多 Worker 进程导致的 HTTP 429 问题

#### 自动重试机制
- `retry_pending_full_fetch` 定时任务（每 30 分钟）
- 自动重试卡在 PENDING_FULL_FETCH 状态的 Item
- 任务超时配置：10 分钟（适应 Rate Limiting）

#### Job/Source 生命周期管理
- `JobLifecycleService`: 任务删除、重试、清理
- `DELETE /admin/jobs/{job_id}`: 删除失败任务
- `POST /admin/jobs/{job_id}/retry`: 重试失败任务（最多 3 次）
- `POST /admin/jobs/cleanup`: 清理旧任务
- `POST /admin/sources/cleanup`: 物理删除已删除的源（级联删除 items 和 jobs）
- CLI 命令: `jobs delete/retry/cleanup`, `sources cleanup`
- 完整错误处理：数据库回滚、任务分发失败恢复

### Changed

- 内容质量阈值提升：MIN_CONTENT_LENGTH 500（原 100），MIN_WORD_COUNT 50（新增）
- Item 状态流转优化：NORMALIZED → QUALITY_CHECK → PENDING_FULL_FETCH/MAPPED
- Source 创建后自动触发采集任务

### Fixed

- **asyncio.Lock 事件循环绑定问题**：`asyncio.run()` 每次创建新事件循环导致 Lock 绑定失败
- **多进程 Rate Limit 失效**：threading.Lock 无法跨进程同步，改用 Redis 分布式锁
- **内容质量检查未触发全文提取**：检查顺序调整，先检查内容质量再检查元数据

## [1.4.0] - 2026-03-27

### Added

#### API 架构重构
- Admin API 端点统一到 `/api/v1/admin/` 前缀
- 新增 Jobs API：任务创建、状态查询、历史记录
- 新增 Logs API：日志查询、过滤、导出
- 新增 Clients API：客户端管理、权限控制
- 新增 Diagnose API：系统诊断、健康检查
- OPML 导入/导出支持

#### 数据模型增强
- Job 模型：任务跟踪（type, status, result, error tracking）
- Source 模型新增字段：`consecutive_failures`, `last_error_at`, `last_error_message`, `last_job_id`
- Source 模型全文拉取字段：`needs_full_fetch`, `full_fetch_threshold`, `content_type`, `avg_content_length`, `quality_score`
- Item 模型全文拉取字段：`full_fetch_attempted`, `full_fetch_succeeded`
- Item cursor 格式简化：`item_{uuid8}`（移除时间戳前缀）

#### RSS 采集增强
- 自动触发初始采集：创建源后立即启动采集任务
- OPML 导入后自动触发采集
- HTTP 重定向跟随（301/308）
- 默认 User-Agent 头，避免 403 错误
- 内容质量检测和全文拉取触发

#### 部署优化
- `api.sh` 脚本替代 CLI 工具
- 简化部署命令：`./scripts/api.sh configure`、`./scripts/api.sh diagnose`
- 本地测试环境部署指南

### Changed

- CLI 工具已移除，改用 `api.sh` 脚本
- Unhealthy sources 现在在 diagnose 中可见

### Fixed

- CLI JSON 中文编码问题
- IMPORT job 未触发处理的问题
- 静默失败问题：ingestion 触发失败时添加警告
- `api.sh jobs run` 调用正确的 API 端点
- `api.sh sources create --url` 正确映射到 `config.feed_url`

### Documentation

- SQLAlchemy 2.0 Mapped 迁移设计文档
- 全文拉取混合策略设计文档

## [1.3.0] - 2026-03-22

### Added

#### Documentation
- 完整用户文档体系
  - 快速入门教程 (docs/quickstart.md)
  - 部署指南 (docs/deployment-guide.md)
  - API 使用指南 (docs/api-guide.md)
  - API 参考 (docs/api-reference.md)
  - 安全配置指南 (docs/security-guide.md)
  - 故障排查手册 (docs/troubleshooting.md)
  - 备份与恢复指南 (docs/backup-restore.md)
  - 升级迁移指南 (docs/upgrade-guide.md)
  - 情报源配置示例 (docs/source-config-examples.md)
  - 监控与告警指南 (docs/monitoring.md)

### Fixed
- SSRF 防护 DNS 解析失败时改为 fail closed（防止绕过）
- Docker Compose healthcheck 使用 POSTGRES_USER 环境变量

## [1.2.0] - 2026-03-21

### Added

#### diagnose 命令增强
- `diagnose system` 新增 API 服务健康检查
- `diagnose system` 新增 Dramatiq 任务队列状态检查
- `diagnose sources` 新增 Recent Collection Activity 表格，显示采集状态（Fresh/Recent/Stale/Never）
- `diagnose errors` 新增 Rejection Reason 列，显示 Item 被拒绝的具体原因

#### log 命令增强
- `log export` 命令：导出日志到文件，支持 `--since` 和 `--level` 过滤
- `log clear` 命令：清理旧日志条目，支持 `--older-than` 和确认提示
- `log errors` 和 `log search` 新增 `--format json` 选项，支持 JSON 格式输出

### Fixed
- 修复 `tempfile.mktemp` 已弃用警告，改用 `tempfile.mkstemp`（安全加固）
- 修复 `diagnose system` 静默异常吞没问题，添加日志记录
- 修复 `log clear` 数据丢失风险，改用从文件末尾读取并增大限制
- 修复 `diagnose errors` rejection_reason 类型假设未验证问题
- 更新 `diagnose_system()` 和 `diagnose_errors()` 的 docstring

### Documentation
- 更新 CLI 使用手册（docs/cli-usage-manual.md），添加新命令文档

## [1.1.0] - 2026-03-20

### Added

#### Verification System
- `scripts/verify.sh` - 2-level verification script (Level 1: System Readiness, Level 2: Functional Verification)
- `Makefile` with `verify` and `verify-report` targets
- `sources.yaml` template for verification intelligence sources
- `docs/verification-guide.md` - Usage documentation

### Fixed
- Added `DRAMATIQ_BROKER_URL` environment variable to docker-compose.yml
- Fixed scheduler asyncio event loop issue in `scheduler/main.py`
- Fixed Dockerfile build order for editable install

## [1.0.0] - 2026-03-20

### Added

#### Phase 1: Core Infrastructure
- SQLAlchemy models (Source, Item, Content, ApiClient)
- PostgreSQL database with Alembic migrations
- SourceService for source management
- RSSConnector for RSS/Atom feed collection

#### Phase 2A: Data Processing Pipeline
- ItemService for item lifecycle management
- NormalizationService (content extraction, HTML cleaning, Markdown conversion)
- QualityGateService (metadata integrity, content quality, structure validation)
- ContentService for cross-source deduplication

#### Phase 2B: Multi-Source Collection
- APIConnector for REST API data sources
- WebConnector (trafilatura-based web scraping)
- MediaConnector for YouTube and media platforms
- ConnectorFactory for type-based connector creation

#### Phase 2C: API Service
- FastAPI REST API with API Key authentication
- Content API (incremental pull with cursor)
- Source management API
- Client management API
- Health check endpoint

#### Phase 2D: Scheduling System
- APScheduler for scheduled job management
- Dramatiq task queue with Redis broker
- Worker for async task execution
- Scheduler service with job lifecycle management

#### Phase 2E: Scoring System
- SourceScoreService with three-dimension scoring
- Stability (40%), Activity (30%), Quality (30%)
- Tier evolution based on score changes

#### Phase 2F: CLI Tools
- Typer CLI with 7 command modules
- Interactive TUI with auto-completion
- Source, Job, Content, Client, Config, Log, Diagnose commands

#### Phase 3: End-to-End Integration
- Docker Compose deployment (5 services)
- E2E tests (542 lines, complete workflow)
- Dockerfile with security hardening
- CLI usage manual
- Project summary report

### Security
- Environment variable substitution for sensitive data
- API Key format: `cp_live_{hex32}` (avoids GitHub false positives)
- Production Docker image excludes dev dependencies

### Documentation
- Technical specification (`docs/superpowers/specs/`)
- Implementation plans (`docs/superpowers/plans/`)
- CLI usage manual (`docs/cli-usage-manual.md`)
- Design documents (10 files, progressive loading)

### Testing
- 706 test cases
- Unit tests (~600), Integration tests (~80), E2E tests (~26)
- Core modules coverage ≥ 80%

## [0.1.0] - 2026-03-18

### Added
- Initial project structure
- Basic configuration and dependencies

---

[1.8.1]: https://github.com/cyberstrat-forge/cyber-pulse/releases/tag/v1.8.1
[1.8.0]: https://github.com/cyberstrat-forge/cyber-pulse/releases/tag/v1.8.0
[1.7.0]: https://github.com/cyberstrat-forge/cyber-pulse/releases/tag/v1.7.0
[1.6.1]: https://github.com/cyberstrat-forge/cyber-pulse/releases/tag/v1.6.1
[1.6.0]: https://github.com/cyberstrat-forge/cyber-pulse/releases/tag/v1.6.0
[1.5.0]: https://github.com/cyberstrat-forge/cyber-pulse/releases/tag/v1.5.0
[1.4.0]: https://github.com/cyberstrat-forge/cyber-pulse/releases/tag/v1.4.0
[1.3.0]: https://github.com/cyberstrat-forge/cyber-pulse/releases/tag/v1.3.0
[1.0.0]: https://github.com/cyberstrat-forge/cyber-pulse/releases/tag/v1.0.0
[0.1.0]: https://github.com/cyberstrat-forge/cyber-pulse/releases/tag/v0.1.0