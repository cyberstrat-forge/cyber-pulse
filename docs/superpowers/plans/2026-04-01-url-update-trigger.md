# URL 变更自动触发采集实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** 当情报源的 URL 变更时，自动触发采集任务

**Issue:** #97

**Architecture:** 在 `update_source` API 中检测 URL 变更，创建采集任务

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, PostgreSQL

---

## File Structure

| 文件 | 职责 |
|------|------|
| `src/cyberpulse/models/job.py` | 添加 `URL_UPDATE` 枚举值 |
| `src/cyberpulse/api/routers/admin/sources.py` | 检测 URL 变更并触发采集 |

---

### Task 1: 添加 URL_UPDATE 触发类型

**Files:**
- Modify: `src/cyberpulse/models/job.py`

- [ ] **Step 1: 在 JobTrigger 枚举中添加 URL_UPDATE**

在 `JobTrigger` 枚举中添加新值：

```python
class JobTrigger(StrEnum):
    """Job trigger source enumeration."""
    MANUAL = "manual"      # 手动触发: POST /jobs
    SCHEDULER = "scheduler"  # 定时触发: APScheduler
    CREATE = "create"      # 创建源自动触发
    URL_UPDATE = "url_update"  # URL 变更自动触发
```

- [ ] **Step 2: 提交变更**

```bash
git add src/cyberpulse/models/job.py
git commit -m "feat(models): add URL_UPDATE trigger type for auto-ingest on URL change"
```

---

### Task 2: 实现 URL 变更检测和自动触发

**Files:**
- Modify: `src/cyberpulse/api/routers/admin/sources.py`

- [ ] **Step 1: 在 update_source 函数中添加 URL 变更检测**

在 `update_source` 函数中，在更新 config 之前检测 URL 变更：

```python
@router.put("/sources/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: str,
    update: SourceUpdate,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> SourceResponse:
    """Update source configuration."""
    validate_source_id(source_id)

    source = db.query(Source).filter(Source.source_id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")

    # Detect URL change before updating
    url_changed = False
    if update.config is not None:
        old_feed_url = source.config.get("feed_url") if source.config else None
        new_feed_url = update.config.get("feed_url") if update.config else None
        if old_feed_url != new_feed_url:
            url_changed = True
            logger.info(
                f"URL change detected for source {source_id}: "
                f"{old_feed_url} -> {new_feed_url}"
            )

    if update.name is not None:
        source.name = update.name
    if update.tier is not None:
        source.tier = validate_tier(update.tier)
    if update.score is not None:
        source.score = update.score
    if update.status is not None:
        source.status = validate_status(update.status)
    if update.config is not None:
        source.config = update.config

    db.commit()
    db.refresh(source)

    logger.info(f"Updated source: {source_id}")

    # Trigger ingestion if URL changed
    warnings: list[str] = []
    if url_changed:
        try:
            job = Job(
                job_id=f"job_{secrets.token_hex(8)}",
                type=JobType.INGEST,
                status=JobStatus.PENDING,
                source_id=source.source_id,
                trigger=JobTrigger.URL_UPDATE,
            )
            db.add(job)
            db.commit()

            ingest_source.send(source.source_id, job_id=job.job_id)
            logger.info(
                f"Triggered ingestion for source {source_id} due to URL change, "
                f"job: {job.job_id}"
            )
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to trigger ingestion: {e}", exc_info=True)
            warnings.append("源已更新，但采集任务触发失败，请手动检查")

    return build_source_response(source, warnings if warnings else None)
```

- [ ] **Step 2: 运行测试确认无破坏性变更**

Run: `uv run pytest tests/test_api/ -v -k source`
Expected: 所有测试通过

- [ ] **Step 3: 提交变更**

```bash
git add src/cyberpulse/api/routers/admin/sources.py
git commit -m "feat(api): auto-trigger ingestion when source URL changes"
```

---

### Task 3: 添加集成测试

**Files:**
- Modify: `tests/test_api/test_admin_sources.py`

- [ ] **Step 1: 添加 URL 变更触发采集的测试**

```python
def test_update_source_url_triggers_ingestion(client, db_session):
    """Test that updating source URL triggers ingestion job."""
    from unittest.mock import MagicMock, patch

    from cyberpulse.api.auth import get_current_client
    from cyberpulse.api.dependencies import get_db
    from cyberpulse.models import ApiClient, ApiClientStatus, Job, JobTrigger, Source

    # Create mock client
    mock_client = MagicMock(spec=ApiClient)
    mock_client.permissions = ["admin"]
    mock_client.status = ApiClientStatus.ACTIVE

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_client] = lambda: mock_client

    # Create source
    source = Source(
        source_id="src_test001",
        name="Test Source",
        connector_type="rss",
        config={"feed_url": "https://old.example.com/feed"},
    )
    db_session.add(source)
    db_session.commit()

    # Update URL
    response = client.put(
        "/api/v1/admin/sources/src_test001",
        json={"config": {"feed_url": "https://new.example.com/feed"}},
    )
    assert response.status_code == 200

    # Verify job was created with URL_UPDATE trigger
    job = db_session.query(Job).filter(
        Job.source_id == "src_test001",
        Job.trigger == JobTrigger.URL_UPDATE
    ).first()
    assert job is not None

    app.dependency_overrides.clear()


def test_update_source_same_url_no_job(client, db_session):
    """Test that updating with same URL does not trigger job."""
    from unittest.mock import MagicMock

    from cyberpulse.api.auth import get_current_client
    from cyberpulse.api.dependencies import get_db
    from cyberpulse.models import ApiClient, ApiClientStatus, Job, JobTrigger, Source

    # Create mock client
    mock_client = MagicMock(spec=ApiClient)
    mock_client.permissions = ["admin"]
    mock_client.status = ApiClientStatus.ACTIVE

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_client] = lambda: mock_client

    # Create source
    source = Source(
        source_id="src_test002",
        name="Test Source 2",
        connector_type="rss",
        config={"feed_url": "https://example.com/feed"},
    )
    db_session.add(source)
    db_session.commit()

    # Update with same URL
    response = client.put(
        "/api/v1/admin/sources/src_test002",
        json={"config": {"feed_url": "https://example.com/feed"}},
    )
    assert response.status_code == 200

    # Verify no job was created
    job = db_session.query(Job).filter(
        Job.source_id == "src_test002",
        Job.trigger == JobTrigger.URL_UPDATE
    ).first()
    assert job is None

    app.dependency_overrides.clear()
```

- [ ] **Step 2: 运行测试**

Run: `uv run pytest tests/test_api/test_admin_sources.py -v`
Expected: 所有测试通过

- [ ] **Step 3: 提交测试**

```bash
git add tests/test_api/test_admin_sources.py
git commit -m "test(api): add tests for URL change auto-trigger"
```

---

### Task 4: 创建 PR

- [ ] **Step 1: 推送分支**

```bash
git push origin feat/url-update-trigger
```

- [ ] **Step 2: 创建 PR**

---

## Self-Review

**1. Spec Coverage:**
- ✅ JobTrigger 枚举添加 URL_UPDATE
- ✅ update_source 检测 URL 变更
- ✅ URL 变更触发采集任务
- ✅ 测试覆盖

**2. Edge Cases:**
- ✅ URL 相同时不触发
- ✅ 触发失败时返回警告
- ✅ 日志记录变更