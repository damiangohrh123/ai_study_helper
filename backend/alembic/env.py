import asyncio
from logging.config import fileConfig
import os

from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context

# Import your Base and models here
from db import Base  # adjust this import if needed
import models        # ensure all models are imported

# Alembic Config object
config = context.config

# Set up loggers
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Get DB URL from environment or .env
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))
    DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # fallback to manual construction if needed
    from db import DATABASE_URL as DB_URL
    DATABASE_URL = DB_URL

def run_migrations_offline():
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online():
    connectable = create_async_engine(DATABASE_URL, future=True)
    async with connectable.begin() as connection:
        def do_migrations(sync_conn):
            context.configure(connection=sync_conn, target_metadata=target_metadata)
            context.run_migrations()
        await connection.run_sync(do_migrations)
    await connectable.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())