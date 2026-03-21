# 部署优化计划6：CLI 源导入导出

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 CLI 中实现 source import/export 命令，支持 OPML 和 YAML 格式的批量导入导出。

**Architecture:** OPML 格式仅支持 RSS 源的基础信息导入；YAML 格式支持所有类型源的完整配置。复用现有 SourceService。

**Tech Stack:** Python, Typer, Pydantic

**依赖:** 无（独立于部署脚本）

---

## 文件结构

```
cyber-pulse/
├── src/cyberpulse/cli/
│   ├── commands/
│   │   ├── __init__.py          # 修改：注册新命令
│   │   └── source_io.py         # 新建：导入导出命令
│   └── app.py                   # 修改：添加命令
└── tests/
    └── test_cli/
        └── test_source_io.py    # 新建：测试
```

---

## Task 1: 创建源导入导出命令模块

**Files:**
- Create: `src/cyberpulse/cli/commands/source_io.py`

- [ ] **Step 1: 创建导入导出模块**

```python
"""
源导入导出命令

支持格式：
- OPML: 仅 RSS 源，基础信息
- YAML: 所有类型，完整配置
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Annotated, Optional

import typer
import yaml
from rich.console import Console
from rich.table import Table

from cyberpulse.services.source_service import SourceService

console = Console()
app = typer.Typer(name="source", help="Source import/export commands")


# ============================================================================
# 数据模型
# ============================================================================

OPML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
    <head>
        <title>cyber-pulse Sources</title>
    </head>
    <body>
    </body>
</opml>
"""


# ============================================================================
# 导入功能
# ============================================================================

def parse_opml(file_path: Path) -> list[dict]:
    """解析 OPML 文件，返回源列表"""
    sources = []

    tree = ET.parse(file_path)
    root = tree.getroot()

    # 查找所有 outline 元素
    for outline in root.iter("outline"):
        xml_url = outline.get("xmlUrl")
        if xml_url:
            sources.append({
                "name": outline.get("text") or outline.get("title") or "Unknown",
                "connector_type": "rss",
                "config": {"feed_url": xml_url},
                "tier": "T2",
            })

    return sources


def parse_yaml(file_path: Path) -> list[dict]:
    """解析 YAML 文件，返回源列表"""
    with open(file_path, "r") as f:
        data = yaml.safe_load(f)

    if not data or "sources" not in data:
        return []

    return data["sources"]


def import_sources(sources: list[dict], dry_run: bool = False) -> dict:
    """导入源到数据库"""
    results = {
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "errors": [],
    }

    if not sources:
        return results

    service = SourceService()

    for source_data in sources:
        try:
            name = source_data.get("name", "Unknown")
            connector_type = source_data.get("connector_type", "rss")

            # 检查是否已存在
            existing = service.find_by_name(name)
            if existing:
                results["skipped"] += 1
                console.print(f"  [yellow]跳过[/yellow] {name} (已存在)")
                continue

            if dry_run:
                console.print(f"  [blue]预览[/blue] {name} ({connector_type})")
                results["success"] += 1
                continue

            # 创建源
            source = service.create(
                name=name,
                connector_type=connector_type,
                config=source_data.get("config", {}),
                tier=source_data.get("tier", "T2"),
                tags=source_data.get("tags", []),
            )

            results["success"] += 1
            console.print(f"  [green]导入[/green] {name} ({source.id})")

        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"{name}: {str(e)}")
            console.print(f"  [red]失败[/red] {name}: {e}")

    return results


@app.command("import")
def import_command(
    file: Annotated[
        Path,
        typer.Argument(help="Import file path (OPML or YAML)"),
    ],
    format: Annotated[
        Optional[str],
        typer.Option("--format", "-f", help="File format (opml/yaml, auto-detect by extension)"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview import without making changes"),
    ] = False,
):
    """
    从 OPML 或 YAML 文件批量导入源

    示例:
        cyber-pulse source import feeds.opml
        cyber-pulse source import sources.yaml --dry-run
        cyber-pulse source import data.xml --format opml
    """
    if not file.exists():
        console.print(f"[red]文件不存在: {file}[/red]")
        raise typer.Exit(1)

    # 自动检测格式
    if not format:
        suffix = file.suffix.lower()
        if suffix in [".opml", ".xml"]:
            format = "opml"
        elif suffix in [".yaml", ".yml"]:
            format = "yaml"
        else:
            console.print(f"[red]无法识别文件格式，请使用 --format 指定[/red]")
            raise typer.Exit(1)

    console.print(f"[bold]导入源[/bold] (格式: {format}, 文件: {file})")

    # 解析文件
    if format == "opml":
        sources = parse_opml(file)
    elif format == "yaml":
        sources = parse_yaml(file)
    else:
        console.print(f"[red]不支持的格式: {format}[/red]")
        raise typer.Exit(1)

    if not sources:
        console.print("[yellow]未找到任何源[/yellow]")
        raise typer.Exit(0)

    console.print(f"找到 [bold]{len(sources)}[/bold] 个源")

    if dry_run:
        console.print("[blue]预览模式（不会实际导入）[/blue]")

    # 导入
    results = import_sources(sources, dry_run)

    # 显示结果
    console.print()
    console.print(f"[green]成功: {results['success']}[/green]")
    console.print(f"[yellow]跳过: {results['skipped']}[/yellow]")
    console.print(f"[red]失败: {results['failed']}[/red]")

    if results["errors"]:
        console.print()
        console.print("[bold]错误详情:[/bold]")
        for error in results["errors"]:
            console.print(f"  - {error}")


# ============================================================================
# 导出功能
# ============================================================================

def export_to_opml(sources: list, file_path: Path) -> None:
    """导出源到 OPML 文件"""
    root = ET.fromstring(OPML_TEMPLATE)
    body = root.find("body")

    for source in sources:
        if source.connector_type != "rss":
            continue

        outline = ET.SubElement(body, "outline")
        outline.set("text", source.name)
        outline.set("title", source.name)
        outline.set("type", "rss")
        outline.set("xmlUrl", source.config.get("feed_url", ""))

    tree = ET.ElementTree(root)
    tree.write(file_path, encoding="UTF-8", xml_declaration=True)


def export_to_yaml(sources: list, file_path: Path) -> None:
    """导出源到 YAML 文件"""
    data = {
        "sources": [
            {
                "name": s.name,
                "connector_type": s.connector_type,
                "config": s.config,
                "tier": s.tier,
                "tags": s.tags or [],
            }
            for s in sources
        ]
    }

    with open(file_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


@app.command("export")
def export_command(
    output: Annotated[
        Optional[Path],
        typer.Option("-o", "--output", help="Output file path"),
    ] = None,
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="Export format (opml/yaml)"),
    ] = "yaml",
    tier: Annotated[
        Optional[str],
        typer.Option("--tier", help="Filter by tier (T0/T1/T2/T3)"),
    ] = None,
):
    """
    导出源到 OPML 或 YAML 文件

    示例:
        cyber-pulse source export
        cyber-pulse source export -o sources.yaml
        cyber-pulse source export --format opml -o feeds.opml
        cyber-pulse source export --tier T0 -o tier0.yaml
    """
    service = SourceService()

    # 获取源列表
    sources = service.list_all()

    if tier:
        sources = [s for s in sources if s.tier == tier]

    if not sources:
        console.print("[yellow]没有源可导出[/yellow]")
        raise typer.Exit(0)

    # 确定输出文件
    if not output:
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        ext = ".opml" if format == "opml" else ".yaml"
        output = Path(f"sources-{timestamp}{ext}")

    console.print(f"[bold]导出源[/bold] (格式: {format}, 文件: {output})")

    # 导出
    if format == "opml":
        # OPML 仅支持 RSS 源
        rss_sources = [s for s in sources if s.connector_type == "rss"]
        if len(rss_sources) < len(sources):
            console.print(
                f"[yellow]注意: OPML 仅支持 RSS 源，"
                f"跳过 {len(sources) - len(rss_sources)} 个非 RSS 源[/yellow]"
            )
        export_to_opml(rss_sources, output)
        console.print(f"[green]已导出 {len(rss_sources)} 个 RSS 源[/green]")
    elif format == "yaml":
        export_to_yaml(sources, output)
        console.print(f"[green]已导出 {len(sources)} 个源[/green]")
    else:
        console.print(f"[red]不支持的格式: {format}[/red]")
        raise typer.Exit(1)

    console.print(f"文件: [bold]{output}[/bold]")


# ============================================================================
# 列表命令（辅助）
# ============================================================================

@app.command("list")
def list_command(
    tier: Annotated[
        Optional[str],
        typer.Option("--tier", help="Filter by tier"),
    ] = None,
):
    """列出所有源"""
    service = SourceService()
    sources = service.list_all()

    if tier:
        sources = [s for s in sources if s.tier == tier]

    if not sources:
        console.print("[yellow]没有源[/yellow]")
        return

    table = Table(title=f"Sources ({len(sources)})")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Type", style="blue")
    table.add_column("Tier", style="yellow")
    table.add_column("Status")

    for s in sources:
        status = "[green]active[/green]" if s.is_active else "[red]inactive[/red]"
        table.add_row(s.id, s.name, s.connector_type, s.tier, status)

    console.print(table)


if __name__ == "__main__":
    app()
```

