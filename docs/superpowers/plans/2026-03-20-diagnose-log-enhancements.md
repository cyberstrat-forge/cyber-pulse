# Issues #15 #16 处置计划：诊断与日志命令增强

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增强 CLI 诊断和日志命令，支持服务状态检查、错误详情展示、日志导出和结构化输出。

**Architecture:** 在现有 CLI 命令基础上扩展功能，复用现有服务层和工具函数。诊断增强主要修改 `diagnose.py`，日志增强主要修改 `log.py`。

**Tech Stack:** Python 3.11+ | Typer | Rich | Redis | Dramatiq

---

## Issues 分析结论

### Issue #15 分析

| 改进项 | 优先级 | 合理性 | 说明 |
|--------|--------|--------|------|
| 服务状态检查 | P0 | ⚠️ 部分合理 | 现有 `diagnose system` 未检查 API；Worker/Scheduler 进程状态检查需心跳机制，暂不实现 |
| 拒绝原因详情 | P0 | ⚠️ 部分合理 | `rejection_reason` 已存储在 `raw_metadata` 中，仅需修改 CLI 展示 |
| 任务队列状态 | P1 | ✅ 合理 | Dramatiq 队列监控有价值 |
| 采集历史记录 | P1 | ✅ 合理 | 需要追踪采集问题 |

### Issue #16 分析

| 改进项 | 优先级 | 合理性 | 说明 |
|--------|--------|--------|------|
| Docker 日志访问 | - | ❌ 已解决 | `docker-compose.yml` 已挂载 `./logs:/app/logs` |
| 日志导出 | P0 | ✅ 合理 | 方便分享和归档 |
| JSON 格式输出 | P0 | ✅ 合理 | 程序化处理需求 |
| 日志清理 | P1 | ✅ 合理 | 防止日志无限增长 |

### 发现的问题

1. **Issue #16 对 Docker 日志访问的评估不准确** - `docker-compose.yml` 第 46 行已挂载日志目录，宿主机可直接访问。

2. **Issue #15 对 rejection_reason 的理解有偏差** - 该字段存储在 `item.raw_metadata["rejection_reason"]` 中，CLI 只需提取展示。

3. **Issue #15 对 Worker/Scheduler 进程状态检查的需求** - 检查进程是否运行需要心跳机制或进程监控，当前架构不支持。本计划仅实现 API 健康检查和队列深度检查。

---

## 文件结构

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/cyberpulse/cli/commands/diagnose.py` | 修改 | 增强诊断命令 |
| `src/cyberpulse/cli/commands/log.py` | 修改 | 增强日志命令 |
| `tests/test_cli/test_diagnose_commands.py` | 修改 | 诊断命令测试 |
| `tests/test_cli/test_log_commands.py` | 修改 | 日志命令测试 |

---

## Task 1: 增强 `diagnose errors` 显示拒绝原因

**Files:**
- Modify: `src/cyberpulse/cli/commands/diagnose.py:280-294`
- Test: `tests/test_cli/test_diagnose_commands.py`

- [ ] **Step 1: 编写失败的测试**

```python
# tests/test_cli/test_diagnose_commands.py

class TestDiagnoseErrorsWithReason:
    """Tests for diagnose errors with rejection reason."""

    def test_diagnose_errors_shows_rejection_reason(self) -> None:
        """Test errors diagnosis shows rejection reason from raw_metadata."""
        from datetime import datetime, timezone
        from cyberpulse.models import Item

        mock_item = MagicMock(spec=Item)
        mock_item.item_id = 'item_abc123'
        mock_item.source_id = 'src_xyz'
        mock_item.title = 'Test Item Title'
        mock_item.fetched_at = datetime.now(timezone.utc)
        mock_item.raw_metadata = {
            'rejection_reason': 'Title too short; Empty body',
            'quality_warnings': ['Missing author']
        }

        with patch('cyberpulse.cli.commands.diagnose.SessionLocal') as mock_db, \
             patch('cyberpulse.cli.commands.diagnose.settings') as mock_settings:
            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.all.return_value = [mock_item]
            mock_query.count.return_value = 1
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_session.query.return_value = mock_query
            mock_db.return_value = mock_session
            mock_settings.log_file = None

            result = runner.invoke(app, ['errors'])
            assert result.exit_code == 0
            assert 'Title too short' in result.stdout
            assert 'Empty body' in result.stdout
