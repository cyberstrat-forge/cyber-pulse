# Issue: CLI JSON 输出中文显示为 Unicode 转义序列

## 问题概述

**发现日期**: 2026-03-24
**严重程度**: 低 (不影响功能，影响可读性)
**影响范围**: CLI 所有 JSON 格式输出

## 问题复现

执行以下命令获取内容详情：

```bash
docker compose -f deploy/docker-compose.yml exec api cyber-pulse content get cnt_20260324121106_92464fa9
```

**实际输出**（部分）：

```json
{
  "normalized_title": "\u6df1\u5ea6\u63ed\u79d8\uff1aOpenClaw Skill\u5e02\u573a\u7684\u706b\u7206\u3001\u98ce\u9669\u4e0e\u9632\u5fa1",
  "normalized_body": "\u5b57\u8282\u8df3\u52a8\u5b89\u5168\u4e2d\u5fc3 2026-03-03 17:04 \u5e7f\u4e1c\n\nOpenClaw\u706b\u7206\u5168\u7403..."
}
```

**期望输出**：

```json
{
  "normalized_title": "深度揭秘：OpenClaw Skill市场的火爆、风险与防御",
  "normalized_body": "字节跳动安全中心 2026-03-03 17:04 广东\n\nOpenClaw火爆全球..."
}
```

## 根因分析

### 问题位置

文件：`src/cyberpulse/cli/commands/content.py`

### 原因

Python 的 `json.dumps()` 函数默认使用 `ensure_ascii=True` 参数，会将所有非 ASCII 字符（包括中文）转义为 Unicode 编码形式（如 `\u6df1`）。

### 涉及代码位置

| 行号 | 函数 | 当前代码 |
|------|------|----------|
| 129 | `list_content` | `print(json.dumps(output, indent=2))` |
| 222 | `get_content` (单个) | `print(json.dumps(output, indent=2))` |
| 255 | `get_content` (列表) | `console.print(json.dumps(output_list, indent=2))` |
| 289 | `content_stats` | `print(json.dumps(stats, indent=2))` |

## 解决方案

### 修复方法

在所有 `json.dumps()` 调用中添加 `ensure_ascii=False` 参数：

```python
# 修改前
print(json.dumps(output, indent=2))

# 修改后
print(json.dumps(output, indent=2, ensure_ascii=False))
```

### 完整修改清单

**文件**: `src/cyberpulse/cli/commands/content.py`

1. **第 129 行**（`list_content` 函数）：
   ```python
   print(json.dumps(output, indent=2, ensure_ascii=False))
   ```

2. **第 222 行**（`get_content` 函数，单个内容）：
   ```python
   print(json.dumps(output, indent=2, ensure_ascii=False))
   ```

3. **第 255 行**（`get_content` 函数，内容列表）：
   ```python
   console.print(json.dumps(output_list, indent=2, ensure_ascii=False))
   ```

4. **第 289 行**（`content_stats` 函数）：
   ```python
   print(json.dumps(stats, indent=2, ensure_ascii=False))
   ```

## 其他可能受影响的文件

建议检查其他 CLI 命令文件是否存在相同问题：

- `src/cyberpulse/cli/commands/job.py`
- `src/cyberpulse/cli/commands/log.py`
- `src/cyberpulse/cli/commands/source.py`

## 验证方法

修复后重新构建并部署，执行：

```bash
docker compose -f deploy/docker-compose.yml exec api cyber-pulse content get cnt_20260324121106_92464fa9
```

确认输出中的中文字符正常显示，不再是 Unicode 转义序列。

## 参考资料

- Python `json.dumps()` 文档：https://docs.python.org/3/library/json.html#json.dumps
- `ensure_ascii` 参数说明：If `ensure_ascii` is true (the default), the output is guaranteed to have all incoming non-ASCII characters escaped.