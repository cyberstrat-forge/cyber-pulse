"""
PostgreSQL 测试配置

使用环境变量 TEST_DATABASE_URL 配置测试数据库。
优先级：
1. TEST_DATABASE_URL 环境变量
2. deploy/.env 中的 POSTGRES_* 配置（转换为 localhost）
3. 默认值 postgresql://cyberpulse:cyberpulse123@localhost:5432/cyberpulse_test
"""

import os
from pathlib import Path


def load_deploy_env() -> dict:
    """从 deploy/.env 加载配置。"""
    deploy_env_path = Path(__file__).parent.parent / "deploy" / ".env"
    env_vars = {}
    if deploy_env_path.exists():
        with open(deploy_env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    # 剥离引号（支持单引号和双引号）
                    value = value.strip().strip('"').strip("'")
                    env_vars[key] = value
    return env_vars


def get_test_database_url() -> str:
    """获取测试数据库 URL。"""
    # 1. 直接使用环境变量
    if os.environ.get("TEST_DATABASE_URL"):
        return os.environ["TEST_DATABASE_URL"]

    # 2. 从 deploy/.env 读取并转换为 localhost
    deploy_env = load_deploy_env()
    if deploy_env.get("POSTGRES_USER") and deploy_env.get("POSTGRES_PASSWORD"):
        return (
            f"postgresql://{deploy_env['POSTGRES_USER']}:{deploy_env['POSTGRES_PASSWORD']}"
            f"@localhost:5432/cyberpulse_test"
        )

    # 3. 默认值
    return "postgresql://cyberpulse:cyberpulse123@localhost:5432/cyberpulse_test"


# 在导入任何模块之前设置环境变量
test_db_url = get_test_database_url()
os.environ["DATABASE_URL"] = test_db_url
os.environ["TEST_DATABASE_URL"] = test_db_url

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from cyberpulse.database import Base


def get_admin_database_url(test_db_url: str) -> str:
    """获取管理员数据库 URL（用于创建/删除测试数据库）。"""
    # 替换数据库名为 postgres
    parts = test_db_url.rsplit("/", 1)
    return f"{parts[0]}/postgres"


@pytest.fixture(scope="session")
def db_engine():
    """
    创建测试数据库引擎（session 级别）。

    在测试会话开始时创建数据库，结束时删除。
    """
    test_db_url = get_test_database_url()
    admin_db_url = get_admin_database_url(test_db_url)
    test_db_name = test_db_url.rsplit("/", 1)[-1]

    # 连接到 postgres 数据库来创建测试数据库
    admin_engine = create_engine(admin_db_url, isolation_level="AUTOCOMMIT")

    try:
        with admin_engine.connect() as conn:
            # 检查数据库是否存在
            result = conn.execute(
                text(f"SELECT 1 FROM pg_database WHERE datname = '{test_db_name}'")
            )
            exists = result.fetchone() is not None

            if not exists:
                # 创建测试数据库
                conn.execute(text(f'CREATE DATABASE "{test_db_name}"'))
    except ProgrammingError:
        # 如果数据库已存在，忽略错误
        pass
    finally:
        admin_engine.dispose()

    # 创建测试数据库引擎
    engine = create_engine(test_db_url)

    # 创建所有表
    Base.metadata.create_all(engine)

    yield engine

    # 清理：删除所有表
    Base.metadata.drop_all(engine)
    engine.dispose()

    # 删除测试数据库
    admin_engine = create_engine(admin_db_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            # 断开所有连接
            conn.execute(text(f"""
                    SELECT pg_terminate_backend(pg_stat_activity.pid)
                    FROM pg_stat_activity
                    WHERE pg_stat_activity.datname = '{test_db_name}'
                    AND pid <> pg_backend_pid()
                    """))
            conn.execute(text(f'DROP DATABASE IF EXISTS "{test_db_name}"'))
    finally:
        admin_engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Session:
    """
    创建数据库会话（function 级别）。

    每个测试函数使用独立的事务，测试结束后回滚。
    """
    connection = db_engine.connect()
    transaction = connection.begin()

    Session = sessionmaker(bind=connection)
    session = Session()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def db_session_no_rollback(db_engine) -> Session:
    """
    创建数据库会话（无回滚）。

    用于需要测试提交行为的场景。
    """
    Session = sessionmaker(bind=db_engine)
    session = Session()

    yield session

    session.close()
