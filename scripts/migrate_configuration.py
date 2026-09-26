"""Add configuration tables without replacing or rewriting existing business data."""

import os
from pathlib import Path

from dotenv import load_dotenv
from presales.configuration.models import (
    Entity,
    ExtractionJob,
    Revision,
    SearchDocument,
    SearchIndexJob,
    SourceBlock,
    SourceLink,
    SourceRevision,
)
from presales.storage import Base
from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[1]
NEW_TABLES = (
    Entity.__table__,
    Revision.__table__,
    SourceLink.__table__,
    SourceBlock.__table__,
    SourceRevision.__table__,
    ExtractionJob.__table__,
    SearchDocument.__table__,
    SearchIndexJob.__table__,
)


def migrate(engine):
    with engine.begin() as connection:
        existing = set(inspect(connection).get_table_names())
        if "product_records" not in existing:
            raise ValueError(
                "未找到现有产品库，请核对 DATABASE_URL；本迁移不创建替代数据库"
            )
        if engine.dialect.name == "postgresql":
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(connection, tables=NEW_TABLES, checkfirst=True)
        return [table.name for table in NEW_TABLES if table.name not in existing]


if __name__ == "__main__":
    load_dotenv(ROOT / ".env")
    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        print("新增配置表：", ", ".join(migrate(engine)) or "已迁移，无需更改")
    finally:
        engine.dispose()
