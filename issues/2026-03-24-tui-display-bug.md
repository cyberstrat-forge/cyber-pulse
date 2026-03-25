# Issue: TUI 显示异常

## 问题概述

**发现日期**: 2026-03-24
**严重程度**: P1（影响用户体验）
**影响范围**: TUI 交互模式

## 问题复现

```bash
docker compose -f deploy/docker-compose.yml exec api cyber-pulse shell
```

### 现象 1: 中间区域空白

启动 TUI 后，输出区域显示空白，虽然有欢迎消息但不可见。

输入命令后才显示内容。

### 现象 2: 命令输入框不正确

设计要求：
```
│  cyber-pulse> [Input Area]                              │
```

实际显示：提示符和输入框分离，布局混乱。

## 根因分析

### 问题 1: 输出区域初始不刷新

**代码位置**: `src/cyberpulse/cli/tui.py` 第 206-212 行

```python
self.output_control = FormattedTextControl(
    lambda: [("class:output", "\n".join(self.state.output_lines[-20:]))]
)
output_area = Window(
    content=self.output_control,
    height=15,
)
```

**问题**:
- `run()` 方法中添加了欢迎消息（第 292-294 行）
- 但 `FormattedTextControl` 使用 lambda 延迟计算
- 界面初始渲染时可能没有正确刷新

**对比设计要求**:
```
Welcome to cyber-pulse!

System Status:
• API Server: 🟢 Running on port 8000
• Database: 🟢 Connected
• Redis: 🟢 Connected
• Active Sources: 12 (T0: 2, T1: 5, T2: 5)
• Scheduled Jobs: 1

Recent Activity:
[2026-03-18 10:30:15] ✓ Source "安全客" added (T2)
...

Tips:
• Run '/source list' to see all sources
• Run '/diagnose system' to check system health
```

当前只显示：
```
Welcome to cyber-pulse TUI!
Type /help for available commands.
```

### 问题 2: 输入框布局错误

**代码位置**: `src/cyberpulse/cli/tui.py` 第 214-221 行，第 240 行

```python
# 当前实现
Label("cyber-pulse>", style="class:input"),  # 提示符单独一行
input_area,  # 输入框在另一行
```

**正确做法**:
```python
# 提示符和输入框应该在同一行
from prompt_toolkit.layout import VSplit

input_row = VSplit([
    Label("cyber-pulse> ", style="class:input"),
    Window(content=BufferControl(buffer=self.input_buffer), height=1),
])
```

### 问题 3: 缺少初始系统状态

设计要求显示系统状态（API、DB、Redis、Sources、Jobs），但当前 `run()` 方法没有获取这些信息。

## 解决方案

### 修复 1: 初始显示系统状态

```python
async def _get_system_status(self) -> dict:
    """获取系统状态信息"""
    from ..database import get_db
    from ..models import Source

    db = next(get_db())

    # 统计源
    total_sources = db.query(Source).filter(Source.status == "ACTIVE").count()
    t0_count = db.query(Source).filter(Source.tier == "T0").count()
    t1_count = db.query(Source).filter(Source.tier == "T1").count()
    t2_count = db.query(Source).filter(Source.tier == "T2").count()

    return {
        "api_running": True,  # 既然 TUI 在运行，API 肯定在运行
        "db_connected": True,
        "redis_connected": True,  # TODO: 实际检查
        "sources": {
            "total": total_sources,
            "t0": t0_count,
            "t1": t1_count,
            "t2": t2_count,
        },
        "jobs": 0,  # TODO: 从调度器获取
    }

def _build_welcome_message(self, status: dict) -> str:
    """构建欢迎消息"""
    lines = [
        "Welcome to cyber-pulse!",
        "",
        "System Status:",
        f"  • API Server: Running",
        f"  • Database: Connected",
        f"  • Redis: Connected",
        f"  • Active Sources: {status['sources']['total']} "
        f"(T0: {status['sources']['t0']}, T1: {status['sources']['t1']}, T2: {status['sources']['t2']})",
        f"  • Scheduled Jobs: {status['jobs']}",
        "",
        "Tips:",
        "  • Run '/source list' to see all sources",
        "  • Run '/diagnose system' to check system health",
        "  • Run '/help' to see all commands",
    ]
    return "\n".join(lines)
```

### 修复 2: 输入框布局

```python
from prompt_toolkit.layout import VSplit

def _build_layout(self) -> None:
    # ... 其他代码 ...

    # 输入行：提示符 + 输入框在同一行
    input_row = VSplit([
        Label("cyber-pulse> ", style="class:input", dont_extend=True),
        Window(
            content=BufferControl(buffer=self.input_buffer),
            height=1,
        ),
    ])

    # Main layout
    self.layout = Layout(
        HSplit([
            header,
            Window(height=1),  # Spacer
            output_area,
            Window(height=1),  # Spacer
            input_row,
            status_bar,
        ])
    )
```

### 修复 3: 强制刷新输出

