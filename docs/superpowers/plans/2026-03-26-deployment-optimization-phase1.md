# 部署优化阶段 1 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 CLI 废弃、管理员 Key 机制重构、api.sh 管理脚本创建、用户分离支持

**Architecture:** 移除 CLI 模块，改用纯 Bash 脚本 api.sh 管理应用；Admin Key 仅存数据库，首次部署生成并输出；开发者和运维人员通过不同方式获取部署包

**Tech Stack:** Python 3.11, FastAPI, bcrypt, Bash, curl, jq

---

## 任务依赖关系

```
Task 1 (CLI 移除)
    │
    ├──→ Task 2 (startup.py) ──→ Task 3 (auth.py)
    │         │                        │
    │         └────────────────────────┴──→ Task 4 (generate-env.sh)
    │                                        │
    │                                        └──→ Task 5 (cyber-pulse.sh)
    │                                              │
    └──────────────────────────────────────────────┘
                       │
                       ↓
              Task 6 (api.sh 基础)
                       │
                       ↓
              Task 7 (文档更新)
                       │
                       ↓
              Task 8 (基本验证)
                       │
                       ↓
              Task 9 (build-deploy-package.sh)
                       │
                       ↓
              Task 10 (install.sh 用户分离)
                       │
                       ↓
              Task 11 (api.sh 高级命令)
                       │
                       ↓
              Task 12 (完整验证)
```

**执行顺序说明**:
- Task 1 必须首先完成（移除 CLI 后才能验证其他功能）
- Task 2-5 可并行执行（均为 Admin Key 机制重构，互不依赖）
- Task 6 依赖 Task 1（api.sh 替代 CLI）
- Task 7-8 依赖 Task 1-6（文档和验证需要功能完成）
- Task 9-11 依赖 Task 6（高级功能基于 api.sh 基础）
- Task 12 必须最后执行（完整验证所有功能）

---

## 文件结构

### 删除
- `src/cyberpulse/cli/` - 整个 CLI 模块目录

### 新增
- `scripts/api.sh` - API 管理脚本

### 修改
- `pyproject.toml` - 移除 CLI 入口点和依赖
- `src/cyberpulse/api/startup.py` - 修改 `ensure_admin_client()`
- `src/cyberpulse/api/auth.py` - 移除 `get_plain_key()` 方法
- `deploy/init/generate-env.sh` - 移除 `ADMIN_API_KEY` 生成
- `scripts/cyber-pulse.sh` - 移除 `admin show-key/rotate-key`，新增 `admin reset`

---

## Task 1: 移除 CLI 模块

**Depends on:** 无（首个任务）

**Files:**
- Delete: `src/cyberpulse/cli/` (整个目录)
- Modify: `pyproject.toml:35-37,58-59`
- Test: `tests/test_cli_removal.py` (新建)

- [ ] **Step 1: 编写测试验证 CLI 移除**

创建测试文件 `tests/test_cli_removal.py`:

```python
"""Tests for CLI module removal verification."""

import subprocess
import sys


class TestCLIRemoval:
    """Verify CLI module has been completely removed."""

    def test_cli_module_not_importable(self):
        """CLI module should not be importable."""
        result = subprocess.run(
            [sys.executable, "-c", "import cyberpulse.cli"],
            capture_output=True,
            text=True
        )
        assert result.returncode != 0, "CLI module should not be importable"
        assert "No module named" in result.stderr or "cannot import" in result.stderr

    def test_cyber_pulse_command_not_exists(self):
        """cyber-pulse CLI command should not exist."""
        result = subprocess.run(
            ["cyber-pulse", "--help"],
            capture_output=True,
            text=True
        )
        # Command should fail (not found or exit with error)
        assert result.returncode != 0

    def test_cli_directory_not_exists(self):
        """CLI directory should not exist."""
        import pathlib
        cli_dir = pathlib.Path("src/cyberpulse/cli")
        assert not cli_dir.exists(), "CLI directory should be removed"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
uv run pytest tests/test_cli_removal.py -v
```

Expected: 测试失败（CLI 模块仍存在）

- [ ] **Step 3: 删除 CLI 模块目录**

```bash
rm -rf src/cyberpulse/cli/
```

- [ ] **Step 4: 修改 pyproject.toml 移除 CLI 入口点**

删除第 58-59 行：
```diff
- [project.scripts]
- cyber-pulse = "cyberpulse.cli.app:app"
```

完整修改后的 `pyproject.toml` 相关部分：

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.1.0",
    "pytest-env>=1.0.0",
    "ruff>=0.2.0",
    "black>=23.12.0",
    "mypy>=1.8.0",
    "httpx>=0.26.0",
    "faker>=21.0.0",
    "factory-boy>=3.3.0",
]

[project.urls]
Homepage = "https://github.com/cyberstrat-forge/cyber-pulse"
Repository = "https://github.com/cyberstrat-forge/cyber-pulse"
```

- [ ] **Step 5: 修改 pyproject.toml 移除 CLI 依赖**

从 `dependencies` 列表中移除 typer, rich, prompt-toolkit（第 35-37 行）：

```diff
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "sqlalchemy>=2.0.0",
    "psycopg2-binary>=2.9.0",
    "alembic>=1.13.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "redis>=5.0.0",
    "dramatiq[redis]>=1.14.0",
    "apscheduler>=3.10.0",
    "httpx>=0.26.0",
    "feedparser>=6.0.0",
    "feedfinder2>=0.0.4",
    "trafilatura>=1.6.0",
    "google-api-python-client>=2.100.0",
-   "typer>=0.9.0",
-   "rich>=13.7.0",
-   "prompt-toolkit>=3.0.0",
    "python-dateutil>=2.8.0",
    "python-multipart>=0.0.6",
    "passlib[bcrypt]>=1.7.4",
    "beautifulsoup4>=4.14.3",
]
```

- [ ] **Step 6: 运行测试验证通过**

```bash
uv run pytest tests/test_cli_removal.py -v
```

Expected: 所有测试通过

- [ ] **Step 7: 提交 CLI 移除**

```bash
git add pyproject.toml tests/test_cli_removal.py
git add -u src/cyberpulse/cli/
git commit -m "refactor: remove CLI module

- Delete src/cyberpulse/cli/ directory
- Remove [project.scripts] entry point from pyproject.toml
- Remove typer, rich, prompt-toolkit dependencies
- Add tests to verify CLI removal

CLI is replaced by scripts/api.sh for API management"
```

---

## Task 2: 重构管理员 Key 机制 - startup.py

**Depends on:** Task 1 (CLI 移除)

**Files:**
- Modify: `src/cyberpulse/api/startup.py`
- Test: `tests/test_startup.py` (新建)

- [ ] **Step 1: 编写测试用例**

创建测试文件 `tests/test_startup.py`:

```python
"""Tests for API startup initialization."""

import os
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from cyberpulse.models import ApiClient, ApiClientStatus
from cyberpulse.api.startup import ensure_admin_client


@pytest.fixture
def db_session():
    """Create an in-memory database session for testing."""
    engine = create_engine("sqlite:///:memory:")
    from cyberpulse.models import Base
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestEnsureAdminClient:
    """Tests for ensure_admin_client function."""

    def test_creates_admin_when_none_exists(self, db_session, capsys):
        """Should create admin client if none exists."""
        with patch('cyberpulse.api.startup.SessionLocal', return_value=db_session):
            ensure_admin_client()

        # Check admin was created
        admin = db_session.query(ApiClient).filter(
            ApiClient.permissions.contains(["admin"])
        ).first()

        assert admin is not None
        assert admin.name == "Administrator"
        assert "admin" in admin.permissions
        assert admin.status == ApiClientStatus.ACTIVE

        # Check key was printed to stdout
        captured = capsys.readouterr()
        assert "Admin API Key:" in captured.out
        assert "cp_live_" in captured.out

    def test_does_not_create_if_admin_exists(self, db_session, capsys):
        """Should not create new admin if one already exists."""
        # Create existing admin
        existing = ApiClient(
            client_id="cli_existing01",
            name="Existing Admin",
            api_key="hashed_key",
            status=ApiClientStatus.ACTIVE,
            permissions=["admin", "read"],
        )
        db_session.add(existing)
        db_session.commit()

        with patch('cyberpulse.api.startup.SessionLocal', return_value=db_session):
            ensure_admin_client()

        # Should still be only one admin
        admins = db_session.query(ApiClient).filter(
            ApiClient.permissions.contains(["admin"])
        ).all()

        assert len(admins) == 1
        assert admins[0].client_id == "cli_existing01"

        # Key should not be printed
        captured = capsys.readouterr()
        assert "Admin API Key:" not in captured.out

    def test_generated_key_format(self, db_session, capsys):
        """Generated key should have correct format."""
        with patch('cyberpulse.api.startup.SessionLocal', return_value=db_session):
            ensure_admin_client()

        captured = capsys.readouterr()
        # Extract key from output
        for line in captured.out.split('\n'):
            if 'cp_live_' in line:
                # Key should be cp_live_ followed by 32 hex chars
                key = line.split('cp_live_')[-1].strip()
                assert len(key) == 32
                assert all(c in '0123456789abcdef' for c in key)
                break
```

- [ ] **Step 2: 运行测试验证失败**

```bash
uv run pytest tests/test_startup.py -v
```

Expected: 测试失败（现有实现不输出 Key）

- [ ] **Step 3: 修改 startup.py**

```python
"""API startup initialization.

Ensures admin client exists on first run.
"""

import logging
import secrets

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import ApiClient, ApiClientStatus
from .auth import generate_api_key, hash_api_key

logger = logging.getLogger(__name__)


def ensure_admin_client() -> None:
    """Ensure admin client exists.

    This function is called on API startup to create the initial
    admin client if none exists.

    On first run, generates a new admin API key, stores its bcrypt
    hash in the database, and outputs the plain key to terminal ONCE.

    The key cannot be retrieved later - use 'admin reset' to generate
    a new key if forgotten.
    """
    db: Session = SessionLocal()
    try:
        # Check if admin client already exists
        admin = db.query(ApiClient).filter(
            ApiClient.permissions.contains(["admin"])
        ).first()

        if admin:
            logger.info("Admin client already exists")
            return

        # Generate new admin key
        plain_key = generate_api_key()
        hashed_key = hash_api_key(plain_key)

        # Create admin client
        client_id = f"cli_{secrets.token_hex(8)}"

        admin = ApiClient(
            client_id=client_id,
            name="Administrator",
            api_key=hashed_key,
            status=ApiClientStatus.ACTIVE,
            permissions=["admin", "read"],
            description="System administrator (auto-created on first run)",
        )

        db.add(admin)
        db.commit()
        db.refresh(admin)

        logger.info(f"Created admin client: {client_id}")

        # Output key to terminal ONCE
        print(f"\n{'='*60}")
        print("Admin client created successfully.")
        print(f"{'='*60}")
        print(f"\n  Admin API Key: {plain_key}\n")
        print("  IMPORTANT: This key is shown ONCE. Save it securely now!")
        print("  If lost, use './scripts/cyber-pulse.sh admin reset' to generate a new key.")
        print(f"\n{'='*60}\n")

    except Exception as e:
        logger.error(f"Failed to ensure admin client: {e}")
        db.rollback()
        raise
    finally:
        db.close()
