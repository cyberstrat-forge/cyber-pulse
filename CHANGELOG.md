# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- RSS auto-discovery service for finding RSS feeds from site URLs
- Source failure tracking with `consecutive_failures` and `last_error_at` fields
- Automatic source freezing after 5 consecutive failures
- RSS feed URL auto-update on permanent redirect (301/308)
- RSS discovery integration when adding sources via CLI

### Fixed
- HTTP redirect handling in RSS connector (now follows redirects)
- Missing User-Agent header causing 403 errors from some RSS feeds

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

[1.0.0]: https://github.com/cyberstrat-forge/cyber-pulse/releases/tag/v1.0.0
[0.1.0]: https://github.com/cyberstrat-forge/cyber-pulse/releases/tag/v0.1.0