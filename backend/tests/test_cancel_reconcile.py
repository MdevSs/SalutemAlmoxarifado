"""Cancelamento, reconciliação, data retroativa, CSV seguro e cabeçalhos de segurança."""

from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from test_api_crud import FakeControlConnection, client, login  # noqa: F401  (fixture reutilizada)

from app.api import requests as request_api
from app.services import erp

PRODUCT = erp.Product("10.001.0007", "Parafuso inox", Decimal("100.0000"), 1, "10.001")


@pytest.fixture
def erp_ok(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    posted: list[dict[str, Any]] = []
    fake_connection = FakeControlConnection()

    @contextmanager
    def fake_erp_connection():
        yield fake_connection

    monkeypatch.setattr(request_api, "erp_connection", fake_erp_connection)
    monkeypatch.setattr(
        request_api, "find_products", lambda _c, codes: {code: PRODUCT for code in codes}
    )

    def record_post(*, itecontrol: int, requested_date: date, items: list[dict[str, Any]]) -> bool:
        posted.append({"itecontrol": itecontrol, "items": items})
        return False

    monkeypatch.setattr(request_api, "post_requisition", record_post)
    return posted


def create_request(client: TestClient, instructions: str = "Oficina") -> dict[str, Any]:
    csrf = login(client, 1, "senha-setor-teste-123")
    response = client.post(
        "/api/requests",
        headers={"X-CSRF-Token": csrf},
        json={
            "requested_date": date.today().isoformat(),
            "delivery_instructions": instructions,
            "items": [{"material_code": "10.001.0007", "quantity": "5.0000"}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_requester_cancels_own_pending_request(client: TestClient, erp_ok: list) -> None:
    created = create_request(client)
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    cancelled = client.post(
        f"/api/requests/{created['itecontrol']}/cancel",
        headers={"X-CSRF-Token": csrf},
        json={"reason": "Pedido duplicado"},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "Cancelada"
    assert "Pedido duplicado" in cancelled.json()["events"][-1]["note"]
    again = client.post(
        f"/api/requests/{created['itecontrol']}/cancel",
        headers={"X-CSRF-Token": csrf},
        json={"reason": "De novo"},
    )
    assert again.status_code == 409
    assert erp_ok == []  # cancelar nunca toca o ERP


def test_cancel_requires_a_reason_and_csrf(client: TestClient, erp_ok: list) -> None:
    created = create_request(client)
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    url = f"/api/requests/{created['itecontrol']}/cancel"
    assert client.post(url, headers={"X-CSRF-Token": csrf}, json={"reason": "  "}).status_code == 422
    assert client.post(url, json={"reason": "sem csrf"}).status_code == 403


def test_requester_cannot_cancel_after_attendance_started(
    client: TestClient, erp_ok: list
) -> None:
    created = create_request(client)
    warehouse_csrf = login(client, 2, "senha-almox-teste-1234")
    client.post(
        f"/api/requests/{created['itecontrol']}/start", headers={"X-CSRF-Token": warehouse_csrf}
    )
    requester_csrf = login(client, 1, "senha-setor-teste-123")
    response = client.post(
        f"/api/requests/{created['itecontrol']}/cancel",
        headers={"X-CSRF-Token": requester_csrf},
        json={"reason": "Mudei de ideia"},
    )
    assert response.status_code == 409


def test_warehouse_cancel_blocked_while_erp_sync_is_uncertain_then_reconciled(
    client: TestClient, erp_ok: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = create_request(client)
    control = created["itecontrol"]
    csrf = login(client, 2, "senha-almox-teste-1234")
    client.post(f"/api/requests/{control}/start", headers={"X-CSRF-Token": csrf})

    def erp_down(**_kwargs: Any) -> bool:
        raise OperationalError("insert", {}, Exception("ERP fora do ar"))

    monkeypatch.setattr(request_api, "post_requisition", erp_down)
    finalize = client.post(
        f"/api/requests/{control}/finalize",
        headers={"X-CSRF-Token": csrf},
        json={"responsible_name": "Maria", "deliveries": [{"item_index": 1, "quantity": "5"}]},
    )
    assert finalize.status_code == 503
    assert client.get(f"/api/requests/{control}").json()["erp_status"] == "falhou"

    # A baixa pode ter sido gravada no ERP: cancelar localmente deixaria movimento órfão.
    blocked = client.post(
        f"/api/requests/{control}/cancel",
        headers={"X-CSRF-Token": csrf},
        json={"reason": "Tentativa indevida"},
    )
    assert blocked.status_code == 409

    # Ainda fora do ar: a reconciliação não finaliza nada.
    still_down = client.post("/api/requests/reconcile", headers={"X-CSRF-Token": csrf})
    assert still_down.status_code == 200
    assert still_down.json() == {"checked": 1, "synced": 0, "still_pending": 1}

    # ERP volta: a reconciliação confirma sem duplicar a baixa.
    calls: list[int] = []
    monkeypatch.setattr(
        request_api,
        "post_requisition",
        lambda *, itecontrol, requested_date, items: calls.append(itecontrol) or True,
    )
    recovered = client.post("/api/requests/reconcile", headers={"X-CSRF-Token": csrf})
    assert recovered.json() == {"checked": 1, "synced": 1, "still_pending": 0}
    final = client.get(f"/api/requests/{control}").json()
    assert final["status"] == "Finalizada" and final["erp_status"] == "enviado"
    assert calls == [control]


def test_warehouse_can_cancel_in_progress_when_nothing_was_prepared(
    client: TestClient, erp_ok: list
) -> None:
    created = create_request(client)
    csrf = login(client, 2, "senha-almox-teste-1234")
    control = created["itecontrol"]
    client.post(f"/api/requests/{control}/start", headers={"X-CSRF-Token": csrf})
    response = client.post(
        f"/api/requests/{control}/cancel",
        headers={"X-CSRF-Token": csrf},
        json={"reason": "Item descontinuado"},
    )
    assert response.status_code == 200 and response.json()["status"] == "Cancelada"
    notes = client.put(
        f"/api/requests/{control}/notes",
        headers={"X-CSRF-Token": csrf},
        json={"warehouse_notes": "tarde demais"},
    )
    assert notes.status_code == 409


def test_old_request_dates_are_rejected(client: TestClient, erp_ok: list) -> None:
    csrf = login(client, 1, "senha-setor-teste-123")
    old = (date.today() - timedelta(days=30)).isoformat()
    response = client.post(
        "/api/requests",
        headers={"X-CSRF-Token": csrf},
        json={
            "requested_date": old,
            "items": [{"material_code": "10.001.0007", "quantity": "1"}],
        },
    )
    assert response.status_code == 422
    assert "anterior" in response.text


def test_csv_export_neutralizes_spreadsheet_formulas(client: TestClient, erp_ok: list) -> None:
    create_request(client, instructions='=HYPERLINK("http://evil","clique")')
    login(client, 2, "senha-almox-teste-1234")
    exported = client.get("/api/requests/export.csv")
    assert exported.status_code == 200
    assert "'=HYPERLINK" in exported.text
    assert ";=HYPERLINK" not in exported.text


def test_security_headers_are_present(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"


def test_erp_allowed_host_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import HTTPException

    from app.core.config import get_settings
    from app.core.database import validate_erp_host

    monkeypatch.setenv("ERP_ALLOWED_HOST", "erp.interno.salutem")
    get_settings.cache_clear()
    try:
        validate_erp_host("postgresql+psycopg://u:p@erp.interno.salutem:5432/db")
        with pytest.raises(HTTPException):
            validate_erp_host("postgresql+psycopg://u:p@192.168.1.2:5432/db")
    finally:
        get_settings.cache_clear()