```

- [ ] **Step 4: 运行测试验证通过**

```bash
uv run pytest tests/test_startup.py -v
```

Expected: 所有测试通过

- [ ] **Step 5: 提交**

```bash
git add src/cyberpulse/api/startup.py tests/test_startup.py
git commit -m "feat(api): generate and output admin key on first run

- Admin key is now generated on first startup if no admin exists
- Key is output to terminal ONCE (cannot be retrieved later)
- Remove dependency on ADMIN_API_KEY env variable
- Add tests for startup behavior"
```

---

## Task 3: 重构管理员 Key 机制 - auth.py

**Depends on:** Task 2 (startup.py 已实现 Admin Key 生成)

**Files:**
- Modify: `src/cyberpulse/api/auth.py`
- Test: `tests/test_api_auth.py` (补充测试)

- [ ] **Step 1: 编写 reset_admin_key 测试用例**

在 `tests/test_api_auth.py` 中添加测试类：

```python
class TestResetAdminKey:
    """Tests for reset_admin_key functionality."""

    def test_reset_admin_key_success(self, db_session):
        """Should reset admin key and return new plain key."""
        # Create existing admin
        from cyberpulse.api.auth import hash_api_key, generate_api_key
        old_key = generate_api_key()
        admin = ApiClient(
            client_id="cli_admin01",
            name="Admin",
            api_key=hash_api_key(old_key),
            status=ApiClientStatus.ACTIVE,
            permissions=["admin", "read"],
        )
        db_session.add(admin)
        db_session.commit()

        # Reset key
        from cyberpulse.api.auth import ApiClientService
        service = ApiClientService(db_session)
        result = service.reset_admin_key()

        assert result is not None
        client, new_key = result
        assert client.client_id == "cli_admin01"
        assert new_key.startswith("cp_live_")
        assert new_key != old_key

        # Verify new key works
        from cyberpulse.api.auth import verify_api_key
        assert verify_api_key(new_key, client.api_key)

    def test_reset_admin_key_no_admin_exists(self, db_session):
        """Should return None if no admin client exists."""
        from cyberpulse.api.auth import ApiClientService
        service = ApiClientService(db_session)
        result = service.reset_admin_key()
        assert result is None

    def test_old_key_invalid_after_reset(self, db_session):
        """Old key should be invalid after reset."""
        from cyberpulse.api.auth import hash_api_key, generate_api_key, ApiClientService, verify_api_key
        old_key = generate_api_key()
        admin = ApiClient(
            client_id="cli_admin02",
            name="Admin",
            api_key=hash_api_key(old_key),
            status=ApiClientStatus.ACTIVE,
            permissions=["admin"],
        )
        db_session.add(admin)
        db_session.commit()

        service = ApiClientService(db_session)
        service.reset_admin_key()

        # Old key should no longer verify
        db_session.refresh(admin)
        assert not verify_api_key(old_key, admin.api_key)
```

- [ ] **Step 2: 运行测试验证失败**

```bash
uv run pytest tests/test_api_auth.py::TestResetAdminKey -v
```

Expected: 测试失败（方法未实现）

- [ ] **Step 3: 添加 reset_admin_key 方法到 ApiClientService**

在 `ApiClientService` 类中添加 `reset_admin_key` 方法（在 `rotate_key` 方法后）：

```python
    def reset_admin_key(self) -> Optional[Tuple[ApiClient, str]]:
        """
        Reset admin API key.

        Generates a new key for the first client with 'admin' permission.
        The old key immediately becomes invalid.

        Returns:
            Tuple of (ApiClient, new_plain_key) if successful, None otherwise
        """
        admin = self.get_by_permission("admin")
        if not admin:
            return None

        # Generate and hash new API key
        plain_key = generate_api_key()
        hashed_key = hash_api_key(plain_key)

        admin.api_key = hashed_key  # type: ignore[assignment]
        try:
            self.db.commit()
            self.db.refresh(admin)
            logger.info(f"Reset admin API key for client: {admin.client_id}")
            return admin, plain_key
        except Exception as e:
            logger.error(f"Failed to reset admin key: {e}")
            self.db.rollback()
            raise
```

- [ ] **Step 4: 移除 get_plain_key 方法**

删除 `get_plain_key` 方法（第 390-412 行），因为它依赖于环境变量中的明文 Key，与新的设计不符。

- [ ] **Step 5: 运行测试验证通过**

```bash
uv run pytest tests/test_api_auth.py -v
```

Expected: 所有测试通过

- [ ] **Step 6: 提交**

```bash
git add src/cyberpulse/api/auth.py tests/test_api_auth.py
git commit -m "refactor(auth): add reset_admin_key, remove get_plain_key

- Add reset_admin_key() for admin key reset functionality
- Remove get_plain_key() which relied on env variable storage
- Admin key is now database-only (bcrypt hashed)
- Add tests for reset_admin_key"
```

---

## Task 4: 重构管理员 Key 机制 - generate-env.sh

**Depends on:** Task 3 (auth.py 已实现 reset_admin_key)

**Files:**
- Modify: `deploy/init/generate-env.sh`
- Test: Shell 脚本语法验证

- [ ] **Step 1: 编写验证测试**

创建测试脚本 `tests/test_generate_env.sh`:

```bash
#!/usr/bin/env bash
# Tests for generate-env.sh modifications

set -e

SCRIPT_PATH="deploy/init/generate-env.sh"

echo "Testing generate-env.sh..."

# Test 1: Script syntax is valid
echo -n "  Syntax check... "
bash -n "$SCRIPT_PATH" && echo "PASS" || { echo "FAIL"; exit 1; }

# Test 2: No ADMIN_API_KEY in output
echo -n "  No ADMIN_API_KEY in script... "
if grep -q "ADMIN_API_KEY" "$SCRIPT_PATH"; then
    echo "FAIL: ADMIN_API_KEY still present"
    exit 1
else
    echo "PASS"
fi

# Test 3: No generate_admin_api_key function
echo -n "  No generate_admin_api_key function... "
if grep -q "generate_admin_api_key" "$SCRIPT_PATH"; then
    echo "FAIL: generate_admin_api_key function still present"
    exit 1
else
    echo "PASS"
fi

