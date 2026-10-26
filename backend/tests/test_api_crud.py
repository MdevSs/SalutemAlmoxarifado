import logging
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection as SQLAlchemyConnection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import requests as request_api
from app.core.database import get_app_session, validate_erp_host
from app.core.security import hash_password
from app.main import app
from app.models import Base, Setor
from app.services import erp


class FakeControlResult:
    def __init__(self, value: int) -> None:
        self.value = value

    def scalar_one(self) -> int:
        return self.value


class FakeControlConnection:
    def __init__(self, next_control: int = 84333) -> None:
        self.next_control = next_control

    def execute(self, statement: Any) -> FakeControlResult:
        query = " ".join(str(statement).lower().split())
        assert query == (
            "select coalesce(max(itecontrol), 0) + 1 as proximo_id from toqmovi"
        )
        result = FakeControlResult(self.next_control)
        self.next_control += 1
        return result


def test_allocate_control_uses_next_id_from_erp(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_connection = FakeControlConnection(next_control=1)

    @contextmanager
    def fake_erp_connection():
        yield fake_connection

    monkeypatch.setattr(request_api, "erp_connection", fake_erp_connection)

    assert request_api._allocate_control() == 1


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("APP_SESSION_SECRET", "test-only-session-secret-long-enough-1234567890")
    monkeypatch.setenv("APP_COOKIE_SECURE", "false")
    monkeypatch.setenv("APP_COOKIE_SAMESITE", "lax")
    from app.core.config import get_settings

    get_settings.cache_clear()
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with test_sessions() as session:
        session.add_all(
            [
                Setor(
                    id=1,
                    nome="Serralheria",
                    perfil="solicitante",
                    lider_nome="Erivaldo",
                    senha_hash=hash_password("senha-setor-teste-123"),
                ),
                Setor(
                    id=2,
                    nome="Almoxarifado",
                    perfil="almoxarifado",
                    lider_nome=None,
                    senha_hash=hash_password("senha-almox-teste-1234"),
                ),
                Setor(
                    id=3,
                    nome="Administrador",
                    perfil="administrador",
                    lider_nome=None,
                    senha_hash=hash_password("senha-admin-teste-1234"),
                ),
            ]
        )
        session.commit()

    def override_app_session() -> Generator[Session, None, None]:
        with test_sessions() as session:
            yield session

    app.dependency_overrides[get_app_session] = override_app_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
    get_settings.cache_clear()


def login(client: TestClient, sector_id: int, password: str) -> str:
    token = client.get("/api/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/api/auth/login",
        json={"sector_id": sector_id, "password": password},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def test_schema_has_only_two_business_tables() -> None:
    assert set(Base.metadata.tables) == {"setores", "requisicoes"}


def test_erp_dsn_is_restricted_to_the_authorized_lan_host() -> None:
    validate_erp_host("postgresql+psycopg://user:placeholder@192.168.1.2:5432/salutem")
    with pytest.raises(HTTPException) as error:
        validate_erp_host("postgresql+psycopg://user:placeholder@192.168.1.18:5432/salutem")
    assert error.value.status_code == 503
    assert "placeholder" not in error.value.detail
    with pytest.raises(HTTPException):
        validate_erp_host(
            "postgresql+psycopg://user:placeholder@192.168.1.2:5432/salutem?hostaddr=192.168.1.18"
        )


def test_erp_failure_log_redacts_connection_credentials(caplog: pytest.LogCaptureFixture) -> None:
    request_api._log_erp_failure(
        84345,
        SQLAlchemyError(
            "could not connect postgresql+psycopg://postgres:never-log-this@192.168.1.2/salutem "
            "password=also-never-log-this"
        ),
    )

    assert "ERP finalization DB error control=84345" in caplog.text
    assert "[credenciais ocultas]" in caplog.text
    assert "[oculto]" in caplog.text
    assert "never-log-this" not in caplog.text
    assert "also-never-log-this" not in caplog.text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("=1+1", "'=1+1"),
        ("+SUM(A1:A2)", "'+SUM(A1:A2)"),
        ("-1+2", "'-1+2"),
        ("@SUM(A1:A2)", "'@SUM(A1:A2)"),
        ("\t=1+1", "'\t=1+1"),
        ("Salutem", "Salutem"),
    ],
)
def test_safe_csv_cell_neutralizes_spreadsheet_formulas(value: str, expected: str) -> None:
    assert request_api._safe_csv_cell(value) == expected