- [ ] **Step 2: 提交新模块**

```bash
git add src/cyberpulse/cli/commands/source_io.py
git commit -m "$(cat <<'EOF'
feat(cli): add source import/export commands

Add source_io.py with import/export functionality:

Import commands:
- cyber-pulse source import <file>
- Auto-detect format by extension
- --format flag for explicit format
- --dry-run for preview mode

Export commands:
- cyber-pulse source export
- -o for output file
- --format opml/yaml
- --tier for filtering

Supported formats:
- OPML: RSS sources only, basic info
- YAML: All source types, full config

Includes source list command for quick viewing.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 注册命令到 CLI 主程序

**Files:**
- Modify: `src/cyberpulse/cli/app.py`

- [ ] **Step 1: 查看当前 CLI 结构**

Run: `cat src/cyberpulse/cli/app.py`

- [ ] **Step 2: 添加 source_io 子应用**

在现有命令注册之后添加：

```python
# 在文件开头的 imports 部分添加
from cyberpulse.cli.commands.source_io import app as source_io_app

# 在主应用注册部分添加
app.add_typer(source_io_app, name="source")
```

- [ ] **Step 3: 测试命令注册**

Run: `cyber-pulse source --help`

Expected: 显示 source 子命令帮助

- [ ] **Step 4: 提交**

```bash
git add src/cyberpulse/cli/app.py
git commit -m "$(cat <<'EOF'
feat(cli): register source import/export commands