echo "All tests passed!"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
chmod +x tests/test_generate_env.sh
./tests/test_generate_env.sh
```

Expected: 测试失败（ADMIN_API_KEY 仍存在）

- [ ] **Step 3: 移除 ADMIN_API_KEY 生成**

删除 `generate_admin_api_key` 函数（第 60-65 行）和相关调用：

```diff
- # 生成 Admin API Key (32 字符，cp_live_ 前缀)
- generate_admin_api_key() {
-     local random_part
-     random_part=$(python3 -c "import secrets; print(secrets.token_hex(16))" 2>/dev/null || openssl rand -hex 16 2>/dev/null)
-     echo "cp_live_${random_part}"
- }
```

- [ ] **Step 4: 移除 generate_env_file 中的 admin_api_key 变量和生成逻辑**

修改 `generate_env_file` 函数：

```diff
  generate_env_file() {
      local force="${1:-false}"
      local postgres_password=""
      local secret_key=""
-     local admin_api_key=""
      local db_user="cyberpulse"
      local db_name="cyberpulse"
```

删除第 131 行：
```diff
-     admin_api_key=$(generate_admin_api_key)
```

- [ ] **Step 5: 从 .env 模板中移除 ADMIN_API_KEY**

修改 cat heredoc 部分（删除 ADMIN_API_KEY 相关行）：

```diff
  # JWT 安全配置
  SECRET_KEY=${secret_key}
  JWT_ALGORITHM=HS256
  ACCESS_TOKEN_EXPIRE_MINUTES=30

- # Admin API Key (首次启动时创建管理员客户端)
- ADMIN_API_KEY=${admin_api_key}

  # 日志配置
  LOG_LEVEL=INFO
```

- [ ] **Step 6: 更新输出摘要**

修改输出摘要部分（删除 Admin API Key 相关行）：

```diff
      echo -e "${BLUE}配置摘要:${NC}"
      echo -e "  数据库用户:   ${db_user}"
      echo -e "  数据库名称:   ${db_name}"
      echo -e "  数据库密码:   ${YELLOW}********${NC} (${#postgres_password} 字符)"
      echo -e "  JWT 密钥:     ${YELLOW}********${NC} (${#secret_key} 字符)"
-     echo -e "  Admin API Key: ${YELLOW}********${NC} (${#admin_api_key} 字符)"
      echo -e "  文件权限:     600"
      echo ""
      echo -e "${YELLOW}⚠ 重要提示:${NC}"
      echo "  1. 请妥善保管此配置文件，不要提交到版本控制"
      echo "  2. 数据库密码仅在首次部署时生成，后续会保留"
-     echo "  3. ADMIN_API_KEY 用于管理端 API 认证，请妥善保管"
-     echo "  4. 如需重置密码，请手动删除 .env 文件后重新运行"
+     echo "  3. Admin API Key 在首次启动时自动生成并输出到终端"
+     echo "  4. 如需重置 Key，请运行: ./scripts/cyber-pulse.sh admin reset"
```

- [ ] **Step 7: 运行测试验证通过**

```bash
./tests/test_generate_env.sh
```

Expected: 所有测试通过

- [ ] **Step 8: 提交**

```bash
git add deploy/init/generate-env.sh tests/test_generate_env.sh
git commit -m "refactor(deploy): remove ADMIN_API_KEY from .env generation

Admin API Key is now generated on first API startup and output
to terminal once. No longer stored in .env file.

Add shell test to verify removal."
```

---

## Task 5: 重构管理员 Key 机制 - cyber-pulse.sh

**Depends on:** Task 4 (generate-env.sh 已移除 ADMIN_API_KEY)

**Files:**
- Modify: `scripts/cyber-pulse.sh`
- Test: Shell 脚本功能验证

- [ ] **Step 1: 编写 admin reset 功能测试**

创建测试脚本 `tests/test_admin_reset.sh`:

```bash
#!/usr/bin/env bash
# Tests for cyber-pulse.sh admin reset command

set -e

SCRIPT_PATH="scripts/cyber-pulse.sh"

echo "Testing cyber-pulse.sh admin commands..."

# Test 1: Script syntax is valid
echo -n "  Syntax check... "
bash -n "$SCRIPT_PATH" && echo "PASS" || { echo "FAIL"; exit 1; }

# Test 2: No show-key command
echo -n "  No show-key command... "
if grep -q "show-key\|show_key" "$SCRIPT_PATH"; then
    echo "FAIL: show-key still present"
    exit 1
else
    echo "PASS"
fi

# Test 3: No rotate-key command
echo -n "  No rotate-key command... "
if grep -q "rotate-key\|rotate_key" "$SCRIPT_PATH"; then
    echo "FAIL: rotate-key still present"
    exit 1
else
    echo "PASS"
fi

# Test 4: Has reset command
echo -n "  Has reset command... "
if grep -q "cmd_admin_reset\|admin reset" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL: reset command not found"
    exit 1
fi

echo "All tests passed!"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
chmod +x tests/test_admin_reset.sh
./tests/test_admin_reset.sh
```

Expected: 测试失败（show-key/rotate-key 仍存在）

- [ ] **Step 3: 修改 cmd_admin 函数**

替换 `cmd_admin` 函数（第 1015-1034 行）：

```bash
cmd_admin() {
    local subcommand="${1:-help}"

    case "$subcommand" in
        reset)
            cmd_admin_reset
            ;;
        help|--help|-h)
            print_admin_help
            ;;
        *)
            print_error "Unknown admin subcommand: $subcommand"
            print_admin_help
            exit 1
            ;;
    esac
}
```

- [ ] **Step 2: 删除 cmd_admin_show_key 和 cmd_admin_rotate_key**

删除第 1036-1112 行的 `cmd_admin_show_key` 和 `cmd_admin_rotate_key` 函数。

- [ ] **Step 3: 添加 cmd_admin_reset 函数**

在 `cmd_admin` 函数后添加：

```bash
cmd_admin_reset() {
    print_header "Reset Admin API Key"

    # Check if service is running
    local current_env
    current_env=$(get_current_env)
    local compose_files
    compose_files=$(get_compose_files "$current_env")

    cd "$DEPLOY_DIR"

    # Check if API is running
    if ! $DOCKER_COMPOSE $compose_files ps api 2>/dev/null | grep -q "running"; then
        print_error "API service is not running"
        print_info "Start the service first: ./scripts/cyber-pulse.sh start"
        exit 1
    fi

    # Warning prompt
    print_warning "This will invalidate the current admin API key!"
    print_warning "All clients using the old key will lose access."
    echo ""
    read -r -p "Are you sure you want to reset? (yes/no): " response

    if [[ "$response" != "yes" ]]; then
        print_info "Reset cancelled"
        exit 0
    fi

    # Call API to reset admin key
    local api_url="http://localhost:8000"
    local temp_key=""

    # We need to call the reset endpoint
    # Since we don't have the old key, we need a different approach
    # Execute inside the container to reset the key

    print_step "Resetting admin key..."

    # Execute Python script inside API container to reset admin key
    local result
    result=$($DOCKER_COMPOSE $compose_files exec -T api python3 -c "
import sys
sys.path.insert(0, '/app')
from cyberpulse.database import SessionLocal
from cyberpulse.api.auth import ApiClientService

db = SessionLocal()
try:
    service = ApiClientService(db)
    result = service.reset_admin_key()
    if result:
        client, plain_key = result
        print(f'OK:{plain_key}')
    else:
        print('ERROR:No admin client found')
finally:
    db.close()
" 2>&1)

    if [[ "$result" == OK:* ]]; then
        local new_key="${result#OK:}"
        echo ""
        echo -e "${GREEN}══════════════════════════════════════════════════════════════${NC}"
        echo -e "${GREEN}Admin API Key reset successfully!${NC}"
        echo -e "${GREEN}══════════════════════════════════════════════════════════════${NC}"
        echo ""
        echo -e "  New Admin API Key: ${YELLOW}${new_key}${NC}"
        echo ""
        echo -e "${RED}  IMPORTANT:${NC}"
        echo -e "  - This key is shown ONCE. Save it securely now!"
        echo -e "  - The old key is now INVALID"
        echo ""
        echo -e "${GREEN}══════════════════════════════════════════════════════════════${NC}"
    else
        print_error "Failed to reset admin key"
        echo "$result"
        exit 1
    fi
}
```

- [ ] **Step 4: 更新 print_admin_help 函数**

替换 `print_admin_help` 函数（第 1114-1123 行）：

```bash
print_admin_help() {
    echo ""
    echo "Admin commands:"
    echo "  reset        Reset admin API key (old key becomes invalid)"
    echo ""
    echo "Examples:"
    echo "  cyber-pulse.sh admin reset"
    echo ""
    echo "Note: Admin key is generated on first deployment and shown once."
    echo "      If lost, use 'reset' to generate a new key."
}
```

- [ ] **Step 5: 更新 show_help 中的 admin 部分**

修改 `show_help` 函数中的 admin 部分（约第 1169-1171 行）：

```diff
  echo "  admin <subcommand>  管理员操作"
- echo "                      show-key           显示当前 API Key"
- echo "                      rotate-key         生成新的 API Key"
+ echo "                      reset              重置 Admin API Key"
```

- [ ] **Step 6: 运行测试验证通过**

```bash
./tests/test_admin_reset.sh
```

Expected: 所有测试通过

- [ ] **Step 7: 提交**

```bash
git add scripts/cyber-pulse.sh tests/test_admin_reset.sh
git commit -m "refactor(scripts): replace admin show-key/rotate-key with reset

- Remove show-key and rotate-key commands (key no longer in .env)
- Add reset command that generates new key and outputs to terminal
- Admin key reset is done via in-container Python execution
- Add shell test for admin commands"
```

---

## Task 6: 创建 api.sh 管理脚本

**Depends on:** Task 1 (CLI 移除), Task 5 (cyber-pulse.sh admin reset 已实现)

**Files:**
- Create: `scripts/api.sh`
- Test: Shell 脚本功能验证

- [ ] **Step 1: 编写 api.sh 功能测试**

创建测试脚本 `tests/test_api_sh.sh`:

```bash
#!/usr/bin/env bash
# Tests for api.sh script

set -e

SCRIPT_PATH="scripts/api.sh"

echo "Testing api.sh..."

# Test 1: Script exists and is executable
echo -n "  Script exists... "
if [[ -f "$SCRIPT_PATH" ]]; then
    echo "PASS"
else
    echo "FAIL: Script not found"
    exit 1
fi

# Test 2: Script syntax is valid
echo -n "  Syntax check... "
bash -n "$SCRIPT_PATH" && echo "PASS" || { echo "FAIL"; exit 1; }

# Test 3: Has configure command
echo -n "  Has configure command... "
if grep -q "cmd_configure" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL: configure command not found"
    exit 1
fi

# Test 4: Has sources commands
echo -n "  Has sources commands... "
if grep -q "cmd_sources_list\|cmd_sources_get\|cmd_sources_create" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL: sources commands not found"
    exit 1
fi

# Test 5: Has jobs commands
echo -n "  Has jobs commands... "
if grep -q "cmd_jobs_list\|cmd_jobs_run" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL: jobs commands not found"
    exit 1
fi

# Test 6: Has clients commands
echo -n "  Has clients commands... "
if grep -q "cmd_clients_list\|cmd_clients_create" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL: clients commands not found"
    exit 1
fi

# Test 7: Has diagnose command
echo -n "  Has diagnose command... "
if grep -q "cmd_diagnose" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL: diagnose command not found"
    exit 1
fi

# Test 8: Help command works
echo -n "  Help command works... "
if bash "$SCRIPT_PATH" help 2>&1 | grep -q "configure"; then
    echo "PASS"
else
    echo "FAIL: help command not working"
    exit 1
fi

echo "All tests passed!"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
chmod +x tests/test_api_sh.sh
./tests/test_api_sh.sh
```

Expected: 测试失败（脚本不存在）

- [ ] **Step 3: 创建 api.sh 脚本（第一部分：头部和配置）**

```bash
#!/usr/bin/env bash
#
# api.sh - Cyber Pulse API 管理脚本
#
# 功能:
#   配置 API 连接、管理情报源、任务、客户端、日志、诊断
#
# 使用:
#   ./scripts/api.sh configure           # 配置 API URL 和 Admin Key
#   ./scripts/api.sh sources list        # 列出情报源
#   ./scripts/api.sh jobs run <src_id>   # 运行采集任务
#   ./scripts/api.sh diagnose            # 系统诊断
#

set -euo pipefail

# ============================================
# 全局配置
# ============================================

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# 配置文件路径
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/cyber-pulse"
CONFIG_FILE="$CONFIG_DIR/config"

# 默认 API URL
DEFAULT_API_URL="http://localhost:8000"

# ============================================
# 工具函数
# ============================================

print_error() {
    echo -e "${RED}[✗]${NC} $1" >&2
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[i]${NC} $1"
}

die() {
    print_error "$1"
    exit 1
}

# 检查依赖
check_dependencies() {
    local missing=()

    if ! command -v curl &>/dev/null; then
        missing+=("curl")
    fi

    if ! command -v jq &>/dev/null; then
        missing+=("jq")
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        die "Missing dependencies: ${missing[*]}. Please install them first."
    fi
}

# 加载配置
load_config() {
    if [[ ! -f "$CONFIG_FILE" ]]; then
        die "Configuration not found. Run './scripts/api.sh configure' first."
    fi

    # shellcheck source=/dev/null
    source "$CONFIG_FILE"

    if [[ -z "${api_url:-}" ]]; then
        die "api_url not set in config. Run './scripts/api.sh configure' first."
    fi

    if [[ -z "${admin_key:-}" ]]; then
        die "admin_key not set in config. Run './scripts/api.sh configure' first."
    fi
}

# API 请求函数
api_request() {
    local method="$1"
    local endpoint="$2"
    local data="${3:-}"

    local url="${api_url}${endpoint}"
    local args=(-s -X "$method" -H "Authorization: Bearer $admin_key" -H "Content-Type: application/json")

    if [[ -n "$data" ]]; then
        args+=(-d "$data")
    fi

    curl "${args[@]}" "$url"
}

# GET 请求
api_get() {
    api_request "GET" "$1"
}

# POST 请求
api_post() {
    api_request "POST" "$1" "${2:-}"
}

# DELETE 请求
api_delete() {
    api_request "DELETE" "$1"
}

# 检查 API 错误
check_api_error() {
    local response="$1"

    if echo "$response" | jq -e '.detail' &>/dev/null; then
        local detail
        detail=$(echo "$response" | jq -r '.detail')
        die "API error: $detail"
    fi
}
```

- [ ] **Step 2: 添加 configure 命令**

继续添加到 api.sh：

```bash
# ============================================
# Configure 命令
# ============================================

cmd_configure() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           Cyber Pulse API 配置                               ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    # 创建配置目录
    mkdir -p "$CONFIG_DIR"

    # 提示输入 API URL
    echo -e "${BLUE}API URL${NC} (按 Enter 使用默认值: $DEFAULT_API_URL)"
    read -r -p "> " input_api_url
    local final_api_url="${input_api_url:-$DEFAULT_API_URL}"

    # 提示输入 Admin Key
    echo ""
    echo -e "${BLUE}Admin API Key${NC} (格式: cp_live_xxxx)"
    read -r -p "> " input_admin_key

    if [[ -z "$input_admin_key" ]]; then
        die "Admin API Key 不能为空"
    fi

    # 验证 Key 格式
    if [[ ! "$input_admin_key" =~ ^cp_live_[a-f0-9]{32}$ ]]; then
        print_warning "Key 格式可能不正确，预期格式: cp_live_ + 32 位十六进制字符"
    fi

    # 测试连接
    echo ""
    print_info "测试连接..."

    local test_response
    test_response=$(curl -s -H "Authorization: Bearer $input_admin_key" "${final_api_url}/api/v1/admin/diagnose" 2>/dev/null || echo '{"detail":"Connection failed"}')

    if echo "$test_response" | jq -e '.status' &>/dev/null; then
        print_success "连接成功"
    else
        local detail
        detail=$(echo "$test_response" | jq -r '.detail // "Unknown error"')
        print_warning "连接测试失败: $detail"
        echo ""
        read -r -p "仍要保存配置吗? (y/N): " save_anyway
        if [[ ! "$save_anyway" =~ ^[Yy]$ ]]; then
            die "配置已取消"
        fi
    fi

    # 写入配置文件
    cat > "$CONFIG_FILE" << EOF
# Cyber Pulse API Configuration
# Generated by: api.sh configure
# Date: $(date '+%Y-%m-%d %H:%M:%S')

api_url=${final_api_url}
admin_key=${input_admin_key}
EOF

    chmod 600 "$CONFIG_FILE"

    echo ""
    print_success "配置已保存到: $CONFIG_FILE"
    print_info "文件权限: 600"
}

