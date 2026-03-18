# Cyber Pulse

Cyber Pulse 是一个内部战略情报采集与标准化系统。从多个情报源采集数据，进行标准化处理，并通过拉取式 API 向下游分析系统提供清洗后的数据。

## 功能特性

- 情报源管理与评分
- 多源数据采集（RSS、API、Web 抓取、媒体 API、平台专用）
- 数据标准化与质量控制
- 拉取式游标 API（至少一次语义）
- 批处理模式，支持可配置调度

## 快速开始

### 前置条件

- Python 3.11+
- PostgreSQL
- Redis

### 安装

1. 克隆仓库：
```bash
git clone https://github.com/your-username/cyber-pulse.git
cd cyber-pulse
```

2. 创建虚拟环境并安装依赖：
```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -e .
pip install -e ".[dev]"
```

3. 配置环境变量：
```bash
cp .env.example .env
# 编辑 .env 文件，填入你的配置
```

4. 启动服务：
```bash
uvicorn cyber_pulse.main:app --host 0.0.0.0 --port 8000
```

5. 运行测试：
```bash
pytest
```

## 系统架构

Cyber Pulse 采用批处理模型，包含以下组件：

- **Source Governance**：管理情报源元数据、评分和配置
- **Task Scheduler**：基于源优先级协调采集任务
- **Connectors**：实现特定来源的数据采集逻辑
- **Normalizer**：将采集数据标准化为统一格式
- **Quality Gate**：发布前验证数据结构
- **API Service**：提供拉取式数据访问接口

详细架构文档见 `docs/` 目录。