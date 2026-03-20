# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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