# ============================================
# Sources 命令
# ============================================

cmd_sources() {
    local subcommand="${1:-list}"
    shift || true

    case "$subcommand" in
        list)           cmd_sources_list "$@" ;;
        get)            cmd_sources_get "$@" ;;
        create)         cmd_sources_create "$@" ;;
        update)         cmd_sources_update "$@" ;;
        delete)         cmd_sources_delete "$@" ;;
        *)
            print_error "Unknown sources subcommand: $subcommand"
            print_sources_help
            exit 1
            ;;
    esac
}

cmd_sources_list() {
    local status_filter=""
    local tier_filter=""
    local scheduled_filter=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --status)       status_filter="$2"; shift 2 ;;
            --tier)         tier_filter="$2"; shift 2 ;;
            --scheduled)    scheduled_filter="$2"; shift 2 ;;
            *)              shift ;;
        esac
    done

    local endpoint="/api/v1/admin/sources"
    local params=()

    [[ -n "$status_filter" ]] && params+=("status=$status_filter")
    [[ -n "$tier_filter" ]] && params+=("tier=$tier_filter")
    [[ -n "$scheduled_filter" ]] && params+=("scheduled=$scheduled_filter")

    if [[ ${#params[@]} -gt 0 ]]; then
        endpoint="${endpoint}?$(IFS='&'; echo "${params[*]}")"
    fi

    local response
    response=$(api_get "$endpoint")
    check_api_error "$response"

    echo "$response" | jq -r '
        if .data then
            ["ID", "Name", "Type", "Status", "Tier", "Scheduled"],
            ["--", "----", "----", "------", "----", "---------"],
            (.data[] | [.source_id, .name, .connector_type, .status, .tier, (if .schedule_interval != null then "Yes" else "No" end)])
            | @tsv
        else
            .[]
        end
    ' | column -t -s $'\t'
}

cmd_sources_get() {
    local source_id="${1:-}"

    if [[ -z "$source_id" ]]; then
        die "Usage: api.sh sources get <source_id>"
    fi

    local response
    response=$(api_get "/api/v1/admin/sources/$source_id")
    check_api_error "$response"

    echo "$response" | jq .
}

cmd_sources_create() {
    local name=""
    local connector_type=""
    local url=""
    local tier=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --name)     name="$2"; shift 2 ;;
            --type)     connector_type="$2"; shift 2 ;;
            --url)      url="$2"; shift 2 ;;
            --tier)     tier="$2"; shift 2 ;;
            *)          shift ;;
        esac
    done

    [[ -z "$name" ]] && die "--name is required"
    [[ -z "$connector_type" ]] && die "--type is required"
    [[ -z "$url" ]] && die "--url is required"

    local data=$(jq -n \
        --arg name "$name" \
        --arg type "$connector_type" \
        --arg url "$url" \
        --arg tier "$tier" \
        '{name: $name, connector_type: $type, url: $url} + if $tier != "" then {tier: $tier} else {} end'
    )

    local response
    response=$(api_post "/api/v1/admin/sources" "$data")
    check_api_error "$response"

    print_success "Source created"
    echo "$response" | jq .
}

cmd_sources_update() {
    local source_id="${1:-}"
    shift

    if [[ -z "$source_id" ]]; then
        die "Usage: api.sh sources update <source_id> [options]"
    fi

    local data="{}"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --name)     data=$(echo "$data" | jq --arg v "$2" '. + {name: $v}'); shift 2 ;;
            --url)      data=$(echo "$data" | jq --arg v "$2" '. + {url: $v}'); shift 2 ;;
            --tier)     data=$(echo "$data" | jq --arg v "$2" '. + {tier: $v}'); shift 2 ;;
            --status)   data=$(echo "$data" | jq --arg v "$2" '. + {status: $v}'); shift 2 ;;
            *)          shift ;;
        esac
    done

    local response
    response=$(api_request "PATCH" "/api/v1/admin/sources/$source_id" "$data")
    check_api_error "$response"

    print_success "Source updated"
    echo "$response" | jq .
}

cmd_sources_delete() {
    local source_id="${1:-}"

    if [[ -z "$source_id" ]]; then
        die "Usage: api.sh sources delete <source_id>"
    fi

    local response
    response=$(api_delete "/api/v1/admin/sources/$source_id")

    if [[ -z "$response" ]]; then
        print_success "Source deleted: $source_id"
    else
        check_api_error "$response"
    fi
}

print_sources_help() {
    echo ""
    echo "Sources commands:"
    echo "  list [--status STATUS] [--tier TIER] [--scheduled BOOL]"
    echo "  get <source_id>"
    echo "  create --name NAME --type TYPE --url URL [--tier TIER]"
    echo "  update <source_id> [--name NAME] [--url URL] [--tier TIER] [--status STATUS]"
    echo "  delete <source_id>"
}
```

- [ ] **Step 3: 添加 Jobs、Clients、Logs、Diagnose 命令**

继续添加到 api.sh：

```bash
# ============================================
# Jobs 命令
# ============================================

cmd_jobs() {
    local subcommand="${1:-list}"
    shift || true

    case "$subcommand" in
        list)   cmd_jobs_list "$@" ;;
        get)    cmd_jobs_get "$@" ;;
        run)    cmd_jobs_run "$@" ;;
        *)
            print_error "Unknown jobs subcommand: $subcommand"
            print_jobs_help
            exit 1
            ;;
    esac
}

cmd_jobs_list() {
    local type_filter=""
    local status_filter=""
    local source_filter=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --type)     type_filter="$2"; shift 2 ;;
            --status)   status_filter="$2"; shift 2 ;;
            --source)   source_filter="$2"; shift 2 ;;
            *)          shift ;;
        esac
    done

    local endpoint="/api/v1/admin/jobs"
    local params=()

    [[ -n "$type_filter" ]] && params+=("job_type=$type_filter")
    [[ -n "$status_filter" ]] && params+=("status=$status_filter")
    [[ -n "$source_filter" ]] && params+=("source_id=$source_filter")

    if [[ ${#params[@]} -gt 0 ]]; then
        endpoint="${endpoint}?$(IFS='&'; echo "${params[*]}")"
    fi

    local response
    response=$(api_get "$endpoint")
    check_api_error "$response"

    echo "$response" | jq -r '
        if .data then
            ["ID", "Type", "Status", "Source", "Started", "Items"],
            ["--", "----", "------", "------", "-------", "-----"],
            (.data[] | [.job_id[:20], .job_type, .status, (.source_id[:12] // "-"), (.started_at[:16] // "-"), (.items_processed // 0)])
            | @tsv
        else
            .[]
        end
    ' | column -t -s $'\t'
}

cmd_jobs_get() {
    local job_id="${1:-}"

    if [[ -z "$job_id" ]]; then
        die "Usage: api.sh jobs get <job_id>"
    fi

    local response
    response=$(api_get "/api/v1/admin/jobs/$job_id")
    check_api_error "$response"

    echo "$response" | jq .
}

cmd_jobs_run() {
    local source_id="${1:-}"

    if [[ -z "$source_id" ]]; then
        die "Usage: api.sh jobs run <source_id>"
    fi

    local response
    response=$(api_post "/api/v1/admin/jobs/run" "{\"source_id\": \"$source_id\"}")
    check_api_error "$response"

    print_success "Job started"
    echo "$response" | jq .
}

print_jobs_help() {
    echo ""
    echo "Jobs commands:"
    echo "  list [--type TYPE] [--status STATUS] [--source SOURCE_ID]"
    echo "  get <job_id>"
    echo "  run <source_id>"
}

# ============================================
# Clients 命令
# ============================================

cmd_clients() {
    local subcommand="${1:-list}"
    shift || true

    case "$subcommand" in
        list)       cmd_clients_list "$@" ;;
        get)        cmd_clients_get "$@" ;;
        create)     cmd_clients_create "$@" ;;
        rotate)     cmd_clients_rotate "$@" ;;
        suspend)    cmd_clients_suspend "$@" ;;
        activate)   cmd_clients_activate "$@" ;;
        delete)     cmd_clients_delete "$@" ;;
        *)
            print_error "Unknown clients subcommand: $subcommand"
            print_clients_help
            exit 1
            ;;
    esac
}

cmd_clients_list() {
    local status_filter=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --status)   status_filter="$2"; shift 2 ;;
            *)          shift ;;
        esac
    done

    local endpoint="/api/v1/admin/clients"

    if [[ -n "$status_filter" ]]; then
        endpoint="${endpoint}?status=${status_filter}"
    fi

    local response
    response=$(api_get "$endpoint")
    check_api_error "$response"

    echo "$response" | jq -r '
        if .data then
            ["ID", "Name", "Status", "Permissions", "Created"],
            ["--", "----", "------", "-----------", "-------"],
            (.data[] | [.client_id, .name, .status, (.permissions | join(",")), (.created_at[:10] // "-")])
            | @tsv
        else
            .[]
        end
    ' | column -t -s $'\t'
}

cmd_clients_get() {
    local client_id="${1:-}"

    if [[ -z "$client_id" ]]; then
        die "Usage: api.sh clients get <client_id>"
    fi

    local response
    response=$(api_get "/api/v1/admin/clients/$client_id")
    check_api_error "$response"

    echo "$response" | jq .
}

cmd_clients_create() {
    local name=""
    local permissions=""
    local description=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --name)         name="$2"; shift 2 ;;
            --permissions)  permissions="$2"; shift 2 ;;
            --description)  description="$2"; shift 2 ;;
            *)              shift ;;
        esac
    done

    [[ -z "$name" ]] && die "--name is required"

    local perms_array="[]"
    if [[ -n "$permissions" ]]; then
        perms_array=$(echo "$permissions" | jq -R 'split(",")')
    fi

    local data=$(jq -n \
        --arg name "$name" \
        --argjson perms "$perms_array" \
        --arg desc "$description" \
        '{name: $name, permissions: $perms} + if $desc != "" then {description: $desc} else {} end'
    )

    local response
    response=$(api_post "/api/v1/admin/clients" "$data")
    check_api_error "$response"

    print_success "Client created"
    echo ""
    echo "$response" | jq .
    echo ""
    print_warning "IMPORTANT: Save the API key now - it cannot be retrieved later!"
}