```

- [ ] **Step 2: 运行测试验证失败**

Run: `.venv/bin/pytest tests/test_cli/test_diagnose_commands.py::TestDiagnoseErrorsWithReason::test_diagnose_errors_shows_rejection_reason -v`
Expected: FAIL (rejection reason not displayed)

- [ ] **Step 3: 实现拒绝原因展示**

修改 `diagnose_errors` 函数中 Rejected Items 表格，添加 Reason 列：

```python
# src/cyberpulse/cli/commands/diagnose.py
# 在 diagnose_errors 函数中，修改表格显示部分

# 找到以下代码块（约第 280-294 行）：
        if rejected_items:
            console.print(f"  Found {query.count()} rejected items")

            table = Table(show_header=True, header_style="bold")
            table.add_column("Item ID", style="dim")
            table.add_column("Source")
            table.add_column("Title")
            table.add_column("Fetched")

            for item in rejected_items[:10]:
                table.add_row(
                    item.item_id,
                    item.source_id,
                    (item.title or "")[:40],
                    item.fetched_at.strftime("%Y-%m-%d %H:%M") if item.fetched_at else "-"
                )

# 替换为：
        if rejected_items:
            console.print(f"  Found {query.count()} rejected items")

            table = Table(show_header=True, header_style="bold")
            table.add_column("Item ID", style="dim")
            table.add_column("Source")
            table.add_column("Title")
            table.add_column("Rejection Reason")
            table.add_column("Fetched")

            for item in rejected_items[:10]:
                # Extract rejection reason from raw_metadata
                raw_meta = item.raw_metadata or {}
                reason = raw_meta.get("rejection_reason", "-")
                if len(reason) > 40:
                    reason = reason[:37] + "..."

                table.add_row(
                    item.item_id,
                    item.source_id,
                    (item.title or "")[:30],
                    reason,
                    item.fetched_at.strftime("%Y-%m-%d %H:%M") if item.fetched_at else "-"
                )
```

- [ ] **Step 4: 运行测试验证通过**

Run: `.venv/bin/pytest tests/test_cli/test_diagnose_commands.py::TestDiagnoseErrorsWithReason::test_diagnose_errors_shows_rejection_reason -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/cyberpulse/cli/commands/diagnose.py tests/test_cli/test_diagnose_commands.py
git commit -m "feat(diagnose): show rejection reason in errors command"
```

---

## Task 2: 增强 `diagnose system` 检查服务状态

**Files:**
- Modify: `src/cyberpulse/cli/commands/diagnose.py:24-96`
- Test: `tests/test_cli/test_diagnose_commands.py`

- [ ] **Step 1: 编写失败的测试**

```python
# tests/test_cli/test_diagnose_commands.py

class TestDiagnoseSystemServices:
    """Tests for diagnose system service status checks."""

    def test_diagnose_system_shows_api_status(self) -> None:
        """Test system diagnosis shows API service status."""
        with patch('cyberpulse.cli.commands.diagnose.SessionLocal') as mock_db, \
             patch('cyberpulse.cli.commands.diagnose.settings') as mock_settings:
            mock_session = MagicMock()
            mock_session.execute.return_value = None
            mock_db.return_value = mock_session
            mock_settings.database_url = 'postgresql://localhost/db'
            mock_settings.redis_url = 'redis://localhost:6379/0'
            mock_settings.dramatiq_broker_url = 'redis://localhost:6379/1'
            mock_settings.log_level = 'INFO'
            mock_settings.log_file = None
            mock_settings.scheduler_enabled = True
            mock_settings.api_host = '0.0.0.0'
            mock_settings.api_port = 8000

            mock_redis = MagicMock()
            mock_redis.ping.return_value = None

            with patch.dict('sys.modules', {'redis': MagicMock(from_url=MagicMock(return_value=mock_redis))}), \
                 patch('urllib.request.urlopen') as mock_urlopen:
                mock_urlopen.return_value.__enter__ = MagicMock()
                mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
                mock_urlopen.return_value.read.return_value = b'{"status":"ok"}'

                result = runner.invoke(app, ['system'])
                assert result.exit_code == 0
                assert 'API' in result.stdout
