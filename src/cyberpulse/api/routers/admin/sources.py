"""Source management API router for admin endpoints."""

import logging
import re
import secrets
import time
from datetime import UTC, datetime, timedelta
from xml.sax.saxutils import escape

import feedparser
import httpx
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ....models import (
    Job,
    JobStatus,
    JobType,
    Settings,
    Source,
    SourceStatus,
    SourceTier,
)
from ...auth import ApiClient, require_permissions
from ...dependencies import get_db
from ...schemas.source import (
    DefaultsResponse,
    DefaultsUpdate,
    ImportResponse,
    ScheduleRequest,
    ScheduleResponse,
    SourceCreate,
    SourceListResponse,
    SourceResponse,
    SourceUpdate,
    TestResult,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# source_id format: src_{8 hex chars}
SOURCE_ID_PATTERN = re.compile(r"^src_[a-f0-9]{8}$")


def validate_source_id(source_id: str) -> None:
    """Validate source_id format."""
    if not SOURCE_ID_PATTERN.match(source_id):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source_id format: {source_id}. Expected format: src_xxxxxxxx"
        )


def validate_tier(tier: str) -> SourceTier:
    """Validate and convert tier string to enum."""
    try:
        return SourceTier(tier.upper())
    except ValueError:
        valid_tiers = [t.value for t in SourceTier]
        raise HTTPException(
            status_code=422,
            detail=f"Invalid tier '{tier}'. Must be one of: {valid_tiers}"
        )


def validate_status(status: str) -> SourceStatus:
    """Validate and convert status string to enum."""
    try:
        return SourceStatus(status.upper())
    except ValueError:
        valid_statuses = [s.value for s in SourceStatus]
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{status}'. Must be one of: {valid_statuses}"
        )