cmd_clients_rotate() {
    local client_id="${1:-}"

    if [[ -z "$client_id" ]]; then
        die "Usage: api.sh clients rotate <client_id>"
    fi

    local response
    response=$(api_post "/api/v1/admin/clients/$client_id/rotate")
    check_api_error "$response"

    print_success "Key rotated"
    echo ""
    echo "$response" | jq .
    echo ""
    print_warning "IMPORTANT: Save the new API key now - old key is invalid!"
}

cmd_clients_suspend() {
    local client_id="${1:-}"

    if [[ -z "$client_id" ]]; then
        die "Usage: api.sh clients suspend <client_id>"
    fi

    local response
    response=$(api_post "/api/v1/admin/clients/$client_id/suspend")
    check_api_error "$response"

    print_success "Client suspended: $client_id"
}

cmd_clients_activate() {
    local client_id="${1:-}"

    if [[ -z "$client_id" ]]; then
        die "Usage: api.sh clients activate <client_id>"
    fi

    local response
    response=$(api_post "/api/v1/admin/clients/$client_id/activate")
    check_api_error "$response"

    print_success "Client activated: $client_id"
}

cmd_clients_delete() {
    local client_id="${1:-}"

    if [[ -z "$client_id" ]]; then
        die "Usage: api.sh clients delete <client_id>"
    fi

    local response
    response=$(api_delete "/api/v1/admin/clients/$client_id")

    if [[ -z "$response" ]]; then
        print_success "Client deleted: $client_id"
    else
        check_api_error "$response"
    fi
}

print_clients_help() {
    echo ""
    echo "Clients commands:"
    echo "  list [--status STATUS]"
    echo "  get <client_id>"
    echo "  create --name NAME [--permissions PERMS] [--description DESC]"
    echo "  rotate <client_id>"
    echo "  suspend <client_id>"
    echo "  activate <client_id>"
    echo "  delete <client_id>"
}

# ============================================
# Logs 命令
# ============================================

cmd_logs() {
    local level=""
    local source_id=""
    local since=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --level)    level="$2"; shift 2 ;;
            --source)   source_id="$2"; shift 2 ;;
            --since)    since="$2"; shift 2 ;;
            *)          shift ;;
        esac
    done

    local endpoint="/api/v1/admin/logs"
    local params=()

    [[ -n "$level" ]] && params+=("level=$level")
    [[ -n "$source_id" ]] && params+=("source_id=$source_id")
    [[ -n "$since" ]] && params+=("since=$since")

    if [[ ${#params[@]} -gt 0 ]]; then
        endpoint="${endpoint}?$(IFS='&'; echo "${params[*]}")"
    fi

    local response
    response=$(api_get "$endpoint")
    check_api_error "$response"

    echo "$response" | jq -r '
        if .data then
            .data[] | "[\(.timestamp[:19])] \(.level | ascii_upcase) \(.message)"
        else
            .[]
        end
    '
}

# ============================================
# Diagnose 命令
# ============================================

cmd_diagnose() {
    local response
    response=$(api_get "/api/v1/admin/diagnose")
    check_api_error "$response"

    echo "$response" | jq .
}

# ============================================
# Items 命令 (content)
# ============================================

cmd_items() {
    local subcommand="${1:-list}"
    shift || true

    case "$subcommand" in
        list)   cmd_items_list "$@" ;;
        get)    cmd_items_get "$@" ;;
        *)
            print_error "Unknown items subcommand: $subcommand"
            print_items_help
            exit 1
            ;;
    esac
}

cmd_items_list() {
    local status_filter=""
    local source_id=""
    local limit="50"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --status)   status_filter="$2"; shift 2 ;;
            --source)   source_id="$2"; shift 2 ;;
            --limit)    limit="$2"; shift 2 ;;
            *)          shift ;;
        esac
    done

    local endpoint="/api/v1/items"
    local params=("limit=$limit")

    [[ -n "$status_filter" ]] && params+=("status=$status_filter")
    [[ -n "$source_id" ]] && params+=("source_id=$source_id")

    endpoint="${endpoint}?$(IFS='&'; echo "${params[*]}")"

    local response
    response=$(api_get "$endpoint")
    check_api_error "$response"

    echo "$response" | jq -r '
        if .data then
            ["ID", "Title", "Status", "Source", "Published"],
            ["--", "-----", "------", "------", "---------"],
            (.data[] | [.item_id[:20], (.title[:40] // "-"), .status, (.source_id[:12] // "-"), (.published_at[:10] // "-")])
            | @tsv
        else
            .[]
        end
    ' | column -t -s $'\t'
}

cmd_items_get() {
    local item_id="${1:-}"

    if [[ -z "$item_id" ]]; then
        die "Usage: api.sh items get <item_id>"
    fi

    local response
    response=$(api_get "/api/v1/items/$item_id")
    check_api_error "$response"

    echo "$response" | jq .
}

print_items_help() {
    echo ""
    echo "Items commands:"
    echo "  list [--status STATUS] [--source SOURCE_ID] [--limit N]"
    echo "  get <item_id>"
}
```

- [ ] **Step 4: 添加帮助和主入口**

继续添加到 api.sh 末尾：

```bash
# ============================================
# 帮助信息
# ============================================

show_help() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           Cyber Pulse API 管理工具                           ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo "用法: api.sh <命令> [选项]"
    echo ""
    echo -e "${BOLD}命令:${NC}"
    echo "  configure              配置 API URL 和 Admin Key"
    echo ""
    echo "  sources <cmd>          情报源管理"
    echo "    list                 列出情报源"
    echo "    get <id>             获取情报源详情"
    echo "    create               创建情报源"
    echo "    update <id>          更新情报源"
    echo "    delete <id>          删除情报源"
    echo ""
    echo "  jobs <cmd>             任务管理"
    echo "    list                 列出任务"
    echo "    get <id>             获取任务详情"
    echo "    run <source_id>      运行采集任务"
    echo ""
    echo "  clients <cmd>          客户端管理"
    echo "    list                 列出客户端"
    echo "    get <id>             获取客户端详情"
    echo "    create               创建客户端"
    echo "    rotate <id>          轮换 API Key"
    echo "    suspend <id>         暂停客户端"
    echo "    activate <id>        激活客户端"
    echo "    delete <id>          删除客户端"
    echo ""
    echo "  items <cmd>            内容管理"
    echo "    list                 列出内容"
    echo "    get <id>             获取内容详情"
    echo ""
    echo "  logs [选项]            查看日志"
    echo "    --level LEVEL        日志级别过滤"
    echo "    --source SOURCE_ID   情报源过滤"
    echo "    --since TIME         时间过滤"
    echo ""
    echo "  diagnose               系统诊断"
    echo ""
    echo -e "${BOLD}配置文件:${NC} $CONFIG_FILE"
    echo -e "${BOLD}示例:${NC}"
    echo "  api.sh configure"
    echo "  api.sh sources list"
    echo "  api.sh jobs run src_xxxx"
    echo "  api.sh diagnose"
}

# ============================================
# 主入口
# ============================================

main() {
    check_dependencies

    local command="${1:-help}"
    shift || true

    case "$command" in
        configure)
            cmd_configure
            ;;
        sources)
            load_config
            cmd_sources "$@"
            ;;
        jobs)
            load_config
            cmd_jobs "$@"
            ;;
        clients)
            load_config
            cmd_clients "$@"
            ;;
        items)
            load_config
            cmd_items "$@"
            ;;
        logs)
            load_config
            cmd_logs "$@"
            ;;
        diagnose)
            load_config
            cmd_diagnose
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            print_error "Unknown command: $command"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

main "$@"
```

- [ ] **Step 6: 设置脚本权限**

```bash
chmod +x scripts/api.sh
```

- [ ] **Step 7: 运行测试验证通过**

```bash
./tests/test_api_sh.sh
```

Expected: 所有测试通过

- [ ] **Step 8: 提交**

```bash
git add scripts/api.sh tests/test_api_sh.sh
git commit -m "feat(scripts): add api.sh management script

Pure Bash script for API management:
- configure: Setup API URL and Admin Key
- sources: CRUD operations for sources
- jobs: List, get, run jobs
- clients: Full client management
- items: Content queries
- logs: Log viewing with filters
- diagnose: System health check

Uses curl + jq, stores config in ~/.config/cyber-pulse/config

Add shell tests for script verification"
```

---

## Task 7: 更新 CLAUDE.md 文档

**Depends on:** Task 6 (api.sh 已创建)

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: 更新常用管理命令部分**

修改 `CLAUDE.md` 中的常用管理命令部分：

```diff
 ### 常用管理命令

-```bash
-./scripts/cyber-pulse.sh status               # 查看状态
-./scripts/cyber-pulse.sh logs                 # 查看日志
-./scripts/cyber-pulse.sh stop                 # 停止服务
-./scripts/cyber-pulse.sh restart              # 重启服务
-```
+```bash
+# 部署管理
+./scripts/cyber-pulse.sh status               # 查看状态
+./scripts/cyber-pulse.sh logs                 # 查看日志
+./scripts/cyber-pulse.sh stop                 # 停止服务
+./scripts/cyber-pulse.sh restart              # 重启服务
+
+# API 管理（首次使用需先配置）
+./scripts/api.sh configure                    # 配置 API URL 和 Admin Key
+./scripts/api.sh sources list                 # 列出情报源
+./scripts/api.sh jobs run src_xxx             # 运行采集任务
+./scripts/api.sh clients list                 # 列出客户端
+./scripts/api.sh diagnose                     # 系统诊断
+```
```

- [ ] **Step 2: 移除 CLI 相关命令**

删除文档中的 CLI 命令部分：

```diff
 ### 开发常用命令

 ```bash
 # 测试
 uv run pytest                           # 全部测试
 uv run pytest tests/test_services/ -v   # 特定目录

 # 代码检查
 uv run ruff check src/ tests/           # Lint
 uv run mypy src/ --ignore-missing-imports  # 类型检查

 # 数据库
 uv run alembic upgrade head             # 迁移
 uv run alembic revision --autogenerate -m "description"  # 创建迁移

-# CLI
-uv run cyber-pulse --help               # CLI 帮助
-uv run cyber-pulse diagnose system      # 系统健康检查
-uv run cyber-pulse diagnose errors      # 错误分析
-uv run cyber-pulse log tail             # 实时查看日志
 ```