def test_all_catalog_queries_include_only_active_products(monkeypatch: pytest.MonkeyPatch) -> None:
    queries: list[str] = []
    parameters: list[dict[str, Any]] = []

    class Result:
        def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
            self.rows = rows or []

        def scalar_one(self) -> int:
            return 0

        def scalars(self) -> "Result":
            return self

        def mappings(self) -> "Result":
            return self

        def all(self) -> list[Any]:
            return self.rows

    class Connection:
        def execute(self, statement: Any, params: dict[str, Any] | None = None) -> Result:
            queries.append(str(statement).lower())
            parameters.append(dict(params or {}))
            if params and "fetch_limit" in params:
                rows = [
                    {
                        "code": f"10.001.{index:04d}",
                        "description": "Produto de teste",
                        "stock": Decimal("5.0000"),
                        "deposit": 1,
                    }
                    for index in range(21)
                ]
                return Result(rows)
            return Result()

    fake_connection = Connection()

    @contextmanager
    def fake_erp_connection():
        yield fake_connection

    monkeypatch.setattr(erp, "erp_connection", fake_erp_connection)
    products, has_more = erp.list_products("Parafuso 4,5")
    cached_products, cached_has_more = erp.list_products("Parafuso 4,5")
    assert len(products) == 20
    assert has_more is True
    assert cached_products == products
    assert cached_has_more is True
    assert erp.find_products(cast(SQLAlchemyConnection, fake_connection), ["10.001.0007"]) == {}
    assert len(queries) == 2
    assert all("p.prostatus = 'a'" in query for query in queries)
    assert all("join public.produto as p" in query for query in queries)
    assert all(":group_10" in query and ":group_11" in query for query in queries)
    assert all(":group_12" in query and ":group_13" in query for query in queries)
    assert "limit :fetch_limit" in queries[0]
    assert "count(" not in queries[0]
    assert parameters[0]["fetch_limit"] == 21
    assert parameters[0]["term"] == "%Parafuso%4,5%"


def test_auth_uses_sector_password_cookie_and_csrf(client: TestClient) -> None:
    login(client, 1, "senha-setor-teste-123")
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json() == {
        "sector_id": 1,
        "sector_name": "Serralheria",
        "profile": "solicitante",
        "leader_name": "Erivaldo",
    }
    assert client.get("/api/sectors").status_code == 403
    no_csrf = client.post(
        "/api/requests",
        json={
            "requested_date": date.today().isoformat(),
            "items": [{"material_code": "10.001.0007", "quantity": 1}],
        },
    )
    assert no_csrf.status_code == 403