def build_source_response(source: Source) -> SourceResponse:
    """Build SourceResponse from Source model."""
    warnings = []
    if source.consecutive_failures >= 3:
        warnings.append(f"连续失败 {source.consecutive_failures} 次")
    if source.status == SourceStatus.FROZEN:
        warnings.append("源已冻结")

    return SourceResponse(
        source_id=source.source_id,
        name=source.name,
        connector_type=source.connector_type or "rss",
        tier=source.tier.value if source.tier else "T2",
        score=source.score or 50.0,
        status=source.status.value if source.status else "ACTIVE",
        is_in_observation=source.is_in_observation or False,
        observation_until=source.observation_until,
        pending_review=source.pending_review or False,
        review_reason=source.review_reason,
        fetch_interval=source.fetch_interval,
        config=source.config or {},
        last_fetched_at=source.last_fetched_at,
        last_scored_at=source.last_scored_at,
        total_items=source.total_items or 0,
        total_contents=source.total_contents or 0,
        schedule_interval=source.schedule_interval,
        next_ingest_at=source.next_ingest_at,
        last_ingested_at=source.last_ingested_at,
        last_ingest_result=source.last_ingest_result,
        items_last_7d=source.items_last_7d or 0,
        consecutive_failures=source.consecutive_failures or 0,
        last_error_at=source.last_error_at,
        last_error_message=source.last_error_message,
        last_job_id=source.last_job_id,
        needs_full_fetch=source.needs_full_fetch or False,
        full_fetch_threshold=source.full_fetch_threshold,
        content_type=source.content_type,
        avg_content_length=source.avg_content_length,
        quality_score=source.quality_score,
        full_fetch_success_count=source.full_fetch_success_count or 0,
        full_fetch_failure_count=source.full_fetch_failure_count or 0,
        warnings=warnings,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


@router.get("/sources", response_model=SourceListResponse)
async def list_sources(
    status: str | None = Query(None, description="Filter by status: ACTIVE, FROZEN, REMOVED"),
    tier: str | None = Query(None, description="Filter by tier: T0, T1, T2, T3"),
    scheduled: bool | None = Query(None, description="Filter by scheduled status"),
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> SourceListResponse:
    """List all sources with optional filtering."""
    logger.debug(f"Listing sources: status={status}, tier={tier}, scheduled={scheduled}")

    query = db.query(Source)

    if status:
        status_enum = validate_status(status)
        query = query.filter(Source.status == status_enum)

    if tier:
        tier_enum = validate_tier(tier)
        query = query.filter(Source.tier == tier_enum)

    if scheduled is not None:
        if scheduled:
            query = query.filter(Source.schedule_interval.isnot(None))
        else:
            query = query.filter(Source.schedule_interval.is_(None))

    sources = query.order_by(desc(Source.created_at)).all()

    return SourceListResponse(
        data=[build_source_response(s) for s in sources],
        count=len(sources),
        offset=0,
        limit=len(sources),
        server_timestamp=datetime.now(UTC),
    )


@router.post("/sources", response_model=SourceResponse, status_code=201)
async def create_source(
    source: SourceCreate,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> SourceResponse:
    """Add a new source."""
    logger.info(f"Creating source: name={source.name}, connector_type={source.connector_type}")

    # Check for duplicate name
    existing = db.query(Source).filter(Source.name == source.name).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Source with name '{source.name}' already exists"
        )

    # Create source
    tier_enum = validate_tier(source.tier) if source.tier else SourceTier.T2
    score = source.score if source.score is not None else (90 if tier_enum == SourceTier.T0 else 70 if tier_enum == SourceTier.T1 else 50)

    new_source = Source(
        source_id=f"src_{secrets.token_hex(4)}",
        name=source.name,
        connector_type=source.connector_type,
        tier=tier_enum,
        score=score,
        status=SourceStatus.ACTIVE,
        config=source.config or {},
        fetch_interval=source.fetch_interval,
    )

    db.add(new_source)
    db.commit()
    db.refresh(new_source)

    logger.info(f"Created source: {new_source.source_id}")

    return build_source_response(new_source)


# ============ 静态路径端点（必须在动态路径之前）============


@router.get("/sources/defaults", response_model=DefaultsResponse)
async def get_defaults(
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> DefaultsResponse:
    """获取源默认配置。"""
    setting = db.query(Settings).filter(Settings.key == "default_fetch_interval").first()

    return DefaultsResponse(
        default_fetch_interval=int(setting.value) if setting else 3600,
        updated_at=setting.updated_at if setting else None,
    )


@router.patch("/sources/defaults", response_model=DefaultsResponse)
async def update_defaults(
    update: DefaultsUpdate,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> DefaultsResponse:
    """更新源默认配置。"""
    setting = db.query(Settings).filter(Settings.key == "default_fetch_interval").first()

    if setting:
        setting.value = str(update.default_fetch_interval)
    else:
        setting = Settings(
            key="default_fetch_interval",
            value=str(update.default_fetch_interval)
        )
        db.add(setting)

    db.commit()
    db.refresh(setting)

    logger.info(f"Updated default_fetch_interval to {update.default_fetch_interval}")

    return DefaultsResponse(
        default_fetch_interval=update.default_fetch_interval,
        updated_at=setting.updated_at,
    )


@router.post("/sources/import", response_model=ImportResponse)
async def import_sources(
    file: UploadFile = File(..., description="OPML 文件"),
    force: bool = Form(False, description="跳过质量验证"),
    skip_invalid: bool = Form(True, description="跳过无效源继续导入"),
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> ImportResponse:
    """批量导入源。从 OPML 文件批量导入 RSS 源。"""
    import xml.etree.ElementTree as ET

    # Read file content
    content = await file.read()

    # Parse OPML
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid OPML file: {str(e)}"
        )

    # Extract feed URLs
    feeds = []
    for outline in root.iter("outline"):
        xml_url = outline.get("xmlUrl")
        if xml_url:
            feeds.append({
                "url": xml_url,
                "title": outline.get("title", xml_url),
            })

    if not feeds:
        raise HTTPException(
            status_code=400,
            detail="No RSS feeds found in OPML file"
        )

    # Create import job
    job = Job(
        job_id=f"job_{secrets.token_hex(8)}",
        type=JobType.IMPORT,
        status=JobStatus.PENDING,
        file_name=file.filename,
        result={
            "total": len(feeds),
            "feeds": feeds,
            "force": force,
            "skip_invalid": skip_invalid,
        },
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    logger.info(f"Created import job {job.job_id} with {len(feeds)} feeds")

    return ImportResponse(
        job_id=job.job_id,
        status="pending",
        message=f"Import job created with {len(feeds)} feeds. Check status at /api/v1/admin/jobs/{job.job_id}",
    )


@router.get("/sources/export")
async def export_sources(
    status: str | None = Query(None, description="Filter by status: ACTIVE, FROZEN, REMOVED"),
    tier: str | None = Query(None, description="Filter by tier: T0, T1, T2, T3"),
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> Response:
    """导出源为 OPML 格式。"""
    query = db.query(Source)

    if status:
        status_enum = validate_status(status)
        query = query.filter(Source.status == status_enum)

    if tier:
        tier_enum = validate_tier(tier)
        query = query.filter(Source.tier == tier_enum)

    sources = query.filter(Source.status != SourceStatus.REMOVED).all()

    # Build OPML content with proper XML escaping
    opml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<opml version="2.0">',
        '  <head>',
        '    <title>CyberPulse Sources Export</title>',
        f'    <dateCreated>{escape(datetime.now(UTC).isoformat())}</dateCreated>',
        '  </head>',
        '  <body>',
    ]

    for source in sources:
        feed_url = source.config.get("feed_url", "") if source.config else ""
        if feed_url:
            safe_name = escape(source.name)
            safe_url = escape(feed_url)
            html_url = feed_url.rsplit("/", 1)[0] if "/" in feed_url else ""
            safe_html_url = escape(html_url)

            opml_lines.append(
                f'    <outline type="rss" '
                f'title="{safe_name}" '
                f'text="{safe_name}" '
                f'xmlUrl="{safe_url}" '
                f'htmlUrl="{safe_html_url}"/>'
            )

    opml_lines.extend([
        '  </body>',
        '</opml>',
    ])

    opml_content = "\n".join(opml_lines)

    logger.info(f"Exported {len(sources)} sources to OPML")

    return Response(
        content=opml_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename=cyberpulse-sources-{datetime.now().strftime('%Y%m%d')}.opml"
        }
    )


# ============ 动态路径端点（必须在静态路径之后）============


@router.get("/sources/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: str,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> SourceResponse:
    """Get source details."""
    validate_source_id(source_id)

    source = db.query(Source).filter(Source.source_id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")

    return build_source_response(source)


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

    if update.name is not None:
        source.name = update.name
    if update.tier is not None:
        source.tier = validate_tier(update.tier)
    if update.score is not None:
        source.score = update.score
    if update.status is not None:
        source.status = validate_status(update.status)
    if update.fetch_interval is not None:
        source.fetch_interval = update.fetch_interval
    if update.config is not None:
        source.config = update.config

    db.commit()
    db.refresh(source)

    logger.info(f"Updated source: {source_id}")

    return build_source_response(source)


@router.delete("/sources/{source_id}", status_code=200)
async def delete_source(
    source_id: str,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> dict:
    """Delete a source (soft delete by setting status to REMOVED)."""
    validate_source_id(source_id)

    source = db.query(Source).filter(Source.source_id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")

    source.status = SourceStatus.REMOVED
    db.commit()

    logger.info(f"Deleted source: {source_id}")

    return {"message": f"Source {source_id} deleted"}


@router.post("/sources/{source_id}/test", response_model=TestResult)
async def test_source(
    source_id: str,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> TestResult:
    """测试源连接性。"""
    validate_source_id(source_id)

    source = db.query(Source).filter(Source.source_id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")

    feed_url = source.config.get("feed_url") if source.config else None
    if not feed_url:
        return TestResult(
            source_id=source_id,
            test_result="failed",
            error_type="config",
            error_message="No feed URL configured",
            suggestion="Configure feed_url in source config",
        )

    try:
        start_time = time.time()
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(
                feed_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; CyberPulse/1.0)"},
            )
            response.raise_for_status()
            content = response.content

        elapsed_ms = int((time.time() - start_time) * 1000)
        feed = feedparser.parse(content)
        items_found = len(feed.get("entries", []))

        warnings = []
        if feed.get("bozo"):
            warnings.append("RSS feed has format issues")

        return TestResult(
            source_id=source_id,
            test_result="success",
            response_time_ms=elapsed_ms,
            items_found=items_found,
            last_modified=None,
            warnings=warnings,
        )

    except httpx.TimeoutException:
        return TestResult(
            source_id=source_id,
            test_result="failed",
            error_type="timeout",
            error_message="Connection timeout after 30s",
            suggestion="检查网络连接或增加超时时间",
        )
    except httpx.HTTPStatusError as e:
        error_type = f"http_{e.response.status_code}"
        suggestion_map = {
            403: "检查网站反爬策略，可能需要添加 User-Agent 或 IP 白名单",
            404: "RSS 地址已失效，尝试自动发现新地址",
            429: "降低采集频率，添加请求间隔",
        }
        return TestResult(
            source_id=source_id,
            test_result="failed",
            error_type=error_type,
            error_message=f"HTTP {e.response.status_code}: {e.response.reason_phrase}",
            suggestion=suggestion_map.get(e.response.status_code, "检查网站访问权限"),
        )
    except Exception as e:
        return TestResult(
            source_id=source_id,
            test_result="failed",
            error_type="connection",
            error_message=str(e),
            suggestion="检查 URL 是否正确，确认网络连接",
        )


@router.post("/sources/{source_id}/schedule", response_model=ScheduleResponse)
async def set_schedule(
    source_id: str,
    request: ScheduleRequest,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> ScheduleResponse:
    """设置源采集调度。"""
    validate_source_id(source_id)

    source = db.query(Source).filter(Source.source_id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")

    source.schedule_interval = request.interval
    source.next_ingest_at = datetime.now(UTC) + timedelta(seconds=request.interval)

    db.commit()
    db.refresh(source)

    logger.info(f"Set schedule for source {source_id}: interval={request.interval}s")

    return ScheduleResponse(
        source_id=source_id,
        schedule_interval=request.interval,
        next_ingest_at=source.next_ingest_at,
        message="Schedule updated",
    )


@router.delete("/sources/{source_id}/schedule")
async def remove_schedule(
    source_id: str,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> dict:
    """取消源采集调度。"""
    validate_source_id(source_id)

    source = db.query(Source).filter(Source.source_id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")

    source.schedule_interval = None
    source.next_ingest_at = None

    db.commit()

    logger.info(f"Removed schedule for source {source_id}")

    return {
        "source_id": source_id,
        "schedule_interval": None,
        "next_ingest_at": None,
        "message": "Schedule removed"
    }