```

- [ ] **Step 2: 验证文档更新**

```bash
# 检查 CLI 命令已移除
grep -q "cyber-pulse --help" CLAUDE.md && echo "FAIL: CLI 命令仍存在" || echo "PASS"

# 检查 api.sh 命令已添加
grep -q "api.sh configure" CLAUDE.md && echo "PASS" || echo "FAIL: api.sh 命令未添加"
```

Expected: 全部 PASS

- [ ] **Step 3: 提交**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for CLI removal

- Replace CLI commands with api.sh script commands
- Update common management commands section"
```

---

## Task 8: 基本验证

**Depends on:** Task 1-7 (所有前置任务完成)

- [ ] **Step 1: 验证 CLI 完全移除**

```bash
# 检查 CLI 目录不存在
ls src/cyberpulse/cli/ 2>/dev/null && echo "FAIL" || echo "PASS"

# 检查 pyproject.toml 中无 CLI 入口
grep "cyberpulse.cli" pyproject.toml && echo "FAIL" || echo "PASS"

# 检查 CLI 依赖已移除
grep -E "typer|rich|prompt-toolkit" pyproject.toml && echo "FAIL" || echo "PASS"
```

Expected: 全部 PASS

- [ ] **Step 2: 验证 api.sh 功能**

```bash
# 检查脚本存在且可执行
test -x scripts/api.sh && echo "PASS" || echo "FAIL"

# 检查帮助命令
./scripts/api.sh help | grep -q "configure" && echo "PASS" || echo "FAIL"
```

Expected: 全部 PASS

- [ ] **Step 3: 运行所有测试**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: 所有测试通过

- [ ] **Step 4: 提交验证结果**

```bash
git add -A
git status
```

确认没有未跟踪或未提交的文件。

---

## Task 9: 创建运维部署包构建脚本

**Depends on:** Task 6 (api.sh 已创建), Task 8 (基本验证通过)

**Files:**
- Create: `scripts/build-deploy-package.sh`
- Test: Shell 脚本功能验证

**背景:** 设计文档要求支持用户分离：开发者获取完整代码库，运维人员仅获取部署管理包。

- [ ] **Step 1: 编写构建脚本测试**

创建测试脚本 `tests/test_build_deploy_package.sh`:

```bash
#!/usr/bin/env bash
# Tests for build-deploy-package.sh

set -e

SCRIPT_PATH="scripts/build-deploy-package.sh"

echo "Testing build-deploy-package.sh..."

# Test 1: Script exists
echo -n "  Script exists... "
if [[ -f "$SCRIPT_PATH" ]]; then
    echo "PASS"
else
    echo "FAIL"
    exit 1
fi

# Test 2: Script is executable
echo -n "  Script is executable... "
if [[ -x "$SCRIPT_PATH" ]]; then
    echo "PASS"
else
    echo "FAIL"
    exit 1
fi

# Test 3: Script syntax valid
echo -n "  Syntax check... "
bash -n "$SCRIPT_PATH" && echo "PASS" || { echo "FAIL"; exit 1; }

# Test 4: Has required functions
echo -n "  Has check_required_files... "
grep -q "check_required_files" "$SCRIPT_PATH" && echo "PASS" || { echo "FAIL"; exit 1; }

echo -n "  Has create_archive... "
grep -q "create_archive" "$SCRIPT_PATH" && echo "PASS" || { echo "FAIL"; exit 1; }

# Test 5: Excludes src/ tests/ docs/
echo -n "  Excludes src/ from package... "
if grep -q "src/" "$SCRIPT_PATH" && ! grep -q '"src/' "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL: src/ might be included"
    exit 1
fi

echo "All tests passed!"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
chmod +x tests/test_build_deploy_package.sh
./tests/test_build_deploy_package.sh
```

Expected: 测试失败（脚本不存在）

- [ ] **Step 3: 创建 build-deploy-package.sh 脚本**

```bash
#!/usr/bin/env bash
#
# build-deploy-package.sh - 构建运维部署包
#
# 功能:
#   从完整代码库中提取运维人员所需的部署文件，生成轻量级部署包
#
# 使用:
#   ./scripts/build-deploy-package.sh [--version VERSION]
#
# 输出:
#   cyber-pulse-deploy-{VERSION}.tar.gz
#

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 默认版本号
VERSION="${1:-}"

# 输出文件名
if [[ -n "$VERSION" ]]; then
    OUTPUT_FILE="cyber-pulse-deploy-${VERSION}.tar.gz"
else
    OUTPUT_FILE="cyber-pulse-deploy-$(date +%Y%m%d%H%M%S).tar.gz"
fi

# 部署包包含的文件
DEPLOY_FILES=(
    "scripts/cyber-pulse.sh"
    "scripts/api.sh"
    "deploy/"
    "sources.yaml"
    "install-ops.sh"
)

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# 检查必需文件
check_required_files() {
    print_info "检查必需文件..."

    local missing=()
    for file in "${DEPLOY_FILES[@]}"; do
        if [[ ! -e "$PROJECT_ROOT/$file" ]] && [[ "$file" != "install-ops.sh" ]]; then
            missing+=("$file")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        print_error "缺少必需文件: ${missing[*]}"
        exit 1
    fi

    print_success "所有必需文件存在"
}

# 创建临时目录
create_temp_dir() {
    TEMP_DIR=$(mktemp -d)
    trap "rm -rf $TEMP_DIR" EXIT
    print_info "临时目录: $TEMP_DIR"
}

# 复制文件到临时目录
copy_files() {
    print_info "复制部署文件..."

    mkdir -p "$TEMP_DIR/cyber-pulse"

    for file in "${DEPLOY_FILES[@]}"; do
        if [[ -e "$PROJECT_ROOT/$file" ]]; then
            # 创建父目录
            parent_dir=$(dirname "$file")
            if [[ "$parent_dir" != "." ]]; then
                mkdir -p "$TEMP_DIR/cyber-pulse/$parent_dir"
            fi
            cp -r "$PROJECT_ROOT/$file" "$TEMP_DIR/cyber-pulse/$file"
        fi
    done

    # 创建 sources.yaml 示例文件（如果不存在）
    if [[ ! -f "$TEMP_DIR/cyber-pulse/sources.yaml" ]]; then
        cat > "$TEMP_DIR/cyber-pulse/sources.yaml" << 'EOF'
# Cyber Pulse 情报源配置
# 格式参考: docs/source-config-examples.md

sources: []
EOF
    fi

    print_success "文件复制完成"
}

# 创建 install-ops.sh（运维安装脚本）
create_install_ops() {
    print_info "创建运维安装脚本..."

    cat > "$TEMP_DIR/cyber-pulse/install-ops.sh" << 'INSTALL_SCRIPT'
#!/usr/bin/env bash
#
# Cyber Pulse 运维安装脚本
# 用于从部署包安装（非 git clone 方式）
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

INSTALL_DIR="${1:-cyber-pulse}"

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

main() {
    echo ""
    echo "========================================"
    echo "   Cyber Pulse 运维安装"
    echo "========================================"
    echo ""

    # 检查当前目录是否为部署包目录
    if [[ ! -f "scripts/cyber-pulse.sh" ]]; then
        error "请在部署包根目录运行此脚本"
        exit 1
    fi

    info "安装目录: $INSTALL_DIR"

    # 如果指定了不同的安装目录，复制文件
    if [[ "$INSTALL_DIR" != "." ]] && [[ "$INSTALL_DIR" != "cyber-pulse" ]]; then
        info "复制文件到 $INSTALL_DIR..."
        mkdir -p "$INSTALL_DIR"
        cp -r scripts deploy sources.yaml "$INSTALL_DIR/" 2>/dev/null || true
        cd "$INSTALL_DIR"
    fi

    # 检查依赖
    info "检查依赖..."
    local missing=()

    command -v docker &>/dev/null || missing+=("docker")
    command -v docker-compose &>/dev/null || command -v docker &>/dev/null && docker compose version &>/dev/null || missing+=("docker-compose")
    command -v curl &>/dev/null || missing+=("curl")
    command -v jq &>/dev/null || missing+=("jq")

    if [[ ${#missing[@]} -gt 0 ]]; then
        error "缺少依赖: ${missing[*]}"
        echo ""
        echo "安装依赖:"
        echo "  Docker:       https://docs.docker.com/get-docker/"
        echo "  Docker Compose: https://docs.docker.com/compose/install/"
        echo "  curl:         通常已预装"
        echo "  jq:           apt install jq / brew install jq"
        exit 1
    fi

    success "依赖检查通过"

    # 设置脚本权限
    chmod +x scripts/cyber-pulse.sh scripts/api.sh

    echo ""
    success "安装完成!"
    echo ""
    echo "下一步操作:"
    echo ""
    echo "  1. 部署服务:"
    echo "     ./scripts/cyber-pulse.sh deploy --env prod"
    echo ""
    echo "  2. 配置管理脚本:"
    echo "     ./scripts/api.sh configure"
    echo ""
    echo "  3. 管理命令:"
    echo "     ./scripts/api.sh diagnose"
    echo "     ./scripts/api.sh sources list"
    echo ""
}

main "$@"
INSTALL_SCRIPT

    chmod +x "$TEMP_DIR/cyber-pulse/install-ops.sh"
    print_success "运维安装脚本创建完成"
}

# 创建 README
create_readme() {
    print_info "创建部署包 README..."

    cat > "$TEMP_DIR/cyber-pulse/README.md" << 'EOF'
# Cyber Pulse 部署包

本部署包仅包含运维部署所需的文件，不包含源代码和测试文件。

## 目录结构

```
cyber-pulse/
├── scripts/
│   ├── cyber-pulse.sh      # 部署脚本
│   └── api.sh              # API 管理脚本
├── deploy/
│   ├── docker-compose.yml
│   └── init/
├── sources.yaml            # 情报源配置
├── install-ops.sh          # 运维安装脚本
└── README.md
```

## 快速开始

### 1. 安装

```bash
./install-ops.sh
```

### 2. 部署

```bash
./scripts/cyber-pulse.sh deploy --env prod
```

### 3. 配置 API 管理

```bash
./scripts/api.sh configure
```

### 4. 日常管理

```bash
./scripts/api.sh diagnose        # 系统诊断
./scripts/api.sh sources list    # 情报源列表
./scripts/api.sh jobs run src_xxx  # 运行采集
```

## 注意事项

- Admin API Key 在首次部署时自动生成并输出到终端
- 请妥善保存 Admin Key，忘记后需使用 `admin reset` 重置
- 详细文档: https://github.com/cyberstrat-forge/cyber-pulse
EOF

    print_success "README 创建完成"
}

# 打包
create_archive() {
    print_info "创建部署包..."

    cd "$TEMP_DIR"
    tar -czf "$PROJECT_ROOT/$OUTPUT_FILE" cyber-pulse

    local size
    size=$(du -h "$PROJECT_ROOT/$OUTPUT_FILE" | cut -f1)

    print_success "部署包创建完成: $OUTPUT_FILE ($size)"
}

# 显示完成信息
show_completion() {
    echo ""
    echo "========================================"
    print_success "部署包构建完成!"
    echo "========================================"
    echo ""
    echo "输出文件: $OUTPUT_FILE"
    echo ""
    echo "运维人员安装方式:"
    echo ""
    echo "  1. 下载部署包"
    echo "  2. 解压: tar -xzf $OUTPUT_FILE"
    echo "  3. 进入目录: cd cyber-pulse"
    echo "  4. 安装: ./install-ops.sh"
    echo ""
}

# 主函数
main() {
    echo ""
    echo "========================================"
    echo "   Cyber Pulse 部署包构建"
    echo "========================================"
    echo ""

    check_required_files
    create_temp_dir
    copy_files
    create_install_ops
    create_readme
    create_archive
    show_completion
}

main
```