```python
def run(self) -> None:
    # 初始化欢迎消息
    status = self._get_system_status()
    welcome = self._build_welcome_message(status)
    for line in welcome.split("\n"):
        self.state.add_output(line)

    # 强制刷新
    self.output_control.text = "\n".join(self.state.output_lines)

    # ... 其余代码 ...
```

## 相关文件

- `src/cyberpulse/cli/tui.py` - TUI 实现

---

## 补充：命令执行问题

### 问题 4: `source` 命令无响应

**现象**: 输入 `source` 后没有任何输出。

**原因分析**:
1. `source` 通过 subprocess 调用 CLI
2. 输出可能没有正确刷新到界面
3. 或者 subprocess 执行失败但错误没有显示

**代码位置**: 第 272-288 行
```python
result = subprocess.run(
    [sys.executable, "-m", "cyberpulse.cli.app"] + shlex.split(command),
    capture_output=True,
    text=True,
)
if result.stdout:
    self.state.add_output(result.stdout.strip())  # 添加到 output_lines
# 但界面可能没有刷新！
```

**问题**: `add_output()` 只是把文本加入列表，没有触发界面刷新。

### 问题 5: `/source` 命令无响应

**现象**: 输入 `/source` 无响应。

**原因**: `/source` 不是内置命令，会被传给 subprocess，但 CLI 不认识 `/source`（CLI 命令不带 `/` 前缀）。

```python
shlex.split("/source")  # 返回 ['/source']
# 执行: python -m cyberpulse.cli.app /source
# CLI 报错: No such command '/source'
```

### 问题 6: 命令格式不统一

**当前实现**:
- 内置命令需要 `/` 前缀: `/help`, `/exit`, `/quit`, `/clear`
- CLI 命令不需要: `source`, `job`, `content`, `version`

**用户困惑**: 不知道哪些命令需要 `/`，哪些不需要。

**设计要求**: 所有命令应该统一格式。

**建议修复**:
```python
def _execute_command(self, command: str) -> None:
    # 去掉 / 前缀，统一处理
    if command.startswith("/"):
        command = command[1:]

    # 内置命令
    if command in ("exit", "quit"):
        ...
    elif command == "help":
        ...
    elif command == "clear":
        ...
    else:
        # 外部命令
        ...
```

### 问题 7: `/exit` 或 `/quit` 无法退出

**现象**: 输入 `/exit` 或 `/quit` 后显示 "Exiting TUI mode..." 但程序没有退出。

**原因分析**:

```python
def _execute_command(self, command: str) -> None:
    if command in ("/exit", "/quit"):
        self.state.add_output("Exiting TUI mode...")
        self.running = False  # 设置标志
        return
```

```python
def run(self) -> None:
    while self.running:
        try:
            application.run()  # 阻塞在这里！
            if not self.running:
                break
```

**问题**: `application.run()` 是阻塞调用，设置 `self.running = False` 后，需要等待下一次循环才能退出，但 `application.run()` 没有返回。

**修复方案**:
```python
@self.key_bindings.add("enter")
def _(event: Any) -> None:
    command = self.input_buffer.text.strip()
    if command:
        self.state.add_to_history(command)
        self._execute_command(command)
        self.input_buffer.text = ""

        # 如果要退出，立即退出应用
        if not self.running:
            event.app.exit()
```

---

## 修复优先级

| 优先级 | 问题 | 影响 |
|--------|------|------|
| **P0** | `/exit` 无法退出 | 用户无法正常退出 |
| **P0** | 命令输出不显示 | TUI 完全不可用 |
| **P1** | 命令格式不统一 | 用户困惑 |
| **P1** | 初始界面空白 | 体验差 |

---

## 修复后的 `_execute_command` 示例

```python
def _execute_command(self, command: str, event: Any) -> None:
    """Execute a command."""
    self.state.add_output(f"> {command}")

    # 统一去掉 / 前缀
    if command.startswith("/"):
        command = command[1:]

    # 内置命令
    if command in ("exit", "quit"):
        self.state.add_output("Exiting TUI mode...")
        self.running = False
        event.app.exit()  # 立即退出
        return

    if command == "help":
        self.state.add_output(get_help_text())
        return

    if command == "clear":
        self.state.clear_output()
        self.state.add_output("Output cleared.")
        return

    # 外部命令通过 subprocess
    try:
        result = subprocess.run(
            [sys.executable, "-m", "cyberpulse.cli.app"] + shlex.split(command),
            capture_output=True,
            text=True,
            timeout=30,  # 添加超时
        )
        if result.stdout:
            self.state.add_output(result.stdout.strip())
        if result.stderr:
            self.state.add_output(result.stderr.strip(), style="error")
        if result.returncode != 0 and not result.stdout and not result.stderr:
            self.state.add_output(f"Command failed with exit code {result.returncode}")
    except subprocess.TimeoutExpired:
        self.state.add_output("Command timed out")
    except Exception as e:
        self.state.add_output(f"Error: {e}")
```

## 相关 Issue

- `2026-03-24-tui-test-report.md` - TUI 测试报告