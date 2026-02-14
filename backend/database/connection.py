"""Database connection and session management."""

import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


# Data directory
DATA_DIR = Path(os.environ.get("NULLGRAVITY_DATA_DIR", Path.home() / ".nullgravity"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR / 'nullgravity.db'}"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


async def init_db():
    """Initialize the database and create all tables."""
    async with engine.begin() as conn:
        # Import models here to ensure they are registered with Base.metadata
        from models.account import Account
        from models.credential import OAuthCredential
        from models.log import Log
        from models.settings import AppSettings
        
        await conn.run_sync(Base.metadata.create_all)

        # Auto-migrate: add missing columns to existing tables
        import sqlalchemy

        result = await conn.execute(sqlalchemy.text("PRAGMA table_info(accounts)"))
        existing_columns = {row[1] for row in result.fetchall()}

        if "device_profile" not in existing_columns:
            await conn.execute(
                sqlalchemy.text("ALTER TABLE accounts ADD COLUMN device_profile JSON")
            )
        
        if "models" not in existing_columns:
            await conn.execute(
                sqlalchemy.text("ALTER TABLE accounts ADD COLUMN models JSON")
            )

        if "status_details" not in existing_columns:
            await conn.execute(
                sqlalchemy.text("ALTER TABLE accounts ADD COLUMN status_details JSON")
            )

        if "avatar_cached" not in existing_columns:
            await conn.execute(
                sqlalchemy.text("ALTER TABLE accounts ADD COLUMN avatar_cached BOOLEAN DEFAULT 0")
            )

        # Auto-migrate: oauth_credentials 新列 (per-client data)
        result2 = await conn.execute(sqlalchemy.text("PRAGMA table_info(oauth_credentials)"))
        cred_columns = {row[1] for row in result2.fetchall()}

        for col_name, col_type in [
            ("tier", "VARCHAR(50)"),
            ("project_id", "VARCHAR(255)"),
            ("models", "JSON"),
            ("quota_data", "JSON"),
            ("last_sync_at", "DATETIME"),
        ]:
            if col_name not in cred_columns:
                await conn.execute(
                    sqlalchemy.text(f"ALTER TABLE oauth_credentials ADD COLUMN {col_name} {col_type}")
                )

        # Auto-migrate: request_logs account_id
        result3 = await conn.execute(sqlalchemy.text("PRAGMA table_info(request_logs)"))
        log_columns = {row[1] for row in result3.fetchall()}
        
        if "account_id" not in log_columns:
             await conn.execute(
                 sqlalchemy.text("ALTER TABLE request_logs ADD COLUMN account_id VARCHAR(36)")
             )


async def close_db():
    """Close the database engine."""
    await engine.dispose()


async def get_session() -> AsyncSession:
    """Dependency to get a database session."""
    async with async_session() as session:
        yield session