- [ ] **Step 4: 设置脚本权限**

```bash
chmod +x scripts/build-deploy-package.sh
```

- [ ] **Step 5: 运行测试验证通过**

```bash
./tests/test_build_deploy_package.sh
```

Expected: 所有测试通过

- [ ] **Step 6: 提交**

```bash
git add scripts/build-deploy-package.sh tests/test_build_deploy_package.sh
git commit -m "feat(scripts): add build-deploy-package.sh for ops package

Creates lightweight deployment package containing:
- scripts/cyber-pulse.sh (deployment)
- scripts/api.sh (API management)
- deploy/ directory
- install-ops.sh (ops installation script)
- README.md

Excludes src/, tests/, docs/ for ops personnel

Add shell tests for script verification"
```

---

## Task 10: 修改 install.sh 支持用户分离

**Depends on:** Task 9 (build-deploy-package.sh 已创建)

**Files:**
- Modify: `install.sh`
- Test: Shell 脚本功能验证

**背景:** 设计文档要求开发者使用 `git clone`，运维人员使用轻量部署包。现有 install.sh 不支持用户类型选择。

- [ ] **Step 1: 编写用户分离测试**

创建测试脚本 `tests/test_install_user_types.sh`:

```bash
#!/usr/bin/env bash
# Tests for install.sh user type separation

set -e

SCRIPT_PATH="install.sh"

echo "Testing install.sh user types..."

# Test 1: Script syntax valid
echo -n "  Syntax check... "
bash -n "$SCRIPT_PATH" && echo "PASS" || { echo "FAIL"; exit 1; }

# Test 2: Has --type option
echo -n "  Has --type option... "
if grep -q "\-\-type\|USER_TYPE" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL: --type option not found"
    exit 1
fi

# Test 3: Has developer mode
echo -n "  Has developer mode... "
if grep -q "developer" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL: developer mode not found"
    exit 1
fi

# Test 4: Has ops mode
echo -n "  Has ops mode... "
if grep -q "ops" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL: ops mode not found"
    exit 1
fi

# Test 5: Has install_ops_package function
echo -n "  Has install_ops_package function... "
if grep -q "install_ops_package" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL: install_ops_package function not found"
    exit 1
fi

echo "All tests passed!"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
chmod +x tests/test_install_user_types.sh
./tests/test_install_user_types.sh
```

Expected: 测试失败（--type 选项不存在）

- [ ] **Step 3: 添加用户类型选项**

修改 `install.sh`，在 `parse_args` 函数中添加 `--type` 选项：

```bash
# 在 parse_args 函数开头添加
USER_TYPE="developer"  # developer 或 ops

# 在 while 循环中添加
            --type)
                USER_TYPE="$2"
                shift 2
                ;;
```

完整修改后的 `parse_args` 函数：

```bash
parse_args() {
    INSTALL_DIR="$DEFAULT_DIR"
    VERSION=""
    BRANCH="$DEFAULT_BRANCH"
    USER_TYPE="developer"  # developer 或 ops

    while [[ $# -gt 0 ]]; do
        case $1 in
            -d|--dir)
                INSTALL_DIR="$2"
                shift 2
                ;;
            -v|--version)
                VERSION="$2"
                shift 2
                ;;
            -b|--branch)
                BRANCH="$2"
                shift 2
                ;;
            --type)
                USER_TYPE="$2"
                shift 2
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                error "未知选项: $1"
                echo ""
                show_help
                exit 1
                ;;
        esac
    done
}
```

- [ ] **Step 2: 更新帮助信息**

修改 `show_help` 函数：

```bash
show_help() {
    cat << EOF
Cyber Pulse 一键安装脚本

用法:
  $0 [选项]

选项:
  -d, --dir DIR       安装目录 (默认: ${DEFAULT_DIR})
  -v, --version TAG   安装指定版本标签 (如: v1.2.0)
  -b, --branch BRANCH 安装指定分支 (默认: ${DEFAULT_BRANCH})
  --type TYPE         用户类型: developer 或 ops (默认: developer)
                      - developer: 完整代码库 (git clone)
                      - ops: 仅部署文件 (轻量级)
  -h, --help          显示此帮助信息

示例:
  # 开发者安装（默认）- 获取完整代码库
  $0

  # 运维人员安装 - 仅获取部署文件
  $0 --type ops

  # 安装到指定目录
  $0 --dir /opt/cyber-pulse

  # 安装指定版本
  $0 --version v1.2.0

更多信息请访问: https://github.com/cyberstrat-forge/cyber-pulse
EOF
}
```

- [ ] **Step 5: 添加运维人员安装函数**

在 `switch_version` 函数后添加：

```bash
# 运维人员安装（下载轻量部署包）
install_ops_package() {
    info "运维模式: 下载部署包..."

    local download_url
    if [[ -n "${VERSION}" ]]; then
        download_url="https://github.com/cyberstrat-forge/cyber-pulse/releases/download/${VERSION}/cyber-pulse-deploy-${VERSION}.tar.gz"
    else
        download_url="https://github.com/cyberstrat-forge/cyber-pulse/releases/latest/download/cyber-pulse-deploy-latest.tar.gz"
    fi

    info "下载地址: ${download_url}"

    # 下载部署包
    local temp_file="/tmp/cyber-pulse-deploy.tar.gz"
    if ! curl -fsSL "${download_url}" -o "${temp_file}"; then
        error "下载部署包失败"
        echo ""
        echo "可能的原因:"
        echo "  1. 版本不存在"
        echo "  2. 网络问题"
        echo ""
        echo "请尝试使用开发者模式: $0 --type developer"
        exit 1
    fi

    # 解压
    info "解压部署包..."
    mkdir -p "${INSTALL_DIR}"
    if ! tar -xzf "${temp_file}" -C "$(dirname "${INSTALL_DIR}")"; then
        error "解压失败"
        rm -f "${temp_file}"
        exit 1
    fi

    # 清理临时文件
    rm -f "${temp_file}"

    success "部署包安装完成"
}
```

- [ ] **Step 6: 修改 main 函数支持用户类型**

修改 `main` 函数：

```bash
main() {
    echo ""
    echo "========================================"
    echo "   Cyber Pulse 安装脚本"
    echo "========================================"
    echo ""

    parse_args "$@"
    check_dependencies

    if [[ "${USER_TYPE}" == "ops" ]]; then
        # 运维人员安装
        check_directory
        install_ops_package
    else
        # 开发者安装
        check_directory
        clone_repository
        switch_version
    fi

    show_completion
}
```

- [ ] **Step 7: 更新完成信息**

修改 `show_completion` 函数，支持不同用户类型：

```bash
show_completion() {
    local install_path
    install_path="$(cd "${INSTALL_DIR}" 2>/dev/null && pwd)" || install_path="${INSTALL_DIR}"

    echo ""
    echo "========================================"
    success "Cyber Pulse 安装完成!"
    echo "========================================"
    echo ""
    echo "安装位置: ${install_path}"
    echo "用户类型: ${USER_TYPE}"
    echo ""
    echo "下一步操作:"
    echo ""

    if [[ "${USER_TYPE}" == "ops" ]]; then
        echo "  1. 进入项目目录:"
        echo "     cd ${INSTALL_DIR}"
        echo ""
        echo "  2. 部署服务:"
        echo "     ./scripts/cyber-pulse.sh deploy --env prod"
        echo ""
        echo "  3. 配置 API 管理:"
        echo "     ./scripts/api.sh configure"
        echo ""
    else
        echo "  1. 进入项目目录:"
        echo "     cd ${INSTALL_DIR}"
        echo ""
        echo "  2. 开发环境部署（本地构建）:"
        echo "     ./scripts/cyber-pulse.sh deploy --env dev --local"
        echo ""
        echo "  3. 测试环境部署（本地构建）:"
        echo "     ./scripts/cyber-pulse.sh deploy --env test --local"
        echo ""
        echo "  4. 生产环境部署（远程镜像）:"
        echo "     ./scripts/cyber-pulse.sh deploy --env prod"
        echo ""
    fi

    echo "API 管理:"
    echo "  ./scripts/api.sh configure       # 配置 API"
    echo "  ./scripts/api.sh diagnose         # 系统诊断"
    echo "  ./scripts/api.sh sources list     # 情报源列表"
    echo ""
    echo "详细文档: https://github.com/cyberstrat-forge/cyber-pulse#readme"
    echo ""
}
```

- [ ] **Step 8: 运行测试验证通过**

```bash
./tests/test_install_user_types.sh
```

Expected: 所有测试通过

- [ ] **Step 9: 提交**

```bash
git add install.sh tests/test_install_user_types.sh
git commit -m "feat(install): add user type separation support

- Add --type option (developer/ops)
- developer: full git clone (default)
- ops: lightweight deployment package download
- Update help and completion messages for both user types
- Add shell tests for user type options"
```

---

## Task 11: api.sh 高级 Sources 命令

**Depends on:** Task 6 (api.sh 基础命令), Task 10 (install.sh 用户分离)

**Files:**
- Modify: `scripts/api.sh`
- Test: Shell 脚本功能验证

**背景:** 设计文档列出 sources 高级命令（test, schedule, import, export, defaults），需要添加到 api.sh。这些命令依赖对应的 API 端点实现。

- [ ] **Step 1: 编写高级命令测试**

更新测试脚本 `tests/test_api_sh.sh`，添加高级命令测试：

```bash
# 在 tests/test_api_sh.sh 末尾添加

# Test 9: Has sources test command
echo -n "  Has sources test command... "
if grep -q "cmd_sources_test" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL: sources test command not found"
    exit 1
fi

# Test 10: Has sources schedule command
echo -n "  Has sources schedule command... "
if grep -q "cmd_sources_schedule\|cmd_sources_unschedule" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL: sources schedule commands not found"
    exit 1
fi

# Test 11: Has sources import/export commands
echo -n "  Has sources import/export commands... "
if grep -q "cmd_sources_import\|cmd_sources_export" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL: sources import/export commands not found"
    exit 1
fi

# Test 12: Has sources defaults commands
echo -n "  Has sources defaults commands... "
if grep -q "cmd_sources_defaults\|cmd_sources_set_defaults" "$SCRIPT_PATH"; then
    echo "PASS"
else
    echo "FAIL: sources defaults commands not found"
    exit 1
fi
```

