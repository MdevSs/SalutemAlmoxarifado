from collections.abc import Generator, Iterator
from contextlib import contextmanager

from fastapi import HTTPException
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_app_engine: Engine | None = None
_erp_engine: Engine | None = None
_app_session_factory: sessionmaker[Session] | None = None
ERP_ALLOWED_HOST = "192.168.1.2"


def validate_erp_host(url: str) -> None:
    try:
        parsed_url = make_url(url)
    except ArgumentError as error:
        raise HTTPException(
            status_code=503,
            detail="ERP_DATABASE_URL inválida; confira o formato no servidor da rede local.",
        ) from error
    host_override = any(key in parsed_url.query for key in ("host", "hostaddr", "service"))
    if parsed_url.host != ERP_ALLOWED_HOST or host_override:
        raise HTTPException(
            status_code=503,
            detail=f"ERP_DATABASE_URL deve apontar ao host autorizado {ERP_ALLOWED_HOST}.",
        )


def get_app_engine() -> Engine | None:
    global _app_engine, _app_session_factory
    url = get_settings().app_sqlalchemy_url
    if not url:
        return None
    if _app_engine is None:
        _app_engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            connect_args={"connect_timeout": 8},
        )
        _app_session_factory = sessionmaker(
            bind=_app_engine, autoflush=False, expire_on_commit=False
        )
    return _app_engine


def get_erp_engine() -> Engine | None:
    global _erp_engine
    url = get_settings().erp_sqlalchemy_url
    if not url:
        return None
    validate_erp_host(url)
    if _erp_engine is None:
        _erp_engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=3,
            max_overflow=2,
            connect_args={"connect_timeout": 8},
        )
    return _erp_engine


def get_app_session() -> Generator[Session, None, None]:
    get_app_engine()
    if _app_session_factory is None:
        raise HTTPException(
            status_code=503,
            detail="Banco local não configurado. Defina APP_DATABASE_URL no servidor.",
        )
    session = _app_session_factory()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def erp_connection() -> Iterator:
    engine = get_erp_engine()
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail="Conexão ERP não configurada. Defina ERP_DATABASE_URL no servidor da rede local.",
        )
    with engine.begin() as connection:
        yield connection