```

- [ ] **Step 2: 运行测试验证失败**

Run: `.venv/bin/pytest tests/test_cli/test_diagnose_commands.py::TestDiagnoseSystemServices::test_diagnose_system_shows_api_status -v`
Expected: FAIL (API status check not implemented)

- [ ] **Step 3: 实现服务状态检查**

在 `diagnose_system` 函数的 Configuration 检查之后，Summary 之前添加服务状态检查：

```python
# src/cyberpulse/cli/commands/diagnose.py
# 在文件顶部添加 import
import urllib.request
import json

# 在 diagnose_system 函数中，Configuration 检查后添加：

    # Check API service
    console.print("\n[bold]API Service:[/bold]")
    try:
        url = f"http://{settings.api_host}:{settings.api_port}/health"
        # Handle 0.0.0.0 binding
        if '0.0.0.0' in url:
            url = url.replace('0.0.0.0', '127.0.0.1')

        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            if data.get('status') == 'healthy':
                console.print("  [green]✓[/green] API service: [green]healthy[/green]")
                console.print(f"  [dim]URL: {url}[/dim]")
            else:
                console.print(f"  [yellow]![/yellow] API service: [yellow]degraded[/yellow]")
                console.print(f"  [dim]Status: {data.get('status')}[/dim]")
    except urllib.error.URLError as e:
        console.print("  [yellow]![/yellow] API service: [yellow]not reachable[/yellow]")
        console.print(f"  [dim]This is normal if API is not running locally[/dim]")
    except Exception as e:
        console.print("  [yellow]![/yellow] API service: [yellow]not reachable[/yellow]")
        console.print(f"  [dim]{str(e)[:50]}[/dim]")

    # Check Dramatiq queue status
    console.print("\n[bold]Task Queue:[/bold]")
    try:
        import redis
        r = redis.from_url(settings.dramatiq_broker_url)
        # Check for pending messages in default queue
        queue_len = r.llen("dramatiq:default")  # type: ignore[attr-defined]
        console.print(f"  [green]✓[/green] Dramatiq Redis: [green]connected[/green]")
        console.print(f"  [dim]Pending tasks in default queue: {queue_len}[/dim]")
    except Exception as e:
        console.print("  [yellow]![/yellow] Could not check queue status")
```

- [ ] **Step 4: 运行测试验证通过**

Run: `.venv/bin/pytest tests/test_cli/test_diagnose_commands.py::TestDiagnoseSystemServices::test_diagnose_system_shows_api_status -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/cyberpulse/cli/commands/diagnose.py tests/test_cli/test_diagnose_commands.py
git commit -m "feat(diagnose): add API and queue status to system command"
```

---

## Task 2.5: 增强 `diagnose sources` 显示采集历史

**Files:**
- Modify: `src/cyberpulse/cli/commands/diagnose.py:98-234`
- Test: `tests/test_cli/test_diagnose_commands.py`

- [ ] **Step 1: 编写失败的测试**

```python
# tests/test_cli/test_diagnose_commands.py

class TestDiagnoseSourcesCollection:
    """Tests for diagnose sources collection history."""

    def test_diagnose_sources_shows_collection_time(self) -> None:
        """Test sources diagnosis shows last collection time."""
        from datetime import datetime, timezone, timedelta
        from cyberpulse.models import Source, SourceTier, SourceStatus

        mock_source = MagicMock(spec=Source)
        mock_source.source_id = 'src_abc123'
        mock_source.name = 'Test Source'
        mock_source.tier = SourceTier.T1
        mock_source.score = 70.0
        mock_source.status = SourceStatus.ACTIVE
        mock_source.is_in_observation = False
        mock_source.observation_until = None
        mock_source.pending_review = False
        mock_source.review_reason = None
        mock_source.last_fetched_at = datetime.now(timezone.utc) - timedelta(hours=1)
        mock_source.total_items = 100
        mock_source.fetch_interval = 3600

        with patch('cyberpulse.cli.commands.diagnose.SessionLocal') as mock_db:
            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.all.return_value = [mock_source]
            mock_query.filter.return_value = mock_query
            mock_session.query.return_value = mock_query
            mock_db.return_value = mock_session

            result = runner.invoke(app, ['sources'])
            assert result.exit_code == 0
            assert 'Last Collection' in result.stdout
