# Cyber Pulse

Cyber Pulse is a strategic intelligence collection system that gathers data from multiple sources, normalizes it, and provides a pull-based API for downstream analysis systems.

## Features

- Source governance and scoring
- Multi-source data collection (RSS, APIs, Web Scraping, Media APIs, Platform-specific)
- Data normalization and quality gating
- Pull-based cursor API with at-least-once semantics
- Batch processing with configurable scheduling

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL
- Redis

### Installation

1. Clone the repository:
```bash
git clone https://github.com/your-username/cyber-pulse.git
cd cyber-pulse
```

2. Create a virtual environment and install dependencies:
```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -e .
pip install -e ".[dev]"
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Start the service:
```bash
uvicorn cyber_pulse.main:app --host 0.0.0.0 --port 8000
```

5. Run tests:
```bash
pytest
```

## Architecture

Cyber Pulse follows a batch processing model with the following components:

- **Source Governance**: Manages source metadata, scoring, and configuration
- **Task Scheduler**: Coordinates ingestion tasks based on source priority
- **Connectors**: Implement source-specific data collection logic
- **Normalizer**: Standardizes collected data into a common format
- **Quality Gate**: Validates data structure before publication
- **API Service**: Provides pull-based access to normalized data

For detailed architecture documentation, see the `docs/` directory.