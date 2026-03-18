"""
PostgreSQL 测试配置

使用环境变量 TEST_DATABASE_URL 配置测试数据库。
默认使用 postgresql://postgres:postgres@localhost:5432/cyberpulse_test
"""

import os

# 在导入任何模块之前设置环境变量
# 这必须是最先执行的代码
os.environ["DATABASE_URL"] = os.environ.get(
    "DATABASE_URL",
    "postgresql://cyberpulse:cyberpulse123@localhost:5432/cyberpulse_test"
)
os.environ["TEST_DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://cyberpulse:cyberpulse123@localhost:5432/cyberpulse_test"
)

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import ProgrammingError

from cyberpulse.database import Base


def get_test_database_url() -> str:
    """获取测试数据库 URL。"""
    return os.environ["TEST_DATABASE_URL"]


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