- [ ] **Step 2: 运行测试验证失败**

```bash
./tests/test_api_sh.sh
```

Expected: 高级命令测试失败

- [ ] **Step 3: 更新 cmd_sources case 语句**

修改 `cmd_sources` 函数，添加新命令：

```bash
cmd_sources() {
    local subcommand="${1:-list}"
    shift || true

    case "$subcommand" in
        list)           cmd_sources_list "$@" ;;
        get)            cmd_sources_get "$@" ;;
        create)         cmd_sources_create "$@" ;;
        update)         cmd_sources_update "$@" ;;
        delete)         cmd_sources_delete "$@" ;;
        test)           cmd_sources_test "$@" ;;
        schedule)       cmd_sources_schedule "$@" ;;
        unschedule)     cmd_sources_unschedule "$@" ;;
        import)         cmd_sources_import "$@" ;;
        export)         cmd_sources_export "$@" ;;
        defaults)       cmd_sources_defaults "$@" ;;
        set-defaults)   cmd_sources_set_defaults "$@" ;;
        *)
            print_error "Unknown sources subcommand: $subcommand"
            print_sources_help
            exit 1
            ;;
    esac
}
```

- [ ] **Step 4: 添加 test 命令**

在 `cmd_sources_delete` 函数后添加：

```bash
cmd_sources_test() {
    local source_id="${1:-}"

    if [[ -z "$source_id" ]]; then
        die "Usage: api.sh sources test <source_id>"
    fi

    print_info "Testing source: $source_id"

    local response
    response=$(api_post "/api/v1/admin/sources/${source_id}/test")
    check_api_error "$response"

    local test_result
    test_result=$(echo "$response" | jq -r '.test_result')

    if [[ "$test_result" == "success" ]]; then
        print_success "Source test passed"
        echo ""
        echo "$response" | jq '{
            source_id,
            test_result,
            response_time_ms,
            items_found,
            last_modified
        }'
    else
        print_error "Source test failed"
        echo ""
        echo "$response" | jq '{
            source_id,
            test_result,
            error_type,
            error_message,
            suggestion
        }'
    fi
}
```

- [ ] **Step 5: 添加 schedule/unschedule 命令**

```bash
cmd_sources_schedule() {
    local source_id="${1:-}"
    local interval=""

    shift
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --interval)  interval="$2"; shift 2 ;;
            *)           shift ;;
        esac
    done

    if [[ -z "$source_id" ]]; then
        die "Usage: api.sh sources schedule <source_id> --interval SECONDS"
    fi

    if [[ -z "$interval" ]]; then
        die "Please specify --interval SECONDS (minimum 300)"
    fi

    local data="{\"interval\": ${interval}}"

    local response
    response=$(api_post "/api/v1/admin/sources/${source_id}/schedule" "$data")
    check_api_error "$response"

    print_success "Schedule set for $source_id"
    echo "$response" | jq .
}

cmd_sources_unschedule() {
    local source_id="${1:-}"

    if [[ -z "$source_id" ]]; then
        die "Usage: api.sh sources unschedule <source_id>"
    fi

    local response
    response=$(api_delete "/api/v1/admin/sources/${source_id}/schedule")
    check_api_error "$response"

    print_success "Schedule removed for $source_id"
    echo "$response" | jq .
}
```

- [ ] **Step 6: 添加 import/export 命令**

```bash
cmd_sources_import() {
    local file=""
    local skip_invalid="false"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --file)         file="$2"; shift 2 ;;
            --skip-invalid) skip_invalid="true"; shift ;;
            *)              shift ;;
        esac
    done

    if [[ -z "$file" ]]; then
        die "Usage: api.sh sources import --file FILE.opml [--skip-invalid]"
    fi

    if [[ ! -f "$file" ]]; then
        die "File not found: $file"
    fi

    print_info "Importing sources from: $file"

    # 使用 curl 上传文件
    local response
    response=$(curl -s -X POST \
        -H "Authorization: Bearer $admin_key" \
        -F "file=@${file}" \
        -F "skip_invalid=${skip_invalid}" \
        "${api_url}/api/v1/admin/sources/import")

    check_api_error "$response"

    local job_id
    job_id=$(echo "$response" | jq -r '.job_id')

    print_success "Import job created: $job_id"
    echo ""
    echo "Check job status with:"
    echo "  ./scripts/api.sh jobs get $job_id"
}

cmd_sources_export() {
    local output_file="${1:-sources-export.yaml}"

    print_info "Exporting sources..."

    local response
    response=$(api_get "/api/v1/admin/sources/export")
    check_api_error "$response"

    echo "$response" > "$output_file"
    print_success "Sources exported to: $output_file"
}
```

- [ ] **Step 7: 添加 defaults/set-defaults 命令**

```bash
cmd_sources_defaults() {
    local response
    response=$(api_get "/api/v1/admin/sources/defaults")
    check_api_error "$response"

    echo "Default fetch interval settings:"
    echo "$response" | jq .
}

cmd_sources_set_defaults() {
    local interval=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --interval)  interval="$2"; shift 2 ;;
            *)           shift ;;
        esac
    done

    if [[ -z "$interval" ]]; then
        die "Usage: api.sh sources set-defaults --interval SECONDS"
    fi

    local data="{\"default_fetch_interval\": ${interval}}"

    local response
    response=$(api_request "PATCH" "/api/v1/admin/sources/defaults" "$data")
    check_api_error "$response"

    print_success "Default fetch interval updated"
    echo "$response" | jq .
}
```

- [ ] **Step 8: 更新 print_sources_help**

```bash
print_sources_help() {
    echo ""
    echo "Sources commands:"
    echo "  list [--status STATUS] [--tier TIER] [--scheduled BOOL]"
    echo "  get <source_id>"
    echo "  create --name NAME --type TYPE --url URL [--tier TIER]"
    echo "  update <source_id> [--name NAME] [--url URL] [--tier TIER] [--status STATUS]"
    echo "  delete <source_id>"
    echo ""
    echo "  test <source_id>                          测试源连接"
    echo "  schedule <source_id> --interval SECONDS   设置采集调度"
    echo "  unschedule <source_id>                    取消采集调度"
    echo ""
    echo "  import --file FILE.opml [--skip-invalid]  批量导入"
    echo "  export [OUTPUT_FILE]                      导出源配置"
    echo ""
    echo "  defaults                                  查看默认配置"
    echo "  set-defaults --interval SECONDS           设置默认采集间隔"
}
```

- [ ] **Step 9: 更新 show_help 中的 sources 部分**

修改 `show_help` 函数中的 sources 部分：

```bash
    echo "  sources <cmd>          情报源管理"
    echo "    list                 列出情报源"
    echo "    get <id>             获取情报源详情"
    echo "    create               创建情报源"
    echo "    update <id>          更新情报源"
    echo "    delete <id>          删除情报源"
    echo "    test <id>            测试连接"
    echo "    schedule <id>        设置调度"
    echo "    unschedule <id>      取消调度"
    echo "    import --file FILE   批量导入"
    echo "    export               导出配置"
    echo "    defaults             默认配置"
```

- [ ] **Step 10: 运行测试验证通过**

```bash
./tests/test_api_sh.sh
```

Expected: 所有测试通过

- [ ] **Step 11: 提交**

```bash
git add scripts/api.sh tests/test_api_sh.sh
git commit -m "feat(scripts): add advanced sources commands to api.sh

Add sources commands:
- test <id>: Test source connectivity
- schedule/unschedule <id>: Manage collection schedule
- import --file FILE: OPML batch import
- export: Export source configuration
- defaults/set-defaults: Manage default settings

These commands require corresponding API endpoints to be implemented.

Update shell tests with advanced command verification"
```

---

## Task 12: 完整验证测试

**Depends on:** Task 1-11 (所有前置任务完成)

- [ ] **Step 1: 验证 CLI 完全移除**

```bash
# 检查 CLI 目录不存在
ls src/cyberpulse/cli/ 2>/dev/null && echo "FAIL" || echo "PASS"

# 检查 pyproject.toml 中无 CLI 入口
grep "cyberpulse.cli" pyproject.toml && echo "FAIL" || echo "PASS"

# 检查 CLI 依赖已移除
grep -E "typer|rich|prompt-toolkit" pyproject.toml && echo "FAIL" || echo "PASS"
```

Expected: 全部 PASS

- [ ] **Step 2: 验证 api.sh 所有命令**

```bash
# 检查脚本存在且可执行
test -x scripts/api.sh && echo "PASS" || echo "FAIL"

# 检查帮助命令
./scripts/api.sh help | grep -q "configure" && echo "PASS" || echo "FAIL"

# 检查高级命令存在
./scripts/api.sh help | grep -q "schedule" && echo "PASS" || echo "FAIL"
./scripts/api.sh help | grep -q "import" && echo "PASS" || echo "FAIL"
```

Expected: 全部 PASS

- [ ] **Step 3: 验证构建脚本**

```bash
# 检查构建脚本存在
test -x scripts/build-deploy-package.sh && echo "PASS" || echo "FAIL"

# 检查构建脚本语法
bash -n scripts/build-deploy-package.sh && echo "PASS" || echo "FAIL"
```

Expected: 全部 PASS

- [ ] **Step 4: 验证安装脚本更新**

```bash
# 检查 --type 选项
grep -q "\-\-type" install.sh && echo "PASS" || echo "FAIL"

# 检查 ops 相关函数
grep -q "install_ops_package" install.sh && echo "PASS" || echo "FAIL"
```

Expected: 全部 PASS

- [ ] **Step 5: 运行测试**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: 所有测试通过

- [ ] **Step 6: 提交最终验证**

```bash
git add -A
git status
```

确认没有未跟踪或未提交的文件。

---

## 验证清单（设计文档对照）

| 设计文档要求 | 实现任务 | TDD 测试 | 状态 |
|-------------|---------|---------|------|
| CLI 完全移除 | Task 1 | tests/test_cli_removal.py | ✅ |
| Admin Key 数据库存储 | Task 2, 3 | tests/test_startup.py, tests/test_api_auth.py | ✅ |
| Admin Key 首次部署输出 | Task 2 | tests/test_startup.py | ✅ |
| Admin reset 命令 | Task 5 | tests/test_admin_reset.sh | ✅ |
| api.sh 基本命令 | Task 6 | tests/test_api_sh.sh | ✅ |
| api.sh 高级命令 | Task 11 | tests/test_api_sh.sh (扩展) | ✅ |
| generate-env.sh 移除 ADMIN_API_KEY | Task 4 | tests/test_generate_env.sh | ✅ |
| 文档更新 | Task 7 | 文档验证 | ✅ |
| build-deploy-package.sh | Task 9 | tests/test_build_deploy_package.sh | ✅ |
| install.sh 用户分离 | Task 10 | tests/test_install_user_types.sh | ✅ |
| 完整验证测试 | Task 12 | 所有测试 + 集成验证 | ✅ |