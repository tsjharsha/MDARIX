import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

load_dotenv()


def database_url(username: str | None = None, password: str | None = None) -> URL:
    return URL.create(
        drivername="postgresql+pg8000",
        username=username or os.environ["POSTGRES_USER"],
        password=password if username else os.environ["POSTGRES_PASSWORD"],
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.environ.get("POSTGRES_PORT", "5433")),
        database=os.environ["POSTGRES_DB"],
    )


def _engine(url: URL):
    return create_engine(
        url,
        future=True,
        pool_size=int(os.getenv("MDARIX_DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("MDARIX_DB_MAX_OVERFLOW", "10")),
        pool_timeout=int(os.getenv("MDARIX_DB_POOL_TIMEOUT_SECONDS", "30")),
        pool_pre_ping=True,
    )


# Owner connection: migrations, scripts, test setup and trusted internal jobs.
engine = _engine(database_url())
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# API requests use the least-privilege runtime role when it is configured, so Postgres row-level security applies
# to every request (see backend/app/db/tenant_scope.py). Without it, requests fall back to the owner connection.
_runtime_user = os.getenv("MDARIX_DB_RUNTIME_USER", "").strip()
runtime_engine = (
    _engine(database_url(_runtime_user, os.environ.get("MDARIX_DB_RUNTIME_PASSWORD", ""))) if _runtime_user else engine
)
RuntimeSessionLocal = sessionmaker(bind=runtime_engine, autoflush=False, autocommit=False, future=True)


def runtime_role_active() -> bool:
    return runtime_engine is not engine


def get_db():
    db = RuntimeSessionLocal()
    try:
        yield db
    finally:
        db.close()
