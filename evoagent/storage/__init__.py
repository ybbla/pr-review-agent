"""持久化与队列：SQLite/PostgreSQL 存储与持久任务队列。"""
from .sqlite_store import TaskStore
from .postgres_store import PostgresTaskStore


def create_store(database_url: str, sqlite_path: str):
    """根据数据库 URL 选择存储后端：PostgreSQL 或默认 SQLite。"""
    if database_url.startswith(("postgres://", "postgresql://")):
        return PostgresTaskStore(database_url)
    return TaskStore(sqlite_path)