Add source_io sub-app to main CLI:
- cyber-pulse source import <file>
- cyber-pulse source export
- cyber-pulse source list

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 编写测试

**Files:**
- Create: `tests/test_cli/test_source_io.py`

- [ ] **Step 1: 创建测试文件**

```python
"""Tests for source import/export commands"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from cyberpulse.cli.commands.source_io import (
    export_to_yaml,
    import_sources,
    parse_opml,
    parse_yaml,
)


class TestParseOPML:
    """OPML 解析测试"""

    def test_parse_basic_opml(self, tmp_path: Path):
        """测试基本 OPML 解析"""
        opml_content = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
    <head><title>Test</title></head>
    <body>
        <outline text="Feed 1" xmlUrl="https://example.com/feed1.xml"/>
        <outline text="Feed 2" xmlUrl="https://example.com/feed2.xml"/>
    </body>
</opml>
"""
        opml_file = tmp_path / "test.opml"
        opml_file.write_text(opml_content)

        sources = parse_opml(opml_file)

        assert len(sources) == 2
        assert sources[0]["name"] == "Feed 1"
        assert sources[0]["connector_type"] == "rss"
        assert sources[0]["config"]["feed_url"] == "https://example.com/feed1.xml"
        assert sources[0]["tier"] == "T2"

    def test_parse_empty_opml(self, tmp_path: Path):
        """测试空 OPML"""
        opml_content = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
    <head><title>Test</title></head>
    <body></body>
</opml>
"""
        opml_file = tmp_path / "empty.opml"
        opml_file.write_text(opml_content)

        sources = parse_opml(opml_file)

        assert len(sources) == 0


class TestParseYAML:
    """YAML 解析测试"""

    def test_parse_basic_yaml(self, tmp_path: Path):
        """测试基本 YAML 解析"""
        yaml_content = """
sources:
  - name: Test RSS
    connector_type: rss
    config:
      feed_url: https://example.com/feed.xml
    tier: T1
  - name: Test API
    connector_type: api
    config:
      base_url: https://api.example.com
    tier: T0
"""
        yaml_file = tmp_path / "sources.yaml"
        yaml_file.write_text(yaml_content)

        sources = parse_yaml(yaml_file)

        assert len(sources) == 2
        assert sources[0]["name"] == "Test RSS"
        assert sources[0]["connector_type"] == "rss"
        assert sources[1]["name"] == "Test API"
        assert sources[1]["connector_type"] == "api"

    def test_parse_empty_yaml(self, tmp_path: Path):
        """测试空 YAML"""
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("sources: []")

        sources = parse_yaml(yaml_file)

        assert len(sources) == 0


class TestImportSources:
    """导入测试"""

    @patch("cyberpulse.cli.commands.source_io.SourceService")
    def test_import_new_sources(self, mock_service_class):
        """测试导入新源"""
        mock_service = MagicMock()
        mock_service.find_by_name.return_value = None
        mock_service.create.return_value = MagicMock(id="src_test123")
        mock_service_class.return_value = mock_service

        sources = [
            {
                "name": "Test Source",
                "connector_type": "rss",
                "config": {"feed_url": "https://example.com/feed.xml"},
                "tier": "T2",
            }
        ]

        results = import_sources(sources)

        assert results["success"] == 1
        assert results["failed"] == 0
        assert results["skipped"] == 0

    @patch("cyberpulse.cli.commands.source_io.SourceService")
    def test_import_skips_existing(self, mock_service_class):
        """测试跳过已存在的源"""
        mock_service = MagicMock()
        mock_service.find_by_name.return_value = MagicMock(id="src_existing")
        mock_service_class.return_value = mock_service

        sources = [
            {
                "name": "Existing Source",
                "connector_type": "rss",
                "config": {"feed_url": "https://example.com/feed.xml"},
                "tier": "T2",
            }
        ]

        results = import_sources(sources)

        assert results["success"] == 0
        assert results["skipped"] == 1

    def test_import_dry_run(self):
        """测试预览模式"""
        with patch("cyberpulse.cli.commands.source_io.SourceService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.find_by_name.return_value = None
            mock_service_class.return_value = mock_service

            sources = [
                {
                    "name": "Test Source",
                    "connector_type": "rss",
                    "config": {"feed_url": "https://example.com/feed.xml"},
                    "tier": "T2",
                }
            ]

            results = import_sources(sources, dry_run=True)

            assert results["success"] == 1
            mock_service.create.assert_not_called()


class TestExportYAML:
    """YAML 导出测试"""

    def test_export_to_yaml(self, tmp_path: Path):
        """测试 YAML 导出"""
        mock_sources = [
            MagicMock(
                name="Source 1",
                connector_type="rss",
                config={"feed_url": "https://example.com/feed1.xml"},
                tier="T1",
                tags=["tech"],
            ),
            MagicMock(
                name="Source 2",
                connector_type="api",
                config={"base_url": "https://api.example.com"},
                tier="T0",
                tags=[],
            ),
        ]

        output_file = tmp_path / "export.yaml"
        export_to_yaml(mock_sources, output_file)

        assert output_file.exists()

        with open(output_file) as f:
            data = yaml.safe_load(f)

        assert "sources" in data
        assert len(data["sources"]) == 2
        assert data["sources"][0]["name"] == "Source 1"
        assert data["sources"][1]["connector_type"] == "api"
```