```

- [ ] **Step 2: 运行测试验证失败**

Run: `.venv/bin/pytest tests/test_cli/test_diagnose_commands.py::TestDiagnoseSourcesCollection::test_diagnose_sources_shows_collection_time -v`
Expected: FAIL (collection time not displayed)

- [ ] **Step 3: 实现采集历史展示**

在 `diagnose_sources` 函数中，Summary 统计后添加采集历史表格：

```python
# src/cyberpulse/cli/commands/diagnose.py
# 在 diagnose_sources 函数中，Summary 部分后添加：

        # Recent collection activity
        active_sources = [
            s for s in sources
            if s.status == SourceStatus.ACTIVE
        ]

        if active_sources:
            console.print(f"\n[bold]Recent Collection Activity:[/bold]")
            collection_table = Table(show_header=True, header_style="bold")
            collection_table.add_column("Source")
            collection_table.add_column("Last Collected")
            collection_table.add_column("Items")
            collection_table.add_column("Status")

            # Sort by last_fetched_at, most recent first
            sorted_sources = sorted(
                active_sources,
                key=lambda x: x.last_fetched_at or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True
            )

            now = datetime.now(timezone.utc)
            for s in sorted_sources[:15]:  # Show top 15
                if s.last_fetched_at:
                    age = now - s.last_fetched_at
                    if age < timedelta(hours=1):
                        status = "[green]Fresh[/green]"
                    elif age < timedelta(hours=24):
                        status = "[yellow]Recent[/yellow]"
                    else:
                        status = "[red]Stale[/red]"
                    collected = s.last_fetched_at.strftime("%Y-%m-%d %H:%M")
                else:
                    status = "[dim]Never[/dim]"
                    collected = "-"

                collection_table.add_row(
                    s.name[:25],
                    collected,
                    str(s.total_items or 0),
                    status
                )

            console.print(collection_table)
```

- [ ] **Step 4: 运行测试验证通过**

Run: `.venv/bin/pytest tests/test_cli/test_diagnose_commands.py::TestDiagnoseSourcesCollection::test_diagnose_sources_shows_collection_time -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/cyberpulse/cli/commands/diagnose.py tests/test_cli/test_diagnose_commands.py
git commit -m "feat(diagnose): add collection history to sources command"
```

---

## Task 3: 添加 `log export` 命令

**Files:**
- Modify: `src/cyberpulse/cli/commands/log.py`
- Test: `tests/test_cli/test_log_commands.py`

- [ ] **Step 1: 编写失败的测试**

```python
# tests/test_cli/test_log_commands.py

class TestLogExport:
    """Tests for log export command."""

    def test_log_export_creates_file(self) -> None:
        """Test log export creates output file."""
        import tempfile
        import os

        # Create a temp log file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write('2024-01-15 10:30:00,123 - test - INFO - Test message\n')
            f.write('2024-01-15 10:31:00,456 - test - ERROR - Error message\n')
            log_path = f.name

        # Create temp output path
        output_path = tempfile.mktemp(suffix='.log')

        try:
            with patch('cyberpulse.cli.commands.log.settings') as mock_settings:
                mock_settings.log_file = log_path

                result = runner.invoke(app, ['export', '--output', output_path])
                assert result.exit_code == 0
                assert os.path.exists(output_path)

                # Check content
                with open(output_path, 'r') as f:
                    content = f.read()
                assert 'Test message' in content
                assert 'Error message' in content
        finally:
            os.unlink(log_path)
            if os.path.exists(output_path):
                os.unlink(output_path)

    def test_log_export_with_since_filter(self) -> None:
        """Test log export with time filter."""
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write('2024-01-15 10:30:00,123 - test - INFO - Old message\n')
            f.write('2025-01-15 10:30:00,123 - test - INFO - New message\n')
            log_path = f.name

        output_path = tempfile.mktemp(suffix='.log')

        try:
            with patch('cyberpulse.cli.commands.log.settings') as mock_settings:
                mock_settings.log_file = log_path

                result = runner.invoke(app, ['export', '--output', output_path, '--since', '1d'])
                assert result.exit_code == 0

                with open(output_path, 'r') as f:
                    content = f.read()
                assert 'New message' in content
                assert 'Old message' not in content
        finally:
            os.unlink(log_path)
            if os.path.exists(output_path):
                os.unlink(output_path)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `.venv/bin/pytest tests/test_cli/test_log_commands.py::TestLogExport -v`
Expected: FAIL (export command not implemented)

- [ ] **Step 3: 实现 log export 命令**

