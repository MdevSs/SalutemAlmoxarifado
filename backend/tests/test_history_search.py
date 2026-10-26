from collections.abc import Generator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import requests as request_api
from app.core.database import get_app_session
from app.core.security import hash_password
from app.main import app
from app.models import Base, Setor
from app.services.erp import Product
from test_api_crud import FakeControlConnection


@pytest.fixture
def history_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
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
        session.add(
            Setor(
                id=1,
                nome="Serralheria",
                perfil="solicitante",
                lider_nome="Erivaldo",
                senha_hash=hash_password("senha-setor-teste-123"),
            )
        )
        session.commit()

    def override_app_session() -> Generator[Session, None, None]:
        with test_sessions() as session:
            yield session

    app.dependency_overrides[get_app_session] = override_app_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
    get_settings.cache_clear()


def test_history_search_and_pagination_cover_all_matching_rows(
    history_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    product = Product("10.001.0007", "Parafuso inox", Decimal("1000.0000"), 1, "10.001")
    fake_connection = FakeControlConnection()

    @contextmanager
    def fake_erp_connection():
        yield fake_connection

    monkeypatch.setattr(request_api, "erp_connection", fake_erp_connection)
    monkeypatch.setattr(
        request_api, "find_products", lambda _connection, codes: {code: product for code in codes}
    )
    csrf = history_client.get("/api/auth/csrf").json()["csrf_token"]
    login = history_client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": csrf},
        json={"sector_id": 1, "password": "senha-setor-teste-123"},
    )
    assert login.status_code == 200, login.text
    csrf = login.json()["csrf_token"]

    for location in ("Ala norte", "Ala sul", "Centro cirúrgico"):
        response = history_client.post(
            "/api/requests",
            headers={"X-CSRF-Token": csrf},
            json={
                "requested_date": date.today().isoformat(),
                    "delivery_instructions": location,
                    "items": [{"material_code": "10.001.0007", "quantity": 1}],
            },
        )
        assert response.status_code == 201, response.text

    for index in range(202):
        response = history_client.post(
            "/api/requests",
            headers={"X-CSRF-Token": csrf},
            json={
                "requested_date": date.today().isoformat(),
                    "delivery_instructions": f"Estoque {index}",
                    "items": [{"material_code": "10.001.0007", "quantity": 1}],
            },
        )
        assert response.status_code == 201, response.text

    page = history_client.get("/api/requests?search=Parafuso%20inox&limit=200&offset=0")
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 205
    assert len(page.json()["items"]) == 200
    assert page.json()["offset"] == 0
    assert page.json()["limit"] == 200
    second_page = history_client.get("/api/requests?search=Parafuso%20inox&limit=200&offset=200")
    assert second_page.status_code == 200, second_page.text
    assert second_page.json()["total"] == 205
    assert len(second_page.json()["items"]) == 5
    assert second_page.json()["offset"] == 200
    assert second_page.json()["limit"] == 200
    controls = [item["itecontrol"] for item in page.json()["items"] + second_page.json()["items"]]
    assert len(controls) == len(set(controls)) == 205

    code_match = history_client.get("/api/requests", params={"search": "10.001.0007"})
    assert code_match.status_code == 200, code_match.text
    assert code_match.json()["total"] == 205
    json_key_match = history_client.get("/api/requests", params={"search": "material_code"})
    assert json_key_match.status_code == 200, json_key_match.text
    assert json_key_match.json()["total"] == 0
    wildcard_match = history_client.get("/api/requests", params={"search": "%"})
    assert wildcard_match.status_code == 200, wildcard_match.text
    assert wildcard_match.json()["total"] == 0

    older_match = history_client.get("/api/requests?search=Centro%20cir%C3%BArgico")
    assert older_match.status_code == 200, older_match.text
    assert older_match.json()["total"] == 1
    assert older_match.json()["items"][0]["delivery_instructions"] == "Centro cirúrgico"

    displayed_control = history_client.get("/api/requests?search=REQ-84333")
    assert displayed_control.status_code == 200, displayed_control.text
    assert displayed_control.json()["total"] == 1
    assert displayed_control.json()["items"][0]["itecontrol"] == 84333

    localized_date = history_client.get(
        "/api/requests", params={"search": date.today().strftime("%d/%m/%Y")}
    )
    assert localized_date.status_code == 200, localized_date.text
    assert localized_date.json()["total"] == 205

    unrelated = history_client.get("/api/requests?search=not-a-real-material")
    assert unrelated.status_code == 200, unrelated.text
    assert unrelated.json()["total"] == 0
