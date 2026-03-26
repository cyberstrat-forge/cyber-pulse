"""Log management API router for admin endpoints.

Provides access to system logs for troubleshooting.

Logs are read from the application log file, not stored in database.
"""

import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ....config import settings
from ....models import Source
from ...auth import ApiClient, require_permissions
from ...dependencies import get_db
from ...schemas.log import LogEntry, LogListResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# Error types we track
ERROR_TYPES = {
    "connection": r"connection|timeout|network",
    "http_403": r"HTTP 403|Forbidden",
    "http_404": r"HTTP 404|Not Found",
    "http_429": r"HTTP 429|Too Many Requests|rate limit",
    "http_5xx": r"HTTP 5\d{2}",
    "parse_error": r"parse|XML|malformed",
    "ssl_error": r"SSL|certificate|TLS",
}


def classify_error(message: str) -> str | None:
    """Classify error message into error type."""
    message_lower = message.lower()
    for error_type, pattern in ERROR_TYPES.items():
        if re.search(pattern, message_lower, re.IGNORECASE):
            return error_type
    return None


def parse_log_line(line: str) -> dict | None:
    """Parse a log line into structured data.

    Expected format: YYYY-MM-DD HH:MM:SS - module - LEVEL - message
    """
    # Match standard log format
    match = re.match(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - ([\w.]+) - (\w+) - (.+)",
        line.strip()
    )
    if not match:
        return None

    timestamp_str, module, level, message = match.groups()

    # Parse timestamp
    try:
        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        timestamp = timestamp.replace(tzinfo=UTC)
    except ValueError:
        return None

    return {
        "timestamp": timestamp,
        "module": module,
        "level": level,
        "message": message,
    }


def extract_source_id(message: str) -> str | None:
    """Extract source_id from log message if present."""
    match = re.search(r"src_[a-f0-9]{8}", message)
    return match.group(0) if match else None


def _get_suggestion(error_type: str) -> str:
    """Get troubleshooting suggestion for error type."""
    suggestions = {
        "connection": "检查网络连接或源服务器状态",
        "http_403": "检查网站反爬策略，可能需要更换 User-Agent",
        "http_404": "RSS 地址可能已更改，尝试重新发现",
        "http_429": "请求频率过高，增加采集间隔",
        "http_5xx": "源服务器错误，稍后重试",
        "parse_error": "RSS 格式异常，检查源内容",
        "ssl_error": "SSL 证书问题，检查证书有效性",
    }
    return suggestions.get(error_type, "检查源配置和网络连接")


@router.get("/logs", response_model=LogListResponse)
async def list_logs(
    level: str = Query("error", description="Log level: error, warning, info"),
    source_id: str | None = Query(None, description="Filter by source ID"),
    since: str | None = Query(None, description="Time range: 1h, 24h, 7d, or ISO datetime"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> LogListResponse:
    """
    Query system logs for troubleshooting.

    Logs are read from the application log file.
    By default, returns error logs from the last 24 hours.
    """
    logger.debug(f"Listing logs: level={level}, source_id={source_id}, since={since}")

    # Validate level
    level = level.upper()
    if level not in ["ERROR", "WARNING", "INFO"]:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid level '{level}'. Must be one of: error, warning, info"
        )

    # Parse since parameter
    since_datetime = None
    if since:
        if since == "1h":
            since_datetime = datetime.now(UTC) - timedelta(hours=1)
        elif since == "24h":
            since_datetime = datetime.now(UTC) - timedelta(hours=24)
        elif since == "7d":
            since_datetime = datetime.now(UTC) - timedelta(days=7)
        else:
            try:
                since_datetime = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid since format: {since}. Use 1h, 24h, 7d, or ISO datetime"
                )
    else:
        # Default to last 24 hours
        since_datetime = datetime.now(UTC) - timedelta(hours=24)

    # Read log file
    log_file = settings.log_file
    if not log_file or not Path(log_file).exists():
        return LogListResponse(
            data=[],
            count=0,
            server_timestamp=datetime.now(UTC),
        )

    entries = []
    try:
        with open(log_file, encoding="utf-8") as f:
            # Read from end of file for efficiency
            lines = f.readlines()[-5000:]  # Read last 5000 lines

        # Build source name lookup
        sources = db.query(Source).all()
        source_map = {s.source_id: s.name for s in sources}

        for line in lines:
            parsed = parse_log_line(line)
            if not parsed:
                continue

            # Filter by level
            if level == "ERROR" and parsed["level"] != "ERROR":
                continue
            elif level == "WARNING" and parsed["level"] not in ["ERROR", "WARNING"]:
                continue

            # Filter by timestamp
            if parsed["timestamp"] < since_datetime:
                continue

            # Extract source info
            msg_source_id = extract_source_id(parsed["message"])
            if source_id and msg_source_id != source_id:
                continue

            # Classify error
            error_type = None
            if parsed["level"] == "ERROR":
                error_type = classify_error(parsed["message"])

            entries.append(LogEntry(
                timestamp=parsed["timestamp"],
                level=parsed["level"],
                module=parsed["module"],
                source_id=msg_source_id,
                source_name=source_map.get(msg_source_id),
                error_type=error_type,
                message=parsed["message"],
                retry_count=0,  # Not tracked in current log format
                suggestion=_get_suggestion(error_type) if error_type else None,
            ))

    except Exception as e:
        logger.error(f"Failed to read log file: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read log file: {str(e)}"
        )

    # Sort by timestamp (newest first) and limit
    entries.sort(key=lambda x: x.timestamp, reverse=True)
    entries = entries[:limit]

    return LogListResponse(
        data=entries,
        count=len(entries),
        server_timestamp=datetime.now(UTC),
    )