def test_admin_can_create_requests_and_use_warehouse_and_sector_screens(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    product = erp.Product("10.001.0007", "Parafuso inox", Decimal("100.0000"), 1, "10.001")
    fake_connection = FakeControlConnection()

    @contextmanager
    def fake_erp_connection():
        yield fake_connection

    monkeypatch.setattr(request_api, "erp_connection", fake_erp_connection)
    monkeypatch.setattr(
        request_api, "find_products", lambda _connection, codes: {code: product for code in codes}
    )
    csrf = login(client, 3, "senha-admin-teste-1234")
    assert client.get("/api/sectors").status_code == 200
    assert client.get("/api/requests/responsibles").status_code == 200
    assert any(
        row["profile"] == "administrador" for row in client.get("/api/auth/sectors").json()
    )
    created = client.post(
        "/api/requests",
        headers={"X-CSRF-Token": csrf},
        json={
            "requested_date": date.today().isoformat(),
            "items": [{"material_code": "10.001.0007", "quantity": 3}],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["sector_name"] == "Administrador"
    assert created.json()["leader_name"] == "Administrador"
    history = client.get("/api/requests")
    assert history.status_code == 200
    assert history.json()["total"] == 1
    new_sector = client.post(
        "/api/sectors",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Setor teste",
            "profile": "solicitante",
            "leader_name": "Ana",
            "password": "senha-novo-setor-1234",
        },
    )
    assert new_sector.status_code == 201, new_sector.text
    started = client.post(f"/api/requests/{created.json()['itecontrol']}/start", headers={"X-CSRF-Token": csrf})
    assert started.status_code == 200, started.text


def test_erp_finalize_failure_returns_safe_503_and_logs_redacted_diagnostics(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    product = erp.Product("10.001.0007", "Parafuso inox", Decimal("100.0000"), 1, "10.001")
    fake_connection = FakeControlConnection()

    @contextmanager
    def fake_erp_connection():
        yield fake_connection

    monkeypatch.setattr(request_api, "erp_connection", fake_erp_connection)
    monkeypatch.setattr(
        request_api, "find_products", lambda _connection, codes: {code: product for code in codes}
    )
    csrf = login(client, 3, "senha-admin-teste-1234")
    created = client.post(
        "/api/requests",
        headers={"X-CSRF-Token": csrf},
        json={"requested_date": date.today().isoformat(), "items": [{"material_code": product.code, "quantity": 3}]},
    )
    assert created.status_code == 201, created.text
    control = created.json()["itecontrol"]
    assert client.post(f"/api/requests/{control}/start", headers={"X-CSRF-Token": csrf}).status_code == 200

    def fail_post(**_kwargs: Any) -> bool:
        raise SQLAlchemyError(
            "connection postgresql+psycopg://postgres:never-log-this@192.168.1.2/salutem "
            "password=also-never-log-this"
        )

    monkeypatch.setattr(request_api, "post_requisition", fail_post)
    with caplog.at_level(logging.ERROR, logger=request_api.__name__):
        failed = client.post(
            f"/api/requests/{control}/finalize",
            headers={"X-CSRF-Token": csrf},
            json={"responsible_name": "Maria", "deliveries": [{"item_index": 1, "quantity": 3}]},
        )

    assert failed.status_code == 503
    assert "never-log-this" not in failed.text
    assert "never-log-this" not in caplog.text
    assert "ERP finalization DB error control=84333" in caplog.text
    assert client.get(f"/api/requests/{control}").json()["erp_status"] == "falhou"


def test_warehouse_cannot_open_sector_administration_and_decimal_quantities_are_rejected(
    client: TestClient,
) -> None:
    request_csrf = login(client, 1, "senha-setor-teste-123")
    decimal_request = client.post(
        "/api/requests",
        headers={"X-CSRF-Token": request_csrf},
        json={
            "requested_date": date.today().isoformat(),
            "items": [{"material_code": "10.001.0007", "quantity": "1.5"}],
        },
    )
    assert decimal_request.status_code == 422
    assert login(client, 2, "senha-almox-teste-1234")
    assert client.get("/api/sectors").status_code == 403
    csrf = client.cookies.get("salutem_csrf")
    assert csrf is not None
    decimal_delivery = client.post(
        "/api/requests/84333/finalize",
        headers={"X-CSRF-Token": csrf},
        json={
            "responsible_name": "Maria",
            "deliveries": [{"item_index": 1, "quantity": "0.5"}],
        },
    )
    assert decimal_delivery.status_code == 422


def test_finalize_rejects_whitespace_only_responsible_name(client: TestClient) -> None:
    csrf = login(client, 2, "senha-almox-teste-1234")
    response = client.post(
        "/api/requests/84333/finalize",
        headers={"X-CSRF-Token": csrf},
        json={"responsible_name": "   ", "deliveries": [{"item_index": 1, "quantity": 0}]},
    )
    assert response.status_code == 422


def test_csrf_refresh_preserves_active_session(client: TestClient) -> None:
    csrf = login(client, 1, "senha-setor-teste-123")
    refreshed = client.get("/api/auth/csrf")
    assert refreshed.status_code == 200
    assert refreshed.json()["csrf_token"] == csrf
    assert client.get("/api/auth/me").status_code == 200
    logout = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert logout.status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_request_posts_control_from_84333_and_records_responsible(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    today = date.today()
    captured: list[dict[str, Any]] = []
    product = erp.Product("10.001.0007", "Parafuso 4,5 mm", Decimal("100.0000"), 1, "10.001")
    fake_connection = FakeControlConnection()

    @contextmanager
    def fake_erp_connection():
        yield fake_connection

    monkeypatch.setattr(request_api, "erp_connection", fake_erp_connection)
    monkeypatch.setattr(
        request_api, "find_products", lambda _connection, codes: {code: product for code in codes}
    )

    def record_post(*, itecontrol: int, requested_date: date, items: list[dict[str, Any]]) -> bool:
        captured.append(
            {"itecontrol": itecontrol, "requested_date": requested_date, "items": items}
        )
        return False

    monkeypatch.setattr(request_api, "post_requisition", record_post)
    csrf = login(client, 1, "senha-setor-teste-123")
    created = client.post(
        "/api/requests",
        headers={"X-CSRF-Token": csrf},
        json={
            "requested_date": today.isoformat(),
            "delivery_instructions": "=1+1",
            "items": [
                {"material_code": "10.001.0007", "quantity": 10},
                {"material_code": "10.001.0007", "quantity": 1},
            ],
        },
    )
    assert created.status_code == 201, created.text
    request = created.json()
    assert request["itecontrol"] == 84333
    assert request["sector_name"] == "Serralheria"
    assert request["leader_name"] == "Erivaldo"
    assert len(request["items"]) == 1
    assert Decimal(str(request["items"][0]["requested_quantity"])) == Decimal("11.0000")

    csrf = login(client, 3, "senha-admin-teste-1234")
    renamed = client.patch(
        "/api/sectors/1",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Manutenção", "leader_name": "Ana"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Manutenção"
    assert client.get("/api/requests/84333").json()["sector_name"] == "Serralheria"
    assert client.get("/api/requests/84333").json()["leader_name"] == "Erivaldo"
    started = client.post("/api/requests/84333/start", headers={"X-CSRF-Token": csrf})
    assert started.status_code == 200, started.text
    finished = client.post(
        "/api/requests/84333/finalize",
        headers={"X-CSRF-Token": csrf},
        json={
            "responsible_name": "Maria",
            "warehouse_notes": "Separação concluída",
            "deliveries": [{"item_index": 1, "quantity": 10}],
        },
    )
    assert finished.status_code == 200, finished.text
    assert finished.json()["status"] == "Parcial"
    assert finished.json()["erp_status"] == "enviado"
    assert finished.json()["responsible_name"] == "Maria"
    locked_notes = client.put(
        "/api/requests/84333/notes",
        headers={"X-CSRF-Token": csrf},
        json={"warehouse_notes": "tentativa de alteração posterior"},
    )
    assert locked_notes.status_code == 409
    persisted = client.get("/api/requests/84333")
    assert persisted.status_code == 200
    assert Decimal(str(persisted.json()["items"][0]["delivered_quantity"])) == Decimal("10.0000")
    complete_request = client.post(
        "/api/requests",
        headers={"X-CSRF-Token": csrf},
        json={"requested_date": today.isoformat(), "items": [{"material_code": "10.001.0007", "quantity": 4}]},
    )
    assert complete_request.status_code == 201, complete_request.text
    assert complete_request.json()["itecontrol"] == 84334
    complete_started = client.post("/api/requests/84334/start", headers={"X-CSRF-Token": csrf})
    assert complete_started.status_code == 200, complete_started.text
    complete_finished = client.post(
        "/api/requests/84334/finalize",
        headers={"X-CSRF-Token": csrf},
        json={"responsible_name": "Maria", "deliveries": [{"item_index": 1, "quantity": 4}]},
    )
    assert complete_finished.status_code == 200, complete_finished.text
    assert complete_finished.json()["status"] == "Finalizada"
    partial_page = client.get(
        "/api/requests",
        params={"status": "Parcial", "date_from": today.isoformat(), "date_to": today.isoformat()},
    )
    assert partial_page.status_code == 200, partial_page.text
    assert partial_page.json()["total"] == 1
    date_page = client.get(
        "/api/requests", params={"date_from": today.isoformat(), "date_to": today.isoformat()}
    )
    assert date_page.status_code == 200, date_page.text
    assert date_page.json()["total"] == 2
    assert client.get("/api/requests", params={"date_from": "2099-01-01"}).json()["total"] == 0
    assert client.get(
        "/api/requests", params={"date_from": "2099-01-01", "date_to": today.isoformat()}
    ).status_code == 422
    multi_term = client.get("/api/requests", params={"search": "parafuso 4,5"})
    assert multi_term.status_code == 200, multi_term.text
    assert multi_term.json()["total"] == 2
    exported = client.get(
        "/api/requests/export.csv", params={"date_from": today.isoformat(), "date_to": today.isoformat()}
    )
    assert exported.status_code == 200, exported.text
    assert "Parcial" in exported.text
    assert "'=1+1" in exported.text
    login(client, 1, "senha-setor-teste-123")
    notifications = client.get(
        "/api/requests/notifications/finalized",
        params={"after": "2000-01-01T00:00:00Z", "after_control": 0},
    )
    assert notifications.status_code == 200, notifications.text
    assert [row["itecontrol"] for row in notifications.json()] == [84333]
    assert notifications.json()[0]["status"] == "Parcial"
    repeated_notifications = client.get(
        "/api/requests/notifications/finalized",
        params={"after": notifications.json()[0]["finalized_at"], "after_control": 84333},
    )
    assert repeated_notifications.status_code == 200, repeated_notifications.text
    assert repeated_notifications.json() == []
    assert captured[0]["itecontrol"] == 84333
    assert captured[0]["requested_date"] == today
    assert captured[0]["items"][0]["material_code"] == "10.001.0007"
    assert captured[0]["items"][0]["delivered_quantity"] == "10.0000"


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None):
        self.rows = rows or []

    def mappings(self) -> "FakeResult":
        return self

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class FakeERPConnection:
    def __init__(self, existing: list[dict[str, Any]] | None = None):
        self.existing = existing or []
        self.inserted: list[dict[str, Any]] = []
        self.insert_sql: list[str] = []

    def execute(self, statement: Any, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement).lower()
        if "pg_advisory_xact_lock" in sql:
            return FakeResult()
        if "from public.toqmovi" in sql:
            return FakeResult(self.existing)
        if "from public.vw_produto_saldo_estoque" in sql:
            codes = params["codes"] if params else []
            return FakeResult(
                [
                    {
                        "code": code,
                        "description": "Item ERP",
                        "stock": Decimal("50.0000"),
                        "deposit": 1,
                    }
                    for code in codes
                ]
            )
        if sql.lstrip().startswith("insert into public.toqmovi"):
            self.inserted.append(params or {})
            self.insert_sql.append(sql)
            return FakeResult()
        raise AssertionError(f"SQL inesperado no teste ERP: {sql[:100]}")


def test_erp_insert_uses_fixed_width_blanks_and_contiguous_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeERPConnection()

    @contextmanager
    def fake_erp_connection():
        yield fake

    monkeypatch.setattr(erp, "erp_connection", fake_erp_connection)
    retried = erp.post_requisition(
        itecontrol=84333,
        requested_date=date(2026, 10, 21),
        items=[
            {"material_code": "10.001.0007", "delivered_quantity": "0.0000"},
            {"material_code": "10.001.0008", "delivered_quantity": "2.0000"},
            {"material_code": "10.001.0009", "delivered_quantity": "3.0000"},
        ],
    )
    assert retried is False
    assert len(fake.inserted) == 2
    first, second = fake.inserted
    assert [first["prisequen"], second["prisequen"]] == [1, 2]
    assert first["itecontrol"] == second["itecontrol"] == 84333
    assert first["pritransac"] == second["pritransac"] == 14
    assert first["prideposit"] == second["prideposit"] == 1
    assert first["priordem"] == second["priordem"] == 0
    assert first["priproduto"] == "10.001.0008"
    assert first["priquanti"] == Decimal("2.0000")
    assert all(first[column] == value for column, value in erp._ERP_MOVEMENT_DEFAULTS.items())
    assert first["priobserv"] == " " * 100
    assert first["privlarr"] == Decimal("0.0000000000")
    assert "current_date" in fake.insert_sql[0]
    assert "cast(localtime(0) as text)" in fake.insert_sql[0]
    assert "to_char(current_time" not in fake.insert_sql[0]
    assert all(column in fake.insert_sql[0] for column in erp._ERP_INSERT_COLUMNS)
    assert "null" not in fake.insert_sql[0]
    assert "pridtalt" not in first and "prihralt" not in first
    assert "doc_controle" not in first and "doc_operacao" not in first and "notdtdigit" not in first


def test_erp_adapter_rejects_fractional_quantities_before_opening_connection() -> None:
    with pytest.raises(HTTPException) as error:
        erp.post_requisition(
            itecontrol=84333,
            requested_date=date(2026, 10, 21),
            items=[{"material_code": "10.001.0008", "delivered_quantity": "2.5000"}],
        )

    assert error.value.status_code == 422


def test_erp_exact_retry_does_not_insert_duplicates(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = {
        "prisequen": 1,
        "pridata": date(2026, 10, 21),
        "priproduto": "10.001.0007",
        "prideposit": 1,
        "pritransac": 14,
        "priordem": 0,
        "priquanti": Decimal("3.0000"),
        **erp._ERP_MOVEMENT_DEFAULTS,
        "pridtalt": date(2026, 10, 21),
        "prihralt": "10:35:19",
    }
    fake = FakeERPConnection(existing=[expected])

    @contextmanager
    def fake_erp_connection():
        yield fake

    monkeypatch.setattr(erp, "erp_connection", fake_erp_connection)
    retried = erp.post_requisition(
        itecontrol=84333,
        requested_date=date(2026, 10, 21),
        items=[{"material_code": "10.001.0007", "delivered_quantity": "3.0000"}],
    )
    assert retried is True
    assert fake.inserted == []


def test_erp_null_rows_are_conflict_not_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeERPConnection(
        existing=[
            {
                "prisequen": None,
                "pridata": None,
                "priproduto": None,
                "prideposit": None,
                "pritransac": None,
                "priquanti": None,
                "operacao": None,
                "pridocto": None,
                "priemitido": None,
                "priusuario": None,
            }
        ]
    )

    @contextmanager
    def fake_erp_connection():
        yield fake

    monkeypatch.setattr(erp, "erp_connection", fake_erp_connection)
    with pytest.raises(HTTPException) as error:
        erp.post_requisition(
            itecontrol=84333,
            requested_date=date(2026, 10, 21),
            items=[{"material_code": "10.001.0007", "delivered_quantity": "1.0000"}],
        )
    assert error.value.status_code == 409
    assert fake.inserted == []
