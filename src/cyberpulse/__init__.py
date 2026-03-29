import os
from pathlib import Path


def _get_version() -> str:
    """获取版本号，优先级：环境变量 > .version 文件 > 默认值"""
    if os.environ.get("APP_VERSION"):
        return os.environ["APP_VERSION"]

    version_file = Path(__file__).parent.parent.parent / ".version"
    if version_file.exists():
        version = version_file.read_text().strip()
        if version:
            return version

    return "1.5.0"


__version__ = _get_version()
__author__ = "老罗"

from .config import settings
from .database import Base, SessionLocal, engine, get_db

__all__ = [
    "__version__",
    "__author__",
    "settings",
    "Base",
    "engine",
    "SessionLocal",
    "get_db",
]