- [ ] **Step 2: 运行测试**

Run: `pytest tests/test_cli/test_source_io.py -v`

Expected: 所有测试通过

- [ ] **Step 3: 提交测试**

```bash
git add tests/test_cli/test_source_io.py
git commit -m "$(cat <<'EOF'
test(cli): add tests for source import/export

Add comprehensive tests for:
- OPML parsing (basic and empty)
- YAML parsing (basic and empty)
- Import functionality (new, existing, dry-run)
- YAML export

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 创建示例文件

**Files:**
- Create: `examples/sources-example.yaml`

- [ ] **Step 1: 创建 YAML 示例**

```yaml
# cyber-pulse 源配置示例
#
# 使用方法:
#   cyber-pulse source import sources-example.yaml
#   cyber-pulse source import sources-example.yaml --dry-run

sources:
  # RSS 源示例
  - name: "TechCrunch"
    connector_type: rss
    config:
      feed_url: "https://techcrunch.com/feed/"
    tier: T1
    tags:
      - tech
      - news

  - name: "Hacker News"
    connector_type: rss
    config:
      feed_url: "https://hnrss.org/frontpage"
    tier: T1
    tags:
      - tech
      - community

  # API 源示例
  - name: "Example API"
    connector_type: api
    config:
      base_url: "https://api.example.com/v1"
      api_key: "${EXAMPLE_API_KEY}"  # 从环境变量读取
      endpoints:
        - "/articles"
        - "/news"
    tier: T0
    tags:
      - premium

  # Web Scraper 示例
  - name: "Example Blog"
    connector_type: web
    config:
      url: "https://blog.example.com"
      selectors:
        title: "h1.post-title"
        content: "div.post-content"
        date: "time.published"
    tier: T2
    tags: []
```

- [ ] **Step 2: 提交示例**

```bash
git add examples/sources-example.yaml
git commit -m "$(cat <<'EOF'
docs: add example sources YAML file

Add sources-example.yaml demonstrating:
- RSS source configuration
- API source configuration
- Web scraper configuration
- Tier and tags usage
- Environment variable usage

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## 验收标准

- [ ] `cyber-pulse source --help` 显示帮助信息
- [ ] `cyber-pulse source import <file>` 成功导入源
- [ ] `cyber-pulse source import <file> --dry-run` 预览导入
- [ ] `cyber-pulse source export -o sources.yaml` 导出 YAML
- [ ] `cyber-pulse source export --format opml -o feeds.opml` 导出 OPML
- [ ] `cyber-pulse source list` 列出所有源
- [ ] 已存在的源在导入时被跳过
- [ ] OPML 导出跳过非 RSS 源并提示用户