在 `log.py` 中添加 export 命令：

```python
# src/cyberpulse/cli/commands/log.py
# 在文件末尾添加：

@app.command("export")
def export_logs(
    output: str = typer.Option(..., "--output", "-o", help="Output file path"),
    since: Optional[str] = typer.Option(
        None, "--since", "-s", help="Export logs since time (e.g., '1h', '24h', '7d')"
    ),
    level: Optional[str] = typer.Option(
        None, "--level", "-l", help="Filter by log level (ERROR, WARNING, INFO, DEBUG)"
    ),
) -> None:
    """Export logs to a file.

    Exports log entries to a file, optionally filtered by time and level.

    Examples:
        cyber-pulse log export --output /tmp/cyberpulse.log
        cyber-pulse log export --output /tmp/errors.log --level ERROR --since 24h
    """
    log_path = get_log_file_path()

    if not log_path.exists():
        console.print(f"[red]Log file not found: {log_path}[/red]")
        raise typer.Exit(1)

    # Parse since parameter
    since_dt = None
    if since:
        since_dt = parse_time_delta(since)
        if since_dt is None:
            console.print(f"[red]Invalid time format: {since}[/red]")
            console.print("[dim]Use format like '1h', '24h', '7d', '30m'[/dim]")
            raise typer.Exit(1)

    # Read all lines
    lines = read_log_lines(log_path, n=50000, from_end=True)

    # Filter and export
    exported = []
    for line in lines:
        parsed = parse_log_line(line)
        if not parsed:
            continue

        # Apply filters
        if since_dt:
            try:
                log_dt = datetime.strptime(parsed['timestamp'], '%Y-%m-%d %H:%M:%S,%f')
                if log_dt < since_dt:
                    continue
            except ValueError:
                continue

        if level and parsed['level'] != level.upper():
            continue

        exported.append(line)

    if not exported:
        console.print("[dim]No log entries match the criteria.[/dim]")
        raise typer.Exit(0)

    # Write to output file
    try:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            for line in exported:
                f.write(line + '\n')

        console.print(f"[green]✓[/green] Exported {len(exported)} log entries to {output}")
        console.print(f"[dim]File size: {format_file_size(output_path.stat().st_size)}[/dim]")
    except OSError as e:
        console.print(f"[red]Failed to write output file: {e}[/red]")
        raise typer.Exit(1)
```

- [ ] **Step 4: 运行测试验证通过**

Run: `.venv/bin/pytest tests/test_cli/test_log_commands.py::TestLogExport -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/cyberpulse/cli/commands/log.py tests/test_cli/test_log_commands.py
git commit -m "feat(log): add export command for log file export"
```

---

## Task 4: 添加 JSON 格式输出支持

**Files:**
- Modify: `src/cyberpulse/cli/commands/log.py`
- Test: `tests/test_cli/test_log_commands.py`

- [ ] **Step 1: 编写失败的测试**

```python
# tests/test_cli/test_log_commands.py

class TestLogJsonOutput:
    """Tests for JSON format output."""

    def test_log_errors_json_format(self) -> None:
        """Test log errors command with JSON output."""
        import tempfile
        import json

        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write('2024-01-15 10:30:00,123 - test - ERROR - Test error\n')
            log_path = f.name

        try:
            with patch('cyberpulse.cli.commands.log.settings') as mock_settings:
                mock_settings.log_file = log_path

                result = runner.invoke(app, ['errors', '--format', 'json'])
                assert result.exit_code == 0

                # Should be valid JSON
                data = json.loads(result.stdout)
                assert isinstance(data, list)
                assert len(data) == 1
                assert data[0]['level'] == 'ERROR'
                assert data[0]['message'] == 'Test error'
        finally:
            os.unlink(log_path)

    def test_log_search_json_format(self) -> None:
        """Test log search command with JSON output."""
        import tempfile
        import json

        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write('2024-01-15 10:30:00,123 - test - INFO - Test message\n')
            log_path = f.name

        try:
            with patch('cyberpulse.cli.commands.log.settings') as mock_settings:
                mock_settings.log_file = log_path

                result = runner.invoke(app, ['search', 'Test', '--format', 'json'])
                assert result.exit_code == 0

                data = json.loads(result.stdout)
                assert isinstance(data, list)
                assert len(data) == 1
        finally:
            os.unlink(log_path)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `.venv/bin/pytest tests/test_cli/test_log_commands.py::TestLogJsonOutput -v`
Expected: FAIL (--format option not implemented)

- [ ] **Step 3: 实现 JSON 格式输出**

修改 `error_logs` 命令添加 `--format` 参数：

```python
# src/cyberpulse/cli/commands/log.py
# 添加 import
import json

