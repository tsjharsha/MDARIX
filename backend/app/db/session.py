import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from backend.app.db.tls import connect_args

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


def _engine(url: URL, *, request_path: bool = False):
    return create_engine(
        url,
        future=True,
        # A failing statement is logged with its SQL only: bound values (passwords, tokens, customer records) never
        # reach the log collector through an exception message.
        hide_parameters=True,
        pool_size=int(os.getenv("MDARIX_DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("MDARIX_DB_MAX_OVERFLOW", "10")),
        pool_timeout=int(os.getenv("MDARIX_DB_POOL_TIMEOUT_SECONDS", "30")),
        pool_pre_ping=True,
        connect_args=connect_args(request_path=request_path),
    )


# Owner connection: migrations, scripts, test setup and trusted internal jobs.
engine = _engine(database_url())
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# API requests use the least-privilege runtime role when it is configured, so Postgres row-level security applies
# to every request (see backend/app/db/tenant_scope.py). Without it, requests fall back to the owner connection.
_runtime_user = os.getenv("MDARIX_DB_RUNTIME_USER", "").strip()


def separate_runtime_engine(runtime_user: str, owner_user: str | None) -> bool:
    """A second pool only for a runtime role that is not the owner: the same login twice would double the connections
    a process may hold (db-audit N4, DB-04)."""
    return bool(runtime_user) and runtime_user != (owner_user or "")


runtime_engine = (
    _engine(database_url(_runtime_user, os.environ.get("MDARIX_DB_RUNTIME_PASSWORD", "")), request_path=True)
    if separate_runtime_engine(_runtime_user, os.environ.get("POSTGRES_USER"))
    else engine
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
