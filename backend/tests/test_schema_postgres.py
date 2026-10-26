"""Valida schema.sql e migrações em PostgreSQL real.

Só roda com TEST_POSTGRES_URL apontando a um banco DESCARTÁVEL, por exemplo:
  TEST_POSTGRES_URL=postgresql+psycopg://postgres:postgres@localhost:5432/salutem_test
O teste apaga e recria as tabelas da aplicação nesse banco. Nunca use o ERP.
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

URL = os.getenv("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="defina TEST_POSTGRES_URL (banco descartável)")
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def conn():
    engine = create_engine(URL)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "DROP TABLE IF EXISTS public.requisicoes, public.setores CASCADE;"
            "DROP SEQUENCE IF EXISTS public.salutem_itecontrol_seq;"
        )
        connection.exec_driver_sql((ROOT / "database" / "schema.sql").read_text())
    with engine.begin() as connection:
        yield connection
    engine.dispose()


def test_sequence_starts_at_84333_and_schema_is_idempotent(conn) -> None:
    conn.exec_driver_sql((ROOT / "database" / "schema.sql").read_text())
    assert conn.execute(text("SELECT nextval('public.salutem_itecontrol_seq')")).scalar_one() == 84333
    tables = set(
        conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).scalars()
    )
    assert tables == {"setores", "requisicoes"}


def test_status_cancelada_allowed_and_invalid_status_rejected(conn) -> None:
    conn.exec_driver_sql((ROOT / "database" / "migrations" / "001_status_cancelada.sql").read_text())
    conn.exec_driver_sql((ROOT / "database" / "migrations" / "001_status_cancelada.sql").read_text())
    conn.execute(
        text(
            "INSERT INTO setores (nome, perfil, lider_nome, senha_hash) "
            "VALUES ('Teste', 'solicitante', 'Ana', 'x')"
        )
    )
    insert = text(
        "INSERT INTO requisicoes (itecontrol, setor_id, setor_nome_snapshot, lider_nome_snapshot,"
        " data_requisicao, status) VALUES (:c, 1, 'Teste', 'Ana', current_date, :s)"
    )
    conn.execute(insert, {"c": 1, "s": "Cancelada"})
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(insert, {"c": 2, "s": "Inventado"})