# 修改 error_logs 函数签名和实现：
@app.command("errors")
def error_logs(
    since: Optional[str] = typer.Option(
        None, "--since", "-s", help="Show errors since time (e.g., '1h', '24h', '7d')"
    ),
    source: Optional[str] = typer.Option(
        None, "--source", help="Filter by source/logger name"
    ),
    n: int = typer.Option(50, "--lines", "-n", help="Maximum number of errors to show"),
    format: str = typer.Option(
        "text", "--format", "-f", help="Output format: text or json"
    ),
) -> None:
    """Show error logs from the cyber-pulse log file.

    Displays ERROR and CRITICAL level log entries, optionally filtered by
    time window and source.

    Examples:
        cyber-pulse log errors
        cyber-pulse log errors --since 1h
        cyber-pulse log errors --since 24h --source cyberpulse.tasks
        cyber-pulse log errors --format json
    """
    log_path = get_log_file_path()

    if not log_path.exists():
        if format == "json":
            print(json.dumps([]))
        else:
            console.print(f"[yellow]Log file not found: {log_path}[/yellow]")
        raise typer.Exit(0)

    # Parse since parameter
    since_dt = None
    if since:
        since_dt = parse_time_delta(since)
        if since_dt is None:
            if format == "json":
                print(json.dumps({"error": f"Invalid time format: {since}"}))
            else:
                console.print(f"[red]Invalid time format: {since}[/red]")
                console.print("[dim]Use format like '1h', '24h', '7d', '30m'[/dim]")
            raise typer.Exit(1)

    lines = read_log_lines(log_path, n=1000, from_end=True)

    errors = []
    for line in lines:
        parsed = parse_log_line(line)
        if parsed and parsed['level'] in ('ERROR', 'CRITICAL'):
            # Apply filters
            if since_dt:
                try:
                    log_dt = datetime.strptime(parsed['timestamp'], '%Y-%m-%d %H:%M:%S,%f')
                    if log_dt < since_dt:
                        continue
                except ValueError:
                    logger.debug(f"Could not parse timestamp: {parsed['timestamp']}")

            if source and source not in parsed['logger']:
                continue

            errors.append(parsed)

            if len(errors) >= n:
                break

    if format == "json":
        print(json.dumps(errors, indent=2))
        raise typer.Exit(0)

    if not errors:
        console.print("[dim]No error logs found.[/dim]")
        raise typer.Exit(0)

    console.print(Panel(f"Found {len(errors)} error entries", style="red bold"))

    for entry in errors:
        level = entry['level']
        color = 'red bold' if level == 'CRITICAL' else 'red'
        console.print(
            f"[dim]{entry['timestamp']}[/dim] "
            f"[{color}]{level:8}[/{color}] "
            f"[cyan]{entry['logger']}[/cyan]"
        )
        console.print(f"  {entry['message']}")
        console.print()
```

同样修改 `search_logs` 命令：

```python
# 修改 search_logs 函数签名和实现：
@app.command("search")
def search_logs(
    text: str = typer.Argument(..., help="Text pattern to search for"),
    n: int = typer.Option(50, "--lines", "-n", help="Maximum number of results"),
    level: Optional[str] = typer.Option(
        None, "--level", "-l", help="Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    ),
    format: str = typer.Option(
        "text", "--format", "-f", help="Output format: text or json"
    ),
) -> None:
    """Search logs for a specific text pattern.

    Searches through all log entries for the given text pattern.
    Pattern matching is case-insensitive by default.

    Examples:
        cyber-pulse log search "connection failed"
        cyber-pulse log search "error" --level ERROR
        cyber-pulse log search "error" --format json
    """
    log_path = get_log_file_path()

    if not log_path.exists():
        if format == "json":
            print(json.dumps([]))
        else:
            console.print(f"[yellow]Log file not found: {log_path}[/yellow]")
        raise typer.Exit(0)

    lines = read_log_lines(log_path, n=5000, from_end=True)

    matches = []
    search_lower = text.lower()

    for line in lines:
        parsed = parse_log_line(line)
        if parsed:
            if search_lower in parsed['message'].lower() or search_lower in parsed['logger'].lower():
                if level and parsed['level'] != level.upper():
                    continue
                matches.append(parsed)

                if len(matches) >= n:
                    break
        elif search_lower in line.lower():
            matches.append({
                'timestamp': '-',
                'logger': '-',
                'level': '-',
                'message': line,
            })

            if len(matches) >= n:
                break

    if format == "json":
        print(json.dumps(matches, indent=2))
        raise typer.Exit(0)

    if not matches:
        console.print(f"[dim]No matches found for '{text}'.[/dim]")
        raise typer.Exit(0)

    console.print(Panel(f"Found {len(matches)} matches for '{text}'", style="blue bold"))

    for entry in matches:
        log_level = entry['level']
        if log_level != '-':
            color = {
                'DEBUG': 'dim',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red bold',
            }.get(log_level, 'white')
            console.print(
                f"[dim]{entry['timestamp']}[/dim] "
                f"[{color}]{log_level:8}[/{color}] "
                f"[cyan]{entry['logger']}[/cyan] - "
                f"{entry['message']}"
            )
        else:
            console.print(entry['message'])
```

- [ ] **Step 4: 运行测试验证通过**

Run: `.venv/bin/pytest tests/test_cli/test_log_commands.py::TestLogJsonOutput -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/cyberpulse/cli/commands/log.py tests/test_cli/test_log_commands.py
git commit -m "feat(log): add JSON format output for errors and search commands"
```

---

## Task 5: 添加 `log clear` 命令

**Files:**
- Modify: `src/cyberpulse/cli/commands/log.py`
- Test: `tests/test_cli/test_log_commands.py`

- [ ] **Step 1: 编写失败的测试**

```python
# tests/test_cli/test_log_commands.py

class TestLogClear:
    """Tests for log clear command."""

    def test_log_clear_older_than_days(self) -> None:
        """Test log clear removes old entries."""
        import tempfile
        import os
        from datetime import datetime, timedelta

        # Create log with old and new entries
        old_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]
        new_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write(f'{old_date} - test - INFO - Old message\n')
            f.write(f'{new_date} - test - INFO - New message\n')
            log_path = f.name

        try:
            with patch('cyberpulse.cli.commands.log.settings') as mock_settings:
                mock_settings.log_file = log_path

                result = runner.invoke(app, ['clear', '--older-than', '7d', '--yes'])
                assert result.exit_code == 0

                # Check file only has new message
                with open(log_path, 'r') as f:
                    content = f.read()
                assert 'New message' in content
                assert 'Old message' not in content
        finally:
            os.unlink(log_path)

    def test_log_clear_requires_confirmation(self) -> None:
        """Test log clear requires confirmation without --yes."""
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write('2024-01-15 10:30:00,123 - test - INFO - Test\n')
            log_path = f.name

        try:
            with patch('cyberpulse.cli.commands.log.settings') as mock_settings:
                mock_settings.log_file = log_path

                # Without --yes, should prompt for confirmation
                result = runner.invoke(app, ['clear', '--older-than', '7d'])
                assert 'Confirm' in result.stdout or result.exit_code != 0
        finally:
            os.unlink(log_path)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `.venv/bin/pytest tests/test_cli/test_log_commands.py::TestLogClear -v`
Expected: FAIL (clear command not implemented)

- [ ] **Step 3: 实现 log clear 命令**

```python
# src/cyberpulse/cli/commands/log.py
# 在文件末尾添加：

@app.command("clear")
def clear_logs(
    older_than: str = typer.Option(
        "7d", "--older-than", "-o", help="Clear logs older than (e.g., '7d', '30d')"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompt"
    ),
) -> None:
    """Clear old log entries from the log file.

    Removes log entries older than the specified time period.
    By default, removes entries older than 7 days.

    Examples:
        cyber-pulse log clear --older-than 7d
        cyber-pulse log clear --older-than 30d --yes
    """
    log_path = get_log_file_path()

    if not log_path.exists():
        console.print(f"[yellow]Log file not found: {log_path}[/yellow]")
        raise typer.Exit(0)

    # Parse older_than parameter
    threshold_dt = parse_time_delta(older_than)
    if threshold_dt is None:
        console.print(f"[red]Invalid time format: {older_than}[/red]")
        console.print("[dim]Use format like '7d', '30d'[/dim]")
        raise typer.Exit(1)

    # Read all lines
    lines = read_log_lines(log_path, n=100000, from_end=False)

    # Filter out old entries
    kept_lines = []
    removed_count = 0

    for line in lines:
        parsed = parse_log_line(line)
        if parsed:
            try:
                log_dt = datetime.strptime(parsed['timestamp'], '%Y-%m-%d %H:%M:%S,%f')
                if log_dt < threshold_dt:
                    removed_count += 1
                    continue
            except ValueError:
                pass  # Keep entries with invalid timestamps
        kept_lines.append(line)

    if removed_count == 0:
        console.print("[dim]No log entries to remove.[/dim]")
        raise typer.Exit(0)

    # Confirm
    if not yes:
        console.print(f"[yellow]This will remove {removed_count} log entries older than {older_than}.[/yellow]")
        confirm = typer.confirm("Continue?")
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(0)

    # Write back
    try:
        with open(log_path, 'w', encoding='utf-8') as f:
            for line in kept_lines:
                f.write(line + '\n')

        console.print(f"[green]✓[/green] Removed {removed_count} log entries")
        console.print(f"[dim]Remaining entries: {len(kept_lines)}[/dim]")
        console.print(f"[dim]File size: {format_file_size(log_path.stat().st_size)}[/dim]")
    except OSError as e:
        console.print(f"[red]Failed to update log file: {e}[/red]")
        raise typer.Exit(1)
```

- [ ] **Step 4: 运行测试验证通过**

Run: `.venv/bin/pytest tests/test_cli/test_log_commands.py::TestLogClear -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/cyberpulse/cli/commands/log.py tests/test_cli/test_log_commands.py
git commit -m "feat(log): add clear command for log cleanup"
```

---

## Task 6: 更新文档

**Files:**
- Modify: `docs/cli-usage-manual.md`

- [ ] **Step 1: 更新 CLI 使用手册**

在 `docs/cli-usage-manual.md` 中添加新命令说明：

```markdown
### 诊断命令增强

#### 服务状态检查

`diagnose system` 现在检查：
- API 服务健康状态
- Dramatiq 任务队列深度

#### 拒绝原因展示

`diagnose errors` 现在显示 `rejection_reason` 字段：

```bash
cyber-pulse diagnose errors
```

输出包含 Rejection Reason 列，显示 Item 被拒绝的具体原因。

### 日志命令增强

#### 日志导出

```bash
# 导出最近 24 小时的日志
cyber-pulse log export --output /tmp/cyberpulse.log --since 24h

# 仅导出错误日志
cyber-pulse log export --output /tmp/errors.log --level ERROR
```

#### JSON 格式输出

```bash
# JSON 格式的错误日志
cyber-pulse log errors --format json

# JSON 格式的搜索结果
cyber-pulse log search "failed" --format json
```

#### 日志清理

```bash
# 清理 7 天前的日志（需要确认）
cyber-pulse log clear --older-than 7d

# 清理 30 天前的日志（跳过确认）
cyber-pulse log clear --older-than 30d --yes
```
```

- [ ] **Step 2: 提交**

```bash
git add docs/cli-usage-manual.md
git commit -m "docs: update CLI manual for diagnose and log enhancements"
```

---

## Task 7: 最终验证

- [ ] **Step 1: 运行完整测试套件**

Run: `.venv/bin/pytest tests/test_cli/ -v`
Expected: All tests PASS

- [ ] **Step 2: 运行代码检查**

Run: `.venv/bin/ruff check src/cyberpulse/cli/commands/`
Expected: No issues

Run: `.venv/bin/mypy src/cyberpulse/cli/commands/ --ignore-missing-imports`
Expected: Success

- [ ] **Step 3: 最终提交**

```bash
git add -A
git commit -m "feat: enhance diagnose and log commands (issues #15 #16)

- diagnose errors: show rejection_reason from raw_metadata
- diagnose system: add API health and queue depth checks
- diagnose sources: add collection history with last collection time
- log export: new command for exporting logs to file
- log errors/search: add --format json for structured output
- log clear: new command for cleaning old log entries"
```

---

## 关联 Issues

- Closes #15 - 增强诊断命令
- Closes #16 - 增强